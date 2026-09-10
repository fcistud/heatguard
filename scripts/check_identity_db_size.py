#!/usr/bin/env python3
"""Identity SQLite size ceiling and schema-exclusion gate (WO-016).

Caps the operator identity object at 8 MiB and asserts it contains no worker
personal-data columns. Production identity data is never copied into CI.

Path resolution (first match wins):

1. ``HEATGUARD_IDENTITY_DB_PATH`` when set (missing file is a hard error)
2. Committed fixture ``tests/fixtures/identity/heatguard-identity-test.db``
3. A temp database materialized from ``infra/identity/schema.sql``

An absent identity set is never treated as compliant.

Usage:
  uv run python scripts/check_identity_db_size.py
  uv run python scripts/check_identity_db_size.py --root /path/to/repo
  uv run python scripts/check_identity_db_size.py --path /tmp/identity.db
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CEILING_BYTES = 8_388_608  # 8 MiB
COMMITTED_FIXTURE = Path("tests") / "fixtures" / "identity" / "heatguard-identity-test.db"
DDL_REL = Path("infra") / "identity" / "schema.sql"
ENV_PATH = "HEATGUARD_IDENTITY_DB_PATH"

FORBIDDEN_IDENTITY_COLUMNS = frozenset(
    {
        "age",
        "weight_kg",
        "height_m",
        "has_comorbidity",
        "worker_id",
        "crew_id",
    }
)
REQUIRED_ROLES = (
    "supervisor",
    "ohs_officer",
    "compliance_officer",
    "inspector",
)
ROLE_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*role\s+IN\s*\(([^)]*)\)\s*\)",
    re.IGNORECASE,
)
SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class IdentityCeilingError(Exception):
    """Hard failure of the identity ceiling / schema-exclusion gate."""


def materialize_from_ddl(ddl_path: Path, dest: Path) -> Path:
    sql = ddl_path.read_text(encoding="utf-8")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    conn = sqlite3.connect(dest)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    return dest


def resolve_identity_db(
    *,
    repo: Path,
    env: dict[str, str] | None = None,
    explicit: Path | None = None,
    generate_dir: Path | None = None,
) -> tuple[Path, str]:
    """Return ``(path, source)`` for the identity object.

    *source* is ``env``, ``committed``, or ``ddl``.
    """
    environ = os.environ if env is None else env
    if explicit is not None:
        if not explicit.is_file():
            raise IdentityCeilingError(f"--path is not a file: {explicit}")
        return explicit.resolve(), "explicit"
    raw = environ.get(ENV_PATH)
    if raw:
        path = Path(raw)
        if not path.is_file():
            raise IdentityCeilingError(
                f"{ENV_PATH} is set but is not a file: {path}. "
                "Unset it or point it at a non-production identity database."
            )
        return path.resolve(), "env"
    committed = repo / COMMITTED_FIXTURE
    if committed.is_file():
        return committed.resolve(), "committed"
    ddl = repo / DDL_REL
    if ddl.is_file():
        dest_dir = generate_dir if generate_dir is not None else Path(tempfile.mkdtemp(prefix="heatguard-identity-"))
        dest = dest_dir / "identity-from-ddl.db"
        return materialize_from_ddl(ddl, dest).resolve(), "ddl"
    raise IdentityCeilingError(
        "no identity object or DDL can be resolved. Set "
        f"{ENV_PATH}, commit {COMMITTED_FIXTURE}, or add {DDL_REL}. "
        "An absent identity set is never compliant."
    )


def _quote_ident(name: str) -> str:
    if not SAFE_IDENT_RE.match(name):
        raise IdentityCeilingError(f"unsafe sqlite identifier: {name!r}")
    return name


def relation_columns(connection: sqlite3.Connection) -> dict[str, list[str]]:
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


def users_table_sql(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    if row is None or not row[0]:
        raise IdentityCeilingError("users table is missing from the identity database")
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


def inspect_schema(connection: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    columns = relation_columns(connection)
    for relation, cols in sorted(columns.items()):
        hit = sorted(FORBIDDEN_IDENTITY_COLUMNS.intersection(cols))
        if hit:
            errors.append(
                f"{relation}: forbidden worker-personal-data column(s) {hit}"
            )
    create_sql = users_table_sql(connection)
    roles = parse_role_check(create_sql)
    required = set(REQUIRED_ROLES)
    if roles is None:
        errors.append(
            "users.role CHECK constraint is missing; "
            f"CREATE TABLE text: {create_sql}"
        )
    elif roles != required:
        errors.append(
            "users.role CHECK constraint must list exactly "
            f"{list(REQUIRED_ROLES)}; found {sorted(roles)}. "
            f"CREATE TABLE text: {create_sql}"
        )
    return errors


def evaluate_path(path: Path) -> list[str]:
    errors: list[str] = []
    size = path.stat().st_size
    if size > CEILING_BYTES:
        errors.append(
            f"{path}: {size} bytes exceeds identity ceiling of {CEILING_BYTES} bytes (8 MiB)"
        )
        return errors
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise IdentityCeilingError(f"cannot open identity database read-only: {path}: {exc}") from exc
    try:
        errors.extend(inspect_schema(conn))
    finally:
        conn.close()
    return errors


def write_report(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="Repository root")
    parser.add_argument("--path", default=None, help="Explicit identity SQLite path")
    parser.add_argument(
        "--report",
        default=str(ROOT / "artifacts" / "identity-ceiling-report.json"),
        help="JSON report path",
    )
    args = parser.parse_args(argv)

    repo = Path(args.root)
    errors: list[str] = []
    resolved: Path | None = None
    source = ""
    size = 0
    try:
        resolved, source = resolve_identity_db(
            repo=repo,
            explicit=Path(args.path) if args.path else None,
        )
        size = resolved.stat().st_size
        errors.extend(evaluate_path(resolved))
    except IdentityCeilingError as exc:
        errors.append(str(exc))

    report = {
        "ok": not errors,
        "path": str(resolved) if resolved is not None else None,
        "source": source or None,
        "size_bytes": size,
        "ceiling_bytes": CEILING_BYTES,
        "errors": errors,
    }
    write_report(report, Path(args.report))
    if errors:
        print("Identity ceiling check FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(
        f"OK — identity object {resolved} ({source}) is {size} bytes "
        f"<= {CEILING_BYTES}; no forbidden columns on tables or views; "
        "role CHECK intact"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
