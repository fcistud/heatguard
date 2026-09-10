"""Identity SQLite schema invariants (WO-017)."""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from heatguard._paths import _REPO_ROOT
from heatguard.canonical import dumps as canonical_dumps
from heatguard.identity.schema import (
    FORBIDDEN_IDENTITY_COLUMNS,
    SCHEMA_VERSION,
    USERS_COLUMNS,
    IdentityDuplicateError,
    IdentitySchemaError,
    IdentitySitesError,
    assert_schema_compatible,
    canonicalize_sites,
    initialize,
    insert_user,
    load_seed_document,
    parse_sites,
    read_schema_version,
    write_seeded_database,
)
from heatguard.types import IDENTITY_ROLES, SITE_SCOPE_WILDCARD

FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "identity"
SEED_JSON = FIXTURE_DIR / "seed_users.json"
SEEDED_DB = FIXTURE_DIR / "heatguard-identity-test.db"


def _user_row() -> dict:
    return {
        "username": "syn.unique",
        "password_hash": "$argon2id$v=19$m=8,t=1,p=1$c3lundGg$c3lundGg",
        "salt": "c3lundGg",
        "kdf_params": {"m": 8, "p": 1, "t": 1},
        "role": "supervisor",
        "sites": ["dubai"],
        "token_version": 1,
        "active": True,
        "created_at_utc": "2024-01-01T00:00:00Z",
        "updated_at_utc": "2024-01-01T00:00:00Z",
    }


def test_identity_package_imports_only_stdlib_and_types() -> None:
    allowed_top = {
        "__future__",
        "json",
        "sqlite3",
        "pathlib",
        "typing",
        "heatguard",
    }
    identity_dir = _REPO_ROOT / "src" / "heatguard" / "identity"
    for path in identity_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top in allowed_top, f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.level and node.module == "schema":
                    continue
                top = node.module.split(".")[0]
                if top == "heatguard":
                    assert node.module == "heatguard.types" or node.module.startswith(
                        "heatguard.identity"
                    ), f"{path.name} imports {node.module}"
                else:
                    assert top in allowed_top, f"{path.name} imports {node.module}"


def test_initialize_creates_empty_users_not_allow_all(tmp_path: Path) -> None:
    path = tmp_path / "identity.db"
    version = initialize(path)
    assert version == SCHEMA_VERSION
    conn = sqlite3.connect(path)
    try:
        assert read_schema_version(conn) == SCHEMA_VERSION
        assert assert_schema_compatible(conn) == SCHEMA_VERSION
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert count == 0
        cols = [
            row[1]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        ]
        assert tuple(cols) == USERS_COLUMNS
    finally:
        conn.close()


def test_initialize_idempotent_preserves_rows(tmp_path: Path) -> None:
    path = tmp_path / "identity.db"
    initialize(path)
    conn = sqlite3.connect(path)
    try:
        insert_user(conn, _user_row())
        conn.commit()
    finally:
        conn.close()
    assert initialize(path) == SCHEMA_VERSION
    conn = sqlite3.connect(path)
    try:
        usernames = [
            row[0] for row in conn.execute("SELECT username FROM users").fetchall()
        ]
        assert usernames == ["syn.unique"]
    finally:
        conn.close()


def test_schema_version_mismatch_names_both_versions(tmp_path: Path) -> None:
    path = tmp_path / "identity.db"
    initialize(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "UPDATE schema_meta SET value = ? WHERE key = ?",
            ("99", "schema_version"),
        )
        conn.commit()
        with pytest.raises(IdentitySchemaError, match="99") as exc:
            assert_schema_compatible(conn)
        assert str(SCHEMA_VERSION) in str(exc.value)
    finally:
        conn.close()
    with pytest.raises(IdentitySchemaError, match="99"):
        initialize(path)


def test_role_check_rejects_admin(tmp_path: Path) -> None:
    path = tmp_path / "identity.db"
    initialize(path)
    conn = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO users (
                    username, password_hash, salt, kdf_params, role, sites,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "syn.admin",
                    "x",
                    "y",
                    "{}",
                    "admin",
                    '["dubai"]',
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:00:00Z",
                ),
            )
    finally:
        conn.close()


