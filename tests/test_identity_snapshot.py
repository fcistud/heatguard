"""Boot-time identity snapshot loader (WO-019)."""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from heatguard._paths import (
    DEFAULT_IDENTITY_TMP_DIR,
    ENV_IDENTITY_TMP_DIR,
    _REPO_ROOT,
    resolve_identity_tmp_dir,
)
from heatguard.identity.fetch import (
    ENV_IDENTITY_OBJECT_URI,
    GcsFetcher,
    IdentityLoadError,
    LocalFileFetcher,
    MemoryFetcher,
    fetcher_from_env,
)
from heatguard.identity.schema import SCHEMA_VERSION, initialize
from heatguard.identity.snapshot import (
    IDENTITY_CEILING_BYTES,
    boot_identity_store,
    clear_snapshot,
    get_current,
    last_load_error,
    load_snapshot,
)
from heatguard.identity.store import open_readonly
from heatguard.observability.logging import redact_processor

FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "identity"
SEEDED = FIXTURE_DIR / "heatguard-identity-test.db"
CORRUPT = FIXTURE_DIR / "corrupt.db"


class _BoomFetcher:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def fetch(self):  # noqa: ANN204
        raise self.exc


class _Resp:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content

    def json(self) -> dict:
        return self._payload


def test_successful_load_from_committed_fixture(tmp_path: Path) -> None:
    snap = load_snapshot(LocalFileFetcher(SEEDED), tmp_dir=tmp_path)
    assert snap.principal_count == 5
    assert snap.generation
    syn = snap.lookup("syn.supervisor")
    assert syn is not None
    assert syn.roles == ("supervisor",)
    assert syn.sites == ("dubai",)
    assert syn.token_version == 1
    assert syn.active is True
    assert snap.lookup("nobody") is None
    disabled = snap.lookup("syn.disabled")
    assert disabled is not None and disabled.active is False
    assert list(tmp_path.glob("heatguard-identity.*.db")) == []


def test_empty_store_is_not_allow_all(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    initialize(db)
    snap = load_snapshot(LocalFileFetcher(db), tmp_dir=tmp_path / "tmp")
    assert snap.principal_count == 0
    assert snap.lookup("anyone") is None
    assert snap.lookup("") is None
    published = boot_identity_store(fetcher=LocalFileFetcher(db), tmp_dir=tmp_path / "boot")
    assert published is not None
    assert published.lookup("syn.supervisor") is None
    assert get_current() is not None


def test_readonly_connection_rejects_insert(tmp_path: Path) -> None:
    dest = tmp_path / "ro.db"
    shutil.copy(SEEDED, dest)
    os.chmod(dest, 0o600)
    conn = open_readonly(dest)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, kdf_params, "
                "role, sites, token_version, active, created_at_utc, updated_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "syn.injected",
                    "x",
                    "x",
                    "{}",
                    "supervisor",
                    '["dubai"]',
                    1,
                    1,
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:00:00Z",
                ),
            )
    finally:
        conn.close()
    assert load_snapshot(LocalFileFetcher(dest), tmp_dir=tmp_path / "tmp").lookup(
        "syn.injected"
    ) is None


def test_permission_denied_does_not_publish(tmp_path: Path) -> None:
    clear_snapshot()
    result = boot_identity_store(
        fetcher=_BoomFetcher(IdentityLoadError("permission_denied", "denied")),
        tmp_dir=tmp_path,
    )
    assert result is None
    assert get_current() is None
    err = last_load_error()
    assert err is not None and err.reason == "permission_denied"


def test_timeout_does_not_publish(tmp_path: Path) -> None:
    result = boot_identity_store(fetcher=_BoomFetcher(TimeoutError()), tmp_dir=tmp_path)
    assert result is None
    assert get_current() is None
    err = last_load_error()
    assert err is not None and err.reason == "timeout"


