"""Identity SQLite schema (Confidential).

The only mutable operator-managed store in HeatGuard. Holds principals
(username, argon2id hash, salt, KDF params, role, site scope, token version,
active flag, timestamps). **No worker personal data columns.**

This module imports only the Python standard library and ``heatguard.types``.
Site JSON uses the same compact sorted-key serialization as ``canonical.py``
without importing it, so the identity package stays a types-layer leaf.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from heatguard.types import IDENTITY_ROLES, SITE_SCOPE_WILDCARD

SCHEMA_VERSION = 1
SCHEMA_VERSION_KEY = "schema_version"

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

USERS_COLUMNS: tuple[str, ...] = (
    "username",
    "password_hash",
    "salt",
    "kdf_params",
    "role",
    "sites",
    "token_version",
    "active",
    "created_at_utc",
    "updated_at_utc",
)

_ROLE_SQL = ", ".join(f"'{role}'" for role in IDENTITY_ROLES)

DDL_USERS = f"""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    kdf_params TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ({_ROLE_SQL})),
    sites TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
)
"""

DDL_SCHEMA_META = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

DDL_STATEMENTS: tuple[str, ...] = (DDL_USERS, DDL_SCHEMA_META)

_JSON_SEPARATORS = (",", ":")


class IdentityError(Exception):
    """Base error for the identity schema package."""


class IdentitySchemaError(IdentityError):
    """Stored schema_version is missing or does not match SCHEMA_VERSION."""


class IdentitySitesError(IdentityError):
    """Site scope is not a canonical JSON array of unique strings."""


class IdentityRoleError(IdentityError):
    """Role is not one of the CHECK-constrained operator roles."""


class IdentityDuplicateError(IdentityError):
    """Username already exists (primary key)."""


def _canonical_json(obj: Any) -> str:
    """Compact JSON matching ``heatguard.canonical.dumps`` for lists/dicts of str/int."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        ensure_ascii=False,
        allow_nan=False,
    )


def canonicalize_sites(sites: object) -> str:
    """Validate and serialize site scope as canonical JSON text.

    ``[SITE_SCOPE_WILDCARD]`` (``["*"]``) is the cross-site read-only form.
    Order is preserved; duplicates and non-strings are rejected.
    """
    if not isinstance(sites, list):
        raise IdentitySitesError(
            f"sites must be a JSON array of strings, got {type(sites).__name__}"
        )
    if any(not isinstance(item, str) for item in sites):
        raise IdentitySitesError("sites entries must all be strings")
    if len(sites) != len(set(sites)):
        raise IdentitySitesError("sites must not contain duplicate values")
    if SITE_SCOPE_WILDCARD in sites and sites != [SITE_SCOPE_WILDCARD]:
        raise IdentitySitesError(
            f"{SITE_SCOPE_WILDCARD!r} must be the sole sites entry when present"
        )
    return _canonical_json(sites)


def parse_sites(raw: str) -> list[str]:
    """Parse stored sites JSON and re-validate."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IdentitySitesError("sites is not valid JSON") from exc
    canonicalize_sites(parsed)
    return parsed


def canonicalize_kdf_params(params: object) -> str:
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except json.JSONDecodeError as exc:
            raise IdentityError("kdf_params is not valid JSON") from exc
    if not isinstance(params, dict):
        raise IdentityError(
            f"kdf_params must be an object, got {type(params).__name__}"
        )
    return _canonical_json(params)


def read_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key = ?",
        (SCHEMA_VERSION_KEY,),
    ).fetchone()
    if row is None:
        raise IdentitySchemaError("schema_meta.schema_version is missing")
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise IdentitySchemaError(
            f"schema_meta.schema_version is not an integer: {row[0]!r}"
        ) from exc


def assert_schema_compatible(connection: sqlite3.Connection) -> int:
    stored = read_schema_version(connection)
    if stored != SCHEMA_VERSION:
        raise IdentitySchemaError(
            f"Identity schema_version mismatch: database has {stored}, "
            f"expected {SCHEMA_VERSION}"
        )
    return stored


def initialize(path: Path | str) -> int:
    """Create an empty identity database at *path*, idempotently.

    Same ``SCHEMA_VERSION``: no-op (data is not dropped). A different stored
    version raises ``IdentitySchemaError``. An empty users table is legitimate
    and is never an allow-all sentinel.
    """
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute("PRAGMA page_size=4096")
            for statement in DDL_STATEMENTS:
                conn.execute(statement)
            existing = conn.execute(
                "SELECT value FROM schema_meta WHERE key = ?",
                (SCHEMA_VERSION_KEY,),
            ).fetchone()
            if existing is not None:
                assert_schema_compatible(conn)
            else:
                conn.execute(
                    "INSERT INTO schema_meta(key, value) VALUES (?, ?)",
                    (SCHEMA_VERSION_KEY, str(SCHEMA_VERSION)),
                )
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        return SCHEMA_VERSION
    finally:
        conn.close()


def insert_user(connection: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    """Insert one principal. Never includes password_hash or salt in errors."""
    username = row["username"]
    if not isinstance(username, str) or not username:
        raise IdentityError("username must be a non-empty string")
    role = row["role"]
    if role not in IDENTITY_ROLES:
        raise IdentityRoleError(f"unknown role {role!r}; allowed: {IDENTITY_ROLES}")
    raw_sites = row["sites"]
    if isinstance(raw_sites, str):
        try:
            raw_sites = json.loads(raw_sites)
        except json.JSONDecodeError as exc:
            raise IdentitySitesError("sites is not valid JSON") from exc
    sites_json = canonicalize_sites(raw_sites)
    kdf_json = canonicalize_kdf_params(row["kdf_params"])
    active = row.get("active", 1)
    if isinstance(active, bool):
        active_int = 1 if active else 0
    elif isinstance(active, int) and active in (0, 1):
        active_int = active
    else:
        raise IdentityError("active must be 0, 1, or a boolean")
    try:
        connection.execute(
            """
            INSERT INTO users (
                username, password_hash, salt, kdf_params, role, sites,
                token_version, active, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                row["password_hash"],
                row["salt"],
                kdf_json,
                role,
                sites_json,
                int(row.get("token_version", 1)),
                active_int,
                row["created_at_utc"],
                row["updated_at_utc"],
            ),
        )
    except sqlite3.IntegrityError as exc:
        detail = str(exc).lower()
        if "unique" in detail or "primary key" in detail:
            raise IdentityDuplicateError(f"username already exists: {username!r}") from exc
        raise


def seed_users(connection: sqlite3.Connection, rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        insert_user(connection, row)


def write_seeded_database(
    path: Path | str,
    rows: Sequence[Mapping[str, Any]],
) -> Path:
    """Initialize *path* (replacing any existing file) and seed *rows*."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    initialize(dest)
    conn = sqlite3.connect(dest)
    try:
        with conn:
            seed_users(conn, rows)
        conn.execute("VACUUM")
        conn.execute("PRAGMA journal_mode=DELETE")
    finally:
        conn.close()
    return dest


def load_seed_document(path: Path | str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    users = payload.get("users", payload)
    if not isinstance(users, list):
        raise IdentityError("seed document must contain a users array")
    return users