def test_username_unique_and_case_sensitive(tmp_path: Path) -> None:
    path = tmp_path / "identity.db"
    initialize(path)
    conn = sqlite3.connect(path)
    try:
        insert_user(conn, _user_row())
        with pytest.raises(IdentityDuplicateError, match="syn.unique"):
            insert_user(conn, _user_row())
        other = _user_row()
        other["username"] = "Syn.unique"
        insert_user(conn, other)
        names = [
            row[0] for row in conn.execute("SELECT username FROM users ORDER BY username")
        ]
        assert names == ["Syn.unique", "syn.unique"]
    finally:
        conn.close()


def test_canonical_sites_round_trip() -> None:
    raw = ["riyadh", "dubai"]
    stored = canonicalize_sites(raw)
    assert stored == canonical_dumps(raw)
    assert parse_sites(stored) == raw
    wildcard = canonicalize_sites([SITE_SCOPE_WILDCARD])
    assert parse_sites(wildcard) == [SITE_SCOPE_WILDCARD]


def test_canonical_sites_rejects_malformed() -> None:
    with pytest.raises(IdentitySitesError):
        canonicalize_sites("dubai")
    with pytest.raises(IdentitySitesError):
        canonicalize_sites(["dubai", 1])
    with pytest.raises(IdentitySitesError):
        canonicalize_sites(["dubai", "dubai"])


def test_forbidden_identity_columns_absent(tmp_path: Path) -> None:
    path = tmp_path / "identity.db"
    initialize(path)
    conn = sqlite3.connect(path)
    try:
        names: set[str] = set()
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        ]
        for table in tables:
            for col in conn.execute(f"PRAGMA table_info({table})").fetchall():
                names.add(col[1])
    finally:
        conn.close()
    assert names.isdisjoint(FORBIDDEN_IDENTITY_COLUMNS)
    for forbidden in (
        "age",
        "weight_kg",
        "height_m",
        "has_comorbidity",
        "worker_id",
        "crew_id",
    ):
        assert forbidden in FORBIDDEN_IDENTITY_COLUMNS


def test_seed_covers_all_roles_wildcard_and_disabled() -> None:
    users = load_seed_document(SEED_JSON)
    roles = {row["role"] for row in users}
    assert roles == set(IDENTITY_ROLES)
    assert any(row["sites"] == [SITE_SCOPE_WILDCARD] and row["role"] == "inspector" for row in users)
    assert any(row["active"] is False for row in users)
    assert all("@" not in row["username"] or row["username"].startswith("syn.") for row in users)
    assert all(row["username"].startswith("syn.") for row in users)


def _sql_dump(path: Path) -> str:
    """Logical SQLite contents — stable across library versions; file bytes are not."""
    conn = sqlite3.connect(path)
    try:
        return "\n".join(conn.iterdump())
    finally:
        conn.close()


def test_fixture_builder_determinism(tmp_path: Path) -> None:
    users = load_seed_document(SEED_JSON)
    a = write_seeded_database(tmp_path / "a.db", users)
    b = write_seeded_database(tmp_path / "b.db", users)
    assert a.read_bytes() == b.read_bytes()
    assert _sql_dump(a) == _sql_dump(b)


def test_seeded_fixture_readonly_uri(tmp_path: Path) -> None:
    users = load_seed_document(SEED_JSON)
    db_path = write_seeded_database(tmp_path / "seeded.db", users)
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            "SELECT username, role, sites, active FROM users ORDER BY username"
        ).fetchall()
        by_name = {row[0]: row for row in rows}
        assert set(by_name) == {u["username"] for u in users}
        for seed in users:
            username, role, sites_json, active = by_name[seed["username"]]
            assert role == seed["role"]
            assert parse_sites(sites_json) == seed["sites"]
            assert bool(active) is bool(seed["active"])
    finally:
        conn.close()


def test_committed_db_round_trip_readonly(tmp_path: Path) -> None:
    assert SEEDED_DB.is_file(), "run: uv run python scripts/build_identity_fixture.py"
    uri = f"file:{SEEDED_DB.resolve().as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        users = load_seed_document(SEED_JSON)
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert count == len(users)
        assert read_schema_version(conn) == SCHEMA_VERSION
    finally:
        conn.close()
    rebuilt = write_seeded_database(tmp_path / "rebuilt.db", users)
    assert _sql_dump(SEEDED_DB) == _sql_dump(rebuilt)
