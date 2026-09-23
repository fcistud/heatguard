"""Offline identity-object guard (WO-020)."""
from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from heatguard._paths import _REPO_ROOT
from heatguard.identity.schema import (
    IDENTITY_SIZE_CEILING_BYTES,
    SCHEMA_VERSION,
    initialize,
    write_seeded_database,
)
from heatguard.types import IDENTITY_ROLES, SITE_SCOPE_WILDCARD

REPO = _REPO_ROOT
SCRIPT = REPO / "scripts" / "validate_identity_object.py"
COMMITTED = REPO / "tests" / "fixtures" / "identity" / "heatguard-identity-test.db"
INVALID = REPO / "tests" / "fixtures" / "identity" / "invalid"
CORRUPT = REPO / "tests" / "fixtures" / "identity" / "corrupt.db"
CI_INVOCATION = [
    "uv",
    "run",
    "python",
    "scripts/validate_identity_object.py",
    "tests/fixtures/identity/heatguard-identity-test.db",
]

GENERATE_PATH = INVALID / "generate.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_identity_object", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_generate():
    spec = importlib.util.spec_from_file_location("identity_invalid_generate", GENERATE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


vm = _load_validator()
gen = _load_generate()


def _db_from_sql(name: str, dest: Path) -> Path:
    return gen.materialize_sql(INVALID / name, dest)


def _principal_row(
    *,
    username: str = "syn.guard",
    role: str = "supervisor",
    sites: list[str] | None = None,
    password_hash: str = "$argon2id$v=19$m=8,t=1,p=1$UkVEQUNUX1RFU1RfU0FMVA$UkVEQUNUX1RFU1RfSEFTSA",
    salt: str = "REDACT_TEST_SALT",
) -> dict:
    return {
        "username": username,
        "password_hash": password_hash,
        "salt": salt,
        "kdf_params": {"m": 8, "p": 1, "t": 1},
        "role": role,
        "sites": sites if sites is not None else ["dubai"],
        "token_version": 1,
        "active": True,
        "created_at_utc": "2024-01-01T00:00:00Z",
        "updated_at_utc": "2024-01-01T00:00:00Z",
    }


def test_committed_fixture_passes() -> None:
    result = vm.validate_identity_object(COMMITTED, repo_root=REPO)
    assert result.ok, result.errors
    assert result.errors == []


def test_empty_users_table_still_enforces_schema(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    initialize(path)
    result = vm.validate_identity_object(path, repo_root=REPO)
    assert result.ok, result.errors


def test_size_at_ceiling_accepted(tmp_path: Path) -> None:
    dest = tmp_path / "at-ceiling.db"
    gen.pad_to_size(COMMITTED, dest, IDENTITY_SIZE_CEILING_BYTES)
    result = vm.validate_identity_object(dest, repo_root=REPO)
    assert result.ok, result.errors
    assert not any("ceiling" in err for err in result.errors)


def test_size_one_byte_over_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "over-ceiling.db"
    gen.pad_to_size(COMMITTED, dest, IDENTITY_SIZE_CEILING_BYTES + 1)
    result = vm.validate_identity_object(dest, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert str(IDENTITY_SIZE_CEILING_BYTES + 1) in joined
    assert str(IDENTITY_SIZE_CEILING_BYTES) in joined
    assert "8 MiB" in joined


def test_schema_version_mismatch_fails(tmp_path: Path) -> None:
    db = _db_from_sql("schema_version_mismatch.sql", tmp_path / "version.db")
    result = vm.validate_identity_object(db, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "schema_version" in joined
    assert "99" in joined
    assert str(SCHEMA_VERSION) in joined


def test_schema_version_match_passes(tmp_path: Path) -> None:
    path = tmp_path / "ok-version.db"
    initialize(path)
    result = vm.validate_identity_object(path, repo_root=REPO)
    assert result.ok, result.errors


def test_forbidden_column_fails(tmp_path: Path) -> None:
    db = _db_from_sql("forbidden_column.sql", tmp_path / "forbidden.db")
    result = vm.validate_identity_object(db, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "age" in joined
    assert "forbidden" in joined


def test_forbidden_column_absent_passes(tmp_path: Path) -> None:
    path = tmp_path / "no-pii.db"
    initialize(path)
    result = vm.validate_identity_object(path, repo_root=REPO)
    assert result.ok, result.errors
    assert not any("forbidden" in err for err in result.errors)


def test_volatile_column_fails(tmp_path: Path) -> None:
    db = _db_from_sql("volatile_column.sql", tmp_path / "volatile.db")
    result = vm.validate_identity_object(db, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "failed_login_count" in joined
    assert "volatile-state" in joined


def test_volatile_column_absent_passes(tmp_path: Path) -> None:
    path = tmp_path / "no-volatile.db"
    initialize(path)
    result = vm.validate_identity_object(path, repo_root=REPO)
    assert result.ok, result.errors
    assert not any("volatile-state" in err for err in result.errors)


def test_altered_role_check_fails(tmp_path: Path) -> None:
    db = _db_from_sql("altered_role_check.sql", tmp_path / "altered.db")
    result = vm.validate_identity_object(db, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "CHECK" in joined
    assert "admin" in joined


def test_missing_role_check_fails(tmp_path: Path) -> None:
    sql = """
    CREATE TABLE users (
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        kdf_params TEXT NOT NULL,
        role TEXT NOT NULL,
        sites TEXT NOT NULL,
        token_version INTEGER NOT NULL DEFAULT 1,
        active INTEGER NOT NULL DEFAULT 1,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
    );
    CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1');
    """
    dest = tmp_path / "missing-check.db"
    dest.write_text("", encoding="utf-8")
    conn = sqlite3.connect(dest)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    result = vm.validate_identity_object(dest, repo_root=REPO)
    assert not result.ok
    assert any("CHECK" in err and "missing" in err for err in result.errors)


def test_reordered_role_check_accepted(tmp_path: Path) -> None:
    roles = "', '".join(reversed(IDENTITY_ROLES))
    sql = f"""
    CREATE TABLE users (
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        kdf_params TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('{roles}')),
        sites TEXT NOT NULL,
        token_version INTEGER NOT NULL DEFAULT 1,
        active INTEGER NOT NULL DEFAULT 1,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
    );
    CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1');
    """
    dest = tmp_path / "reordered.db"
    conn = sqlite3.connect(dest)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    result = vm.validate_identity_object(dest, repo_root=REPO)
    assert result.ok, result.errors


def test_supervisor_wildcard_fails(tmp_path: Path) -> None:
    db = _db_from_sql("supervisor_wildcard.sql", tmp_path / "wildcard.db")
    result = vm.validate_identity_object(db, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "syn.supervisor.wildcard" in joined
    assert "supervisor" in joined
    assert "wildcard" in joined


def test_inspector_wildcard_passes(tmp_path: Path) -> None:
    path = tmp_path / "inspector-star.db"
    write_seeded_database(
        path,
        [_principal_row(username="syn.inspector.ok", role="inspector", sites=[SITE_SCOPE_WILDCARD])],
    )
    result = vm.validate_identity_object(path, repo_root=REPO)
    assert result.ok, result.errors


def test_inspector_explicit_sites_passes(tmp_path: Path) -> None:
    path = tmp_path / "inspector-sites.db"
    write_seeded_database(
        path,
        [_principal_row(username="syn.inspector.dubai", role="inspector", sites=["dubai"])],
    )
    result = vm.validate_identity_object(path, repo_root=REPO)
    assert result.ok, result.errors


def test_inspector_mixed_wildcard_rejected(tmp_path: Path) -> None:
    path = tmp_path / "inspector-mixed.db"
    initialize(path)
    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO users (
                    username, password_hash, salt, kdf_params, role, sites,
                    token_version, active, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (
                    "syn.inspector.mixed",
                    "$argon2id$v=19$m=8,t=1,p=1$UkVEQUNUX1RFU1RfU0FMVA$UkVEQUNUX1RFU1RfSEFTSA",
                    "REDACT_TEST_SALT",
                    '{"m":8,"p":1,"t":1}',
                    "inspector",
                    '["*", "dubai"]',
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:00:00Z",
                ),
            )
    finally:
        conn.close()
    result = vm.validate_identity_object(path, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "syn.inspector.mixed" in joined
    assert "ambiguous" in joined


def test_multi_violation_reports_all(tmp_path: Path) -> None:
    db = _db_from_sql("multi_violation.sql", tmp_path / "multi.db")
    result = vm.validate_identity_object(db, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "schema_version" in joined
    assert "age" in joined
    assert "failed_login_count" in joined
    assert "admin" in joined
    assert "syn.supervisor.wildcard" in joined
    assert len(result.errors) >= 5


def test_missing_file_is_error_not_traceback(tmp_path: Path) -> None:
    missing = tmp_path / "no-such.db"
    result = vm.validate_identity_object(missing, repo_root=REPO)
    assert not result.ok
    assert any("file not found" in err for err in result.errors)


def test_corrupt_file_is_error_not_traceback() -> None:
    result = vm.validate_identity_object(CORRUPT, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "not a readable SQLite" in joined or "cannot" in joined.lower()


def test_main_never_tracebacks_on_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = vm.main([str(tmp_path / "missing.db")])
    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert "FAILED" in captured.out


def test_secret_redaction(tmp_path: Path) -> None:
    db = _db_from_sql("supervisor_wildcard.sql", tmp_path / "secrets.db")
    result = vm.validate_identity_object(db, repo_root=REPO)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "REDACT_TEST_SALT" not in joined
    assert "REDACT_TEST_HASH" not in joined
    assert "$argon2" not in joined
    assert '{"m":8,"p":1,"t":1}' not in joined
    assert "password_hash" not in joined or "syn.supervisor.wildcard" in joined


def test_redact_secrets_strips_argon2() -> None:
    raw = "oops $argon2id$v=19$m=8,t=1,p=1$abc$def leaked"
    assert "$argon2" not in vm.redact_secrets(raw)
    assert "[redacted]" in vm.redact_secrets(raw)


def test_import_fallback_reads_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def blocked(name: str, *args: object, **kwargs: object):
        if name.startswith("heatguard"):
            raise ImportError("blocked for fallback test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    specs = vm.load_identity_invariants(REPO)
    assert specs.schema_version == SCHEMA_VERSION
    assert specs.ceiling_bytes == IDENTITY_SIZE_CEILING_BYTES
    assert "age" in specs.forbidden_columns
    assert "failed_login_count" in specs.volatile_columns


def test_subprocess_matches_ci_on_committed_fixture() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(COMMITTED)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_subprocess_exit_code_on_bad_file(tmp_path: Path) -> None:
    db = _db_from_sql("forbidden_column.sql", tmp_path / "bad.db")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(db)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "FAILED" in proc.stdout
    assert "age" in proc.stdout
    assert "Traceback" not in proc.stderr
    assert "Traceback" not in proc.stdout


def test_ci_workflow_invokes_script_entry_point() -> None:
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "identity-object-guard" in workflow
    assert "scripts/validate_identity_object.py" in workflow
    assert "tests/fixtures/identity/heatguard-identity-test.db" in workflow
    joined = " ".join(CI_INVOCATION)
    assert "scripts/validate_identity_object.py" in joined


def test_generate_helper_writes_over_ceiling(tmp_path: Path) -> None:
    written = gen.write_invalid_set(tmp_path / "set", ceiling_bytes=32768)
    over = written["over_ceiling.db"]
    assert over.is_file()
    assert over.stat().st_size == 32769
    result = vm.validate_identity_object(over, repo_root=REPO)
    assert not result.ok
    assert any("ceiling" in err for err in result.errors)