def test_corrupt_file_does_not_publish(tmp_path: Path) -> None:
    result = boot_identity_store(fetcher=LocalFileFetcher(CORRUPT), tmp_dir=tmp_path)
    assert result is None
    assert get_current() is None
    err = last_load_error()
    assert err is not None and err.reason == "corrupt"


def test_zero_byte_object_is_corrupt(tmp_path: Path) -> None:
    with pytest.raises(IdentityLoadError, match="zero bytes") as exc:
        load_snapshot(MemoryFetcher(b""), tmp_dir=tmp_path)
    assert exc.value.reason == "corrupt"


def test_schema_mismatch_names_versions(tmp_path: Path) -> None:
    db = tmp_path / "mismatch.db"
    initialize(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "UPDATE schema_meta SET value = ? WHERE key = ?",
            ("99", "schema_version"),
        )
        conn.commit()
    finally:
        conn.close()
    result = boot_identity_store(fetcher=LocalFileFetcher(db), tmp_dir=tmp_path / "tmp")
    assert result is None
    assert get_current() is None
    err = last_load_error()
    assert err is not None
    assert err.reason == "schema_mismatch"
    assert "99" in err.message
    assert str(SCHEMA_VERSION) in err.message


def test_size_ceiling_includes_observed_size(tmp_path: Path) -> None:
    over = IDENTITY_CEILING_BYTES + 1
    with pytest.raises(IdentityLoadError) as exc:
        load_snapshot(MemoryFetcher(b"\x00" * over), tmp_dir=tmp_path)
    assert exc.value.reason == "size_ceiling"
    assert str(over) in str(exc.value)
    assert str(IDENTITY_CEILING_BYTES) in str(exc.value)


def test_duplicate_case_differing_usernames_rejected(tmp_path: Path) -> None:
    db = tmp_path / "dup.db"
    initialize(db)
    conn = sqlite3.connect(db)
    try:
        for name in ("Admin", "admin"):
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, kdf_params, "
                "role, sites, token_version, active, created_at_utc, updated_at_utc) "
                "VALUES (?, 'x', 'x', '{}', 'supervisor', '[\"dubai\"]', 1, 1, "
                "'2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')",
                (name,),
            )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(IdentityLoadError) as exc:
        load_snapshot(LocalFileFetcher(db), tmp_dir=tmp_path / "tmp")
    assert exc.value.reason == "duplicate_username"


