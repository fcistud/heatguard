"""Read-only identity SQLite access (WO-019).

Runtime connections use a ``mode=ro&immutable=1`` URI. There is no write API.
Statements are parameterized only.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from heatguard.types import IDENTITY_ROLES

from .fetch import IdentityLoadError
from .schema import (
    FORBIDDEN_IDENTITY_COLUMNS,
    USERS_COLUMNS,
    assert_schema_compatible,
    parse_sites,
)


_SELECT_PRINCIPALS = (
    "SELECT username, role, sites, token_version, active FROM users"
)
_ROLE_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*role\s+IN\s*\(([^)]*)\)\s*\)",
    re.IGNORECASE,
)


def readonly_uri(path: Path | str) -> str:
    """SQLite URI that refuses writes and assumes the file is immutable."""
    resolved = Path(path).resolve()
    return resolved.as_uri() + "?mode=ro&immutable=1"


def open_readonly(path: Path | str) -> sqlite3.Connection:
    """Open *path* read-only. Caller must close the connection."""
    conn = sqlite3.connect(readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def assert_runtime_schema(connection: sqlite3.Connection) -> None:
    """Version, required columns, forbidden PII columns, and exact role CHECK."""
    assert_schema_compatible(connection)
    cols = [
        str(row[1])
        for row in connection.execute("PRAGMA table_info(users)").fetchall()
    ]
    if not cols:
        raise IdentityLoadError("schema_mismatch", "users table is missing")
    missing = [name for name in USERS_COLUMNS if name not in cols]
    if missing:
        raise IdentityLoadError(
            "schema_mismatch",
            "users table is missing required columns",
        )
    forbidden = sorted(FORBIDDEN_IDENTITY_COLUMNS.intersection(cols))
    if forbidden:
        raise IdentityLoadError(
            "forbidden_column",
            "identity object contains forbidden worker-personal-data columns",
        )
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
        ("table", "users"),
    ).fetchone()
    create_sql = str(row[0]) if row is not None and row[0] else ""
    match = _ROLE_CHECK_RE.search(create_sql)
    if match is None:
        raise IdentityLoadError("schema_mismatch", "users.role CHECK constraint is missing")
    found = {part.strip().strip("'\"") for part in match.group(1).split(",") if part.strip()}
    required = set(IDENTITY_ROLES)
    if found != required:
        raise IdentityLoadError(
            "schema_mismatch",
            "users.role CHECK constraint does not list the four operator roles",
        )


def read_principals(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return principal rows without password material."""
    assert_runtime_schema(connection)
    rows = connection.execute(_SELECT_PRINCIPALS).fetchall()
    principals: list[dict[str, Any]] = []
    for row in rows:
        principals.append(
            {
                "username": row["username"],
                "role": row["role"],
                "sites": parse_sites(row["sites"]),
                "token_version": int(row["token_version"]),
                "active": bool(int(row["active"])),
            }
        )
    return principals
