#!/usr/bin/env python3
"""Validate a HeatGuard identity SQLite object (WO-020).

Offline pre-upload / CI guard. Inspects one identity database and reports
every invariant failure in a single batch — never fail-fast, never print
password hashes, salts, or KDF parameters, never raise an unhandled
traceback for a bad input file.

Enforced invariants:

* object size at or below ``IDENTITY_SIZE_CEILING_BYTES`` (8 MiB)
* ``schema_meta.schema_version`` equals code ``SCHEMA_VERSION``
* ``users.role`` carries the four-value CHECK constraint
* no column name intersects ``FORBIDDEN_IDENTITY_COLUMNS``
* no column matches ``VOLATILE_STATE_COLUMNS``
* wildcard site scope is present only on inspector rows (and is the sole
  sites entry when present)

Usage:
  uv run python scripts/validate_identity_object.py
  uv run python scripts/validate_identity_object.py path/to/heatguard-identity.db
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]

COMMITTED_FIXTURE = (
    Path("tests") / "fixtures" / "identity" / "heatguard-identity-test.db"
)
SCHEMA_VERSION_FIXTURE = (
    Path("tests") / "fixtures" / "identity" / "expected_schema_version.txt"
)
INSPECTOR_ROLE = "inspector"
SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ROLE_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*role\s+IN\s*\(([^)]*)\)\s*\)",
    re.IGNORECASE,
)
ARGON2_RE = re.compile(r"\$argon2[^\s,;\"']+")
_SECRET_SUBSTRINGS = (
    "password_hash",
    "salt",
    "kdf_params",
)

_FALLBACK_FORBIDDEN = frozenset(
    {
        "age",
        "weight_kg",
        "height_m",
        "has_comorbidity",
        "worker_id",
        "crew_id",
    }
)
_FALLBACK_VOLATILE = frozenset(
    {
        "failed_login_count",
        "lockout_until",
        "last_login_at",
    }
)
_FALLBACK_ROLES = (
    "supervisor",
    "ohs_officer",
    "compliance_officer",
    "inspector",
)
_FALLBACK_WILDCARD = "*"
_FALLBACK_CEILING = 8 * 1024 * 1024
_FALLBACK_SCHEMA_VERSION = 1


class IdentityInvariants(NamedTuple):
    schema_version: int
    ceiling_bytes: int
    forbidden_columns: frozenset[str]
    volatile_columns: frozenset[str]
    roles: tuple[str, ...]
    wildcard: str
    inspector_role: str


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def fail(self, msg: str) -> None:
        self.errors.append(redact_secrets(msg))


def _repo_root() -> Path:
    return ROOT


def _ensure_src_on_path() -> None:
    src = str(_repo_root() / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _read_fixture_schema_version(repo: Path) -> int:
    fixture = repo / SCHEMA_VERSION_FIXTURE
    if fixture.is_file():
        text = fixture.read_text(encoding="utf-8").strip()
        if text:
            return int(text.splitlines()[0].strip())
    ddl = repo / "infra" / "identity" / "schema.sql"
    if ddl.is_file():
        match = re.search(r"SCHEMA_VERSION\s*=\s*(\d+)", ddl.read_text(encoding="utf-8"))
        if match:
            return int(match.group(1))
    return _FALLBACK_SCHEMA_VERSION


def load_identity_invariants(repo: Path | None = None) -> IdentityInvariants:
    """Prefer live schema imports; fall back to committed fixtures."""
    root = repo or _repo_root()
    try:
        _ensure_src_on_path()
        from heatguard.identity.schema import (
            FORBIDDEN_IDENTITY_COLUMNS,
            IDENTITY_SIZE_CEILING_BYTES,
            SCHEMA_VERSION,
            VOLATILE_STATE_COLUMNS,
        )
        from heatguard.types import IDENTITY_ROLES, SITE_SCOPE_WILDCARD
    except ImportError:
        return IdentityInvariants(
            schema_version=_read_fixture_schema_version(root),
            ceiling_bytes=_FALLBACK_CEILING,
            forbidden_columns=_FALLBACK_FORBIDDEN,
            volatile_columns=_FALLBACK_VOLATILE,
            roles=_FALLBACK_ROLES,
            wildcard=_FALLBACK_WILDCARD,
            inspector_role=INSPECTOR_ROLE,
        )
    return IdentityInvariants(
        schema_version=SCHEMA_VERSION,
        ceiling_bytes=IDENTITY_SIZE_CEILING_BYTES,
        forbidden_columns=frozenset(FORBIDDEN_IDENTITY_COLUMNS),
        volatile_columns=frozenset(VOLATILE_STATE_COLUMNS),
        roles=tuple(IDENTITY_ROLES),
        wildcard=SITE_SCOPE_WILDCARD,
        inspector_role=INSPECTOR_ROLE,
    )


def redact_secrets(text: str) -> str:
    """Strip credential material that must never appear in operator output."""
    redacted = ARGON2_RE.sub("[redacted]", text)
    # Values are never selected; still refuse to echo secret *column contents*
    # if a driver message interpolated a row.
    for marker in ("$argon2id$", "$argon2i$", "$argon2d$"):
        if marker in redacted.lower():
            redacted = re.sub(
                re.escape(marker) + r"[^\s,;\"']*",
                "[redacted]",
                redacted,
                flags=re.IGNORECASE,
            )
    return redacted


def _quote_ident(name: str) -> str:
    if not SAFE_IDENT_RE.match(name):
        raise ValueError(f"unsafe sqlite identifier: {name!r}")
    return name


def _relation_columns(connection: sqlite3.Connection) -> dict[str, list[str]]:
    rows = connection.execute(
        "SELECT name, type FROM sqlite_master "
        "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    found: dict[str, list[str]] = {}
    for name, _kind in rows:
        ident = _quote_ident(str(name))
        cols = [
            str(col[1])
            for col in connection.execute(f"PRAGMA table_info({ident})").fetchall()
        ]
        found[str(name)] = cols
    return found


def _users_table_sql(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
        ("table", "users"),
    ).fetchone()
    if row is None or not row[0]:
        return None
    return str(row[0])


def parse_role_check(create_sql: str) -> set[str] | None:
    match = ROLE_CHECK_RE.search(create_sql)
    if match is None:
        return None
    roles: set[str] = set()
    for part in match.group(1).split(","):
        token = part.strip().strip("'\"")
        if token:
            roles.add(token)
    return roles


def _check_size(path: Path, ceiling: int, result: ValidationResult) -> None:
    size = path.stat().st_size
    if size > ceiling:
        result.fail(
            f"{path}: {size} bytes exceeds identity ceiling of "
            f"{ceiling} bytes (8 MiB)"
        )


def _check_schema_version(
    path: Path,
    connection: sqlite3.Connection,
    expected: int,
    result: ValidationResult,
) -> None:
    try:
        row = connection.execute(
            "SELECT value FROM schema_meta WHERE key = ?",
            ("schema_version",),
        ).fetchone()
    except sqlite3.Error as exc:
        result.fail(f"{path}: cannot read schema_meta.schema_version: {exc}")
        return
    if row is None:
        result.fail(f"{path}: schema_meta.schema_version is missing")
        return
    try:
        stored = int(row[0])
    except (TypeError, ValueError):
        result.fail(
            f"{path}: schema_meta.schema_version is not an integer: {row[0]!r}"
        )
        return
    if stored != expected:
        result.fail(
            f"{path}: schema_version is {stored}, expected {expected}"
        )


def _check_columns(
    path: Path,
    connection: sqlite3.Connection,
    invariants: IdentityInvariants,
    result: ValidationResult,
) -> None:
    try:
        columns = _relation_columns(connection)
    except ValueError as exc:
        result.fail(f"{path}: {exc}")
        return
    except sqlite3.Error as exc:
        result.fail(f"{path}: cannot inspect columns: {exc}")
        return
    for relation, cols in sorted(columns.items()):
        forbidden = sorted(invariants.forbidden_columns.intersection(cols))
        if forbidden:
            result.fail(
                f"{path}:{relation}: forbidden worker-personal-data "
                f"column(s) {forbidden}"
            )
        volatile = sorted(invariants.volatile_columns.intersection(cols))
        if volatile:
            result.fail(
                f"{path}:{relation}: volatile-state column(s) {volatile}"
            )


def _check_role_constraint(
    path: Path,
    connection: sqlite3.Connection,
    invariants: IdentityInvariants,
    result: ValidationResult,
) -> None:
    try:
        create_sql = _users_table_sql(connection)
    except sqlite3.Error as exc:
        result.fail(f"{path}: cannot read sqlite_master for users: {exc}")
        return
    if create_sql is None:
        result.fail(f"{path}: users table is missing")
        return
    roles = parse_role_check(create_sql)
    required = set(invariants.roles)
    if roles is None:
        result.fail(f"{path}: users.role CHECK constraint is missing")
        return
    if roles != required:
        result.fail(
            f"{path}: users.role CHECK constraint must list exactly "
            f"{sorted(required)}; found {sorted(roles)}"
        )


def _check_wildcard_scope(
    path: Path,
    connection: sqlite3.Connection,
    invariants: IdentityInvariants,
    result: ValidationResult,
) -> None:
    wildcard = invariants.wildcard
    like_pattern = f"%{wildcard}%"
    try:
        rows = connection.execute(
            "SELECT username, role, sites FROM users WHERE sites LIKE ?",
            (like_pattern,),
        ).fetchall()
    except sqlite3.Error as exc:
        result.fail(f"{path}: cannot inspect site scope: {exc}")
        return
    for username, role, raw_sites in rows:
        principal = str(username)
        try:
            sites = json.loads(raw_sites)
        except (TypeError, json.JSONDecodeError):
            result.fail(
                f"{path}: principal {principal!r} has sites that are not valid JSON"
            )
            continue
        if not isinstance(sites, list) or wildcard not in sites:
            continue
        if sites != [wildcard]:
            result.fail(
                f"{path}: principal {principal!r} has ambiguous site scope "
                f"({wildcard} mixed with explicit sites)"
            )
            continue
        if role != invariants.inspector_role:
            result.fail(
                f"{path}: principal {principal!r} has wildcard site scope "
                f"but role is {role!r} (wildcard is permitted only for "
                f"{invariants.inspector_role})"
            )


def _open_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def validate_identity_object(
    path: Path | str,
    *,
    repo_root: Path | None = None,
    invariants: IdentityInvariants | None = None,
) -> ValidationResult:
    """Validate one identity database. Always returns; never raises."""
    result = ValidationResult()
    db_path = Path(path)
    specs = invariants or load_identity_invariants(repo_root or _repo_root())

    if not db_path.exists():
        result.fail(f"{db_path}: file not found")
        return result
    if not db_path.is_file():
        result.fail(f"{db_path}: is not a file")
        return result

    try:
        _check_size(db_path, specs.ceiling_bytes, result)
    except OSError as exc:
        result.fail(f"{db_path}: cannot read file: {exc}")
        return result

    try:
        conn = _open_readonly(db_path)
    except sqlite3.Error as exc:
        result.fail(
            f"{db_path}: not a readable SQLite identity database: {exc}"
        )
        return result

    try:
        _check_schema_version(db_path, conn, specs.schema_version, result)
        _check_columns(db_path, conn, specs, result)
        _check_role_constraint(db_path, conn, specs, result)
        _check_wildcard_scope(db_path, conn, specs, result)
    except Exception as exc:  # noqa: BLE001 — convert surprises to a report line
        result.fail(f"{db_path}: unexpected validation error: {exc}")
    finally:
        conn.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        nargs="?",
        default=str(_repo_root() / COMMITTED_FIXTURE),
        help=(
            "Path to an identity SQLite file "
            f"(default: {COMMITTED_FIXTURE})"
        ),
    )
    args = parser.parse_args(argv)

    try:
        result = validate_identity_object(Path(args.database))
    except Exception as exc:  # noqa: BLE001 — CLI must never traceback
        print("Identity object validation FAILED:")
        print(f"  - {redact_secrets(str(exc))}")
        return 1

    if not result.ok:
        print("Identity object validation FAILED:")
        for err in result.errors:
            # Belt-and-braces: never emit secret-shaped tokens even if a
            # future check accidentally interpolated a row.
            lowered = err.lower()
            if any(secret in lowered and "$argon2" in lowered for secret in _SECRET_SUBSTRINGS):
                print(f"  - {redact_secrets(err)}")
            else:
                print(f"  - {err}")
        return 1

    print(f"OK — identity object valid ({args.database})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