def test_tmp_dir_full_does_not_publish(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("x", encoding="utf-8")
    result = boot_identity_store(fetcher=LocalFileFetcher(SEEDED), tmp_dir=blocked)
    assert result is None
    assert get_current() is None
    err = last_load_error()
    assert err is not None and err.reason == "tmp_write_failed"


def test_missing_uri_boot_unpublished() -> None:
    result = boot_identity_store(env={})
    assert result is None
    assert get_current() is None
    err = last_load_error()
    assert err is not None and err.reason == "missing_uri"


def test_fetcher_from_env_file_and_gs() -> None:
    local = fetcher_from_env({ENV_IDENTITY_OBJECT_URI: str(SEEDED)})
    assert isinstance(local, LocalFileFetcher)
    gcs = fetcher_from_env({ENV_IDENTITY_OBJECT_URI: "gs://bucket/identity/heatguard-identity.db"})
    assert isinstance(gcs, GcsFetcher)
    assert gcs.bucket == "bucket"
    assert gcs.object_name == "identity/heatguard-identity.db"


def test_gcs_fetcher_permission_denied() -> None:
    def request(*_a, **_k):
        return _Resp(403)

    fetcher = GcsFetcher(
        "gs://bucket/obj.db",
        token_provider=lambda: "tok",
        request=request,
    )
    with pytest.raises(IdentityLoadError) as exc:
        fetcher.fetch()
    assert exc.value.reason == "permission_denied"


def test_gcs_fetcher_downloads_generation(tmp_path: Path) -> None:
    payload = SEEDED.read_bytes()
    calls: list[object] = []

    def request(_method: str, _url: str, **kwargs: object):
        params = kwargs.get("params") or {}
        calls.append(params)
        if isinstance(params, dict) and params.get("alt") == "media":
            assert params.get("generation") == "99"
            return _Resp(200, content=payload)
        return _Resp(200, {"generation": "99", "size": str(len(payload))})

    fetcher = GcsFetcher(
        "gs://bucket/identity/heatguard-identity.db",
        token_provider=lambda: "tok",
        request=request,
    )
    fetched = fetcher.fetch()
    assert fetched.generation == "99"
    assert len(calls) == 2
    snap = load_snapshot(MemoryFetcher(fetched.payload, fetched.generation), tmp_dir=tmp_path)
    assert snap.generation == "99"
    assert snap.principal_count == 5


def test_gcs_rejects_oversize_before_media() -> None:
    calls: list[object] = []

    def request(_method: str, _url: str, **kwargs: object):
        calls.append(kwargs.get("params"))
        return _Resp(
            200,
            {"generation": "1", "size": str(IDENTITY_CEILING_BYTES + 1)},
        )

    fetcher = GcsFetcher(
        "gs://bucket/obj.db",
        token_provider=lambda: "tok",
        request=request,
    )
    with pytest.raises(IdentityLoadError) as exc:
        fetcher.fetch()
    assert exc.value.reason == "size_ceiling"
    assert len(calls) == 1


def test_local_file_rejects_oversize_before_read(tmp_path: Path) -> None:
    over = tmp_path / "too-big.db"
    over.touch()
    os.truncate(over, IDENTITY_CEILING_BYTES + 1)
    with pytest.raises(IdentityLoadError) as exc:
        LocalFileFetcher(over).fetch()
    assert exc.value.reason == "size_ceiling"


def test_file_uri_decodes_spaces(tmp_path: Path) -> None:
    dest = tmp_path / "a b.db"
    shutil.copy(SEEDED, dest)
    fetcher = fetcher_from_env({ENV_IDENTITY_OBJECT_URI: dest.resolve().as_uri()})
    assert isinstance(fetcher, LocalFileFetcher)
    assert fetcher.path == dest.resolve()
    assert load_snapshot(fetcher, tmp_dir=tmp_path / "tmp").principal_count == 5


def test_forbidden_column_rejected(tmp_path: Path) -> None:
    db = tmp_path / "forbidden.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript((FIXTURE_DIR / "forbidden_column.sql").read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    result = boot_identity_store(fetcher=LocalFileFetcher(db), tmp_dir=tmp_path / "tmp")
    assert result is None
    err = last_load_error()
    assert err is not None and err.reason == "forbidden_column"


def test_extra_role_check_rejected(tmp_path: Path) -> None:
    db = tmp_path / "extra-role.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript((FIXTURE_DIR / "extra_role.sql").read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES (?, ?)",
            ("schema_version", "1"),
        )
        conn.commit()
    finally:
        conn.close()
    result = boot_identity_store(fetcher=LocalFileFetcher(db), tmp_dir=tmp_path / "tmp")
    assert result is None
    err = last_load_error()
    assert err is not None and err.reason == "schema_mismatch"


def test_resolve_identity_tmp_dir_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_IDENTITY_TMP_DIR, raising=False)
    assert resolve_identity_tmp_dir(env={}) == DEFAULT_IDENTITY_TMP_DIR
    assert resolve_identity_tmp_dir(env={ENV_IDENTITY_TMP_DIR: "/var/tmp/hg"}) == Path(
        "/var/tmp/hg"
    )


def test_loader_logs_redact_credential_shaped_fields() -> None:
    event = redact_processor(
        None,
        "warning",
        {
            "event": "heatguard.identity.boot_failed",
            "password_hash": "$argon2id$secret",
            "password": "hunter2",
            "generation": "1",
        },
    )
    assert event["password_hash"] == "REDACTED"
    assert event["password"] == "REDACTED"
    assert event["generation"] == "1"
    assert event["event"] == "heatguard.identity.boot_failed"
