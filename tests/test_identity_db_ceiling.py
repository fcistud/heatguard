"""Identity SQLite size ceiling and schema-exclusion gate (WO-016)."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from heatguard._paths import _REPO_ROOT
from heatguard.identity.schema import FORBIDDEN_IDENTITY_COLUMNS as PKG_FORBIDDEN

REPO = _REPO_ROOT
SCRIPT = REPO / "scripts" / "check_identity_db_size.py"
DDL = REPO / "infra" / "identity" / "schema.sql"
COMMITTED = REPO / "tests" / "fixtures" / "identity" / "heatguard-identity-test.db"
FIXTURES = REPO / "tests" / "fixtures" / "identity"


def _load():
    spec = importlib.util.spec_from_file_location("check_identity_db_size", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cl = _load()


def _db_from_sql(sql_path: Path, dest: Path) -> Path:
    return cl.materialize_from_ddl(sql_path, dest)


def _pad(src: Path, dest: Path, size: int) -> Path:
    data = src.read_bytes()
    if len(data) > size:
        pytest.skip(f"source fixture is already {len(data)} bytes")
    dest.write_bytes(data + b"\0" * (size - len(data)))
    return dest


def test_forbidden_set_matches_schema_package() -> None:
    assert cl.FORBIDDEN_IDENTITY_COLUMNS == PKG_FORBIDDEN


def test_committed_ddl_exists() -> None:
    assert DDL.is_file()
    text = DDL.read_text(encoding="utf-8")
    for role in cl.REQUIRED_ROLES:
        assert f"'{role}'" in text


def test_compliant_schema_and_committed_fixture(tmp_path: Path) -> None:
    assert cl.evaluate_path(COMMITTED) == []
    generated = _db_from_sql(DDL, tmp_path / "from-ddl.db")
    assert cl.evaluate_path(generated) == []
    conn = sqlite3.connect(generated)
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    finally:
        conn.close()


def test_script_subprocess_against_committed_tree(tmp_path: Path) -> None:
    report = tmp_path / "identity-ceiling-report.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPO), "--report", str(report)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["size_bytes"] <= cl.CEILING_BYTES
    assert payload["errors"] == []


def test_resolve_prefers_env_over_committed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generated = _db_from_sql(DDL, tmp_path / "env.db")
    monkeypatch.setenv(cl.ENV_PATH, str(generated))
    path, source = cl.resolve_identity_db(repo=REPO)
    assert source == "env"
    assert path == generated.resolve()


def test_resolve_env_missing_file_is_hard_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(cl.ENV_PATH, str(tmp_path / "missing.db"))
    with pytest.raises(cl.IdentityCeilingError, match=cl.ENV_PATH):
        cl.resolve_identity_db(repo=REPO)


def test_resolve_committed_then_ddl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(cl.ENV_PATH, raising=False)
    path, source = cl.resolve_identity_db(repo=REPO)
    assert source == "committed"
    assert path == COMMITTED.resolve()

    empty = tmp_path / "empty-repo"
    (empty / "infra" / "identity").mkdir(parents=True)
    (empty / "infra" / "identity" / "schema.sql").write_text(DDL.read_text(encoding="utf-8"))
    path, source = cl.resolve_identity_db(repo=empty, generate_dir=tmp_path / "gen")
    assert source == "ddl"
    assert path.is_file()


def test_unresolvable_path_fails_loud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(cl.ENV_PATH, raising=False)
    with pytest.raises(cl.IdentityCeilingError, match="never compliant"):
        cl.resolve_identity_db(repo=tmp_path)


def test_byte_boundaries(tmp_path: Path) -> None:
    src = COMMITTED
    under = _pad(src, tmp_path / "under.db", cl.CEILING_BYTES - 1)
    at = _pad(src, tmp_path / "at.db", cl.CEILING_BYTES)
    over = _pad(src, tmp_path / "over.db", cl.CEILING_BYTES + 1)
    assert cl.evaluate_path(under) == []
    assert cl.evaluate_path(at) == []
    over_errors = cl.evaluate_path(over)
    assert over_errors
    assert "8388608" in over_errors[0] or str(cl.CEILING_BYTES) in over_errors[0]


def test_forbidden_table_column(tmp_path: Path) -> None:
    db = _db_from_sql(FIXTURES / "forbidden_column.sql", tmp_path / "forbidden.db")
    errors = cl.evaluate_path(db)
    assert any("age" in err for err in errors)


def test_forbidden_view_column(tmp_path: Path) -> None:
    db = _db_from_sql(FIXTURES / "forbidden_view.sql", tmp_path / "view.db")
    errors = cl.evaluate_path(db)
    assert any("worker_id" in err for err in errors)


def test_role_check_missing_and_extra(tmp_path: Path) -> None:
    missing = _db_from_sql(FIXTURES / "missing_role_check.sql", tmp_path / "missing.db")
    extra = _db_from_sql(FIXTURES / "extra_role.sql", tmp_path / "extra.db")
    missing_errors = cl.evaluate_path(missing)
    extra_errors = cl.evaluate_path(extra)
    assert any("missing" in err.lower() or "CHECK" in err for err in missing_errors)
    assert any("admin" in err and "CREATE TABLE" in err for err in extra_errors)
