"""Boot-time identity snapshot materialization and atomic holder (WO-019).

The request path reads ``get_current()`` only — no I/O. Fetch, verify, and
SQLite open happen on boot (and later refresh stories). Logging stays in
``api.py`` so this types-layer package never imports observability.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .._paths import resolve_identity_tmp_dir
from .fetch import (
    FetchedObject,
    IdentityFetcher,
    IdentityLoadError,
    fetcher_from_env,
)
from .schema import IdentitySchemaError, SCHEMA_VERSION
from .store import open_readonly, read_principals

IDENTITY_CEILING_BYTES = 8_388_608  # 8 MiB — same cap as scripts/check_identity_db_size.py

REASON_CORRUPT = "corrupt"
REASON_DUPLICATE = "duplicate_username"
REASON_PERMISSION = "permission_denied"
REASON_SCHEMA = "schema_mismatch"
REASON_SIZE = "size_ceiling"
REASON_TIMEOUT = "timeout"
REASON_TMP_WRITE = "tmp_write_failed"
REASON_UNPUBLISHED = "unpublished"


@dataclass(frozen=True, slots=True)
class Principal:
    roles: tuple[str, ...]
    sites: tuple[str, ...]
    token_version: int
    active: bool


@dataclass(frozen=True, slots=True)
class Snapshot:
    principals: Mapping[str, Principal]
    generation: str
    loaded_at: datetime
    principal_count: int

    def lookup(self, username: str) -> Principal | None:
        """Deny-by-default: unknown names return None, never a permissive record."""
        return self.principals.get(username)


class SnapshotHolder:
    """Lock-guarded current snapshot. ``None`` means unpublished (not allow-all)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: Snapshot | None = None
        self._last_error: IdentityLoadError | None = None

    def get_current(self) -> Snapshot | None:
        with self._lock:
            return self._current

    def last_error(self) -> IdentityLoadError | None:
        with self._lock:
            return self._last_error

    def publish(self, snapshot: Snapshot) -> None:
        with self._lock:
            self._current = snapshot
            self._last_error = None

    def clear(self) -> None:
        with self._lock:
            self._current = None

    def record_error(self, error: IdentityLoadError) -> None:
        with self._lock:
            self._current = None
            self._last_error = error


_HOLDER = SnapshotHolder()


def get_current() -> Snapshot | None:
    return _HOLDER.get_current()


def last_load_error() -> IdentityLoadError | None:
    return _HOLDER.last_error()


def publish(snapshot: Snapshot) -> None:
    _HOLDER.publish(snapshot)


def clear_snapshot() -> None:
    _HOLDER.clear()


def load_snapshot(
    fetcher: IdentityFetcher,
    *,
    tmp_dir: Path | str,
) -> Snapshot:
    """Download, verify, open read-only, and materialize an immutable snapshot.

    Does not publish. On any failure the temp file is removed and no snapshot
    is returned.
    """
    fetched = _fetch(fetcher)
    _verify_payload(fetched)
    dest = _write_temp(fetched, Path(tmp_dir))
    try:
        principals = _materialize(dest)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    mapping = MappingProxyType(principals)
    return Snapshot(
        principals=mapping,
        generation=fetched.generation,
        loaded_at=datetime.now(timezone.utc),
        principal_count=len(mapping),
    )


def boot_identity_store(
    *,
    fetcher: IdentityFetcher | None = None,
    tmp_dir: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> Snapshot | None:
    """Cold-start load: clear any prior handle, publish on success, else unpublished.

    Never raises — callers log ``last_load_error()``. Readiness stays not_ready
    while the handle is unpublished.
    """
    _HOLDER.clear()
    try:
        resolved_fetcher = fetcher if fetcher is not None else fetcher_from_env(env)
        resolved_tmp = Path(tmp_dir) if tmp_dir is not None else resolve_identity_tmp_dir(env=env)
        snapshot = load_snapshot(resolved_fetcher, tmp_dir=resolved_tmp)
    except IdentityLoadError as exc:
        _HOLDER.record_error(exc)
        return None
    except Exception as exc:  # noqa: BLE001 — boot must not crash the process
        wrapped = IdentityLoadError(REASON_CORRUPT, "identity object could not be loaded")
        wrapped.__cause__ = exc
        _HOLDER.record_error(wrapped)
        return None
    _HOLDER.publish(snapshot)
    return snapshot


def _fetch(fetcher: IdentityFetcher) -> FetchedObject:
    try:
        return fetcher.fetch()
    except IdentityLoadError:
        raise
    except TimeoutError as exc:
        raise IdentityLoadError(REASON_TIMEOUT, "identity object fetch timed out") from exc
    except PermissionError as exc:
        raise IdentityLoadError(
            REASON_PERMISSION, "identity object is not readable"
        ) from exc
    except FileNotFoundError as exc:
        raise IdentityLoadError("missing_object", "identity object is missing") from exc


def _verify_payload(fetched: FetchedObject) -> None:
    size = len(fetched.payload)
    if size == 0:
        raise IdentityLoadError(REASON_CORRUPT, "identity object is zero bytes")
    if size > IDENTITY_CEILING_BYTES:
        raise IdentityLoadError(
            REASON_SIZE,
            f"identity object is {size} bytes; ceiling is {IDENTITY_CEILING_BYTES}",
        )


def _write_temp(fetched: FetchedObject, tmp_dir: Path) -> Path:
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        dest = tmp_dir / f"heatguard-identity.{fetched.generation}.db"
        dest.write_bytes(fetched.payload)
    except OSError as exc:
        raise IdentityLoadError(
            REASON_TMP_WRITE, "identity object could not be written to hg-tmp"
        ) from exc
    return dest


def _materialize(path: Path) -> dict[str, Principal]:
    try:
        conn = open_readonly(path)
    except Exception as exc:  # noqa: BLE001 — corrupt/unreadable SQLite
        raise IdentityLoadError(REASON_CORRUPT, "identity object is corrupt") from exc
    try:
        try:
            rows = read_principals(conn)
        except IdentitySchemaError as exc:
            raise IdentityLoadError(
                REASON_SCHEMA,
                f"identity schema_version mismatch: database has incompatible "
                f"version (running code expects {SCHEMA_VERSION}): {exc}",
            ) from exc
        except IdentityLoadError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IdentityLoadError(REASON_CORRUPT, "identity object is corrupt") from exc
    finally:
        conn.close()

    seen_folded: dict[str, str] = {}
    principals: dict[str, Principal] = {}
    for row in rows:
        username = row["username"]
        if not isinstance(username, str) or not username:
            raise IdentityLoadError(REASON_CORRUPT, "identity object is corrupt")
        folded = username.casefold()
        prior = seen_folded.get(folded)
        if prior is not None:
            raise IdentityLoadError(
                REASON_DUPLICATE,
                "identity object has duplicate or case-differing usernames",
            )
        seen_folded[folded] = username
        principals[username] = Principal(
            roles=(str(row["role"]),),
            sites=tuple(row["sites"]),
            token_version=int(row["token_version"]),
            active=bool(row["active"]),
        )
    return principals
