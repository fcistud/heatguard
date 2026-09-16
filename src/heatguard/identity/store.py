"""Read-only identity SQLite access (WO-019).

Runtime connections use a ``mode=ro&immutable=1`` URI. There is no write API.
Statements are parameterized only.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .schema import assert_schema_compatible, parse_sites


_SELECT_PRINCIPALS = (
    "SELECT username, role, sites, token_version, active FROM users"
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


def read_principals(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return principal rows without password material."""
    assert_schema_compatible(connection)
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
