"""Layering contract ratchet and process-boundary gate (WO-011)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from heatguard._paths import _REPO_ROOT

REPO = _REPO_ROOT
FIXTURES = REPO / "tests" / "fixtures" / "layering"
CONTRACTS = REPO / ".importlinter"
BASELINE = REPO / "infra" / "architecture" / "layering_baseline.json"
SCRIPT = REPO / "scripts" / "check_layering.py"
NORMATIVE_MODULES = (
    "heatguard.legal_precedence",
    "heatguard.types",
    "heatguard.policy_retrieval",
    "heatguard.policy_rag",
)


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_layering", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cl = _load_checker()


def _eval_report(report: Path, baseline: Path) -> object:
    text = report.read_text(encoding="utf-8")
    returncode = 1 if "BROKEN" in text else 0
    return cl.evaluate(
        report_text=text,
        returncode=returncode,
        baseline_path=baseline,
        contracts_path=CONTRACTS,
    )


def test_committed_baseline_schema() -> None:
    entries, errors = cl.load_baseline(BASELINE)
    assert errors == []
    assert entries
    schema_errors = cl.validate_baseline_schema(entries)
    assert schema_errors == []
    for entry in entries:
        assert set(entry) >= set(cl.REQUIRED_BASELINE_KEYS)
        assert not cl.is_forbidden_contract(entry["contract"])


def test_contracts_file_names_normative_modules() -> None:
    text = CONTRACTS.read_text(encoding="utf-8")
    for name in NORMATIVE_MODULES:
        assert name in text, name
    names = cl.parse_contracts_file(CONTRACTS)
    assert "HeatGuard layered architecture" in names.values()
    assert "types leaf purity" in names.values()
    assert "legal_precedence never imports service or api" in names.values()
    assert "policy_retrieval above policy_rag" in names.values()


def test_clean_report_empty_baseline_passes(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    result = _eval_report(FIXTURES / "clean.txt", baseline)
    assert result.ok, result.errors
    assert result.violations == []


def test_new_violation_ratchet_fails(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    result = _eval_report(FIXTURES / "new_violation.txt", baseline)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "new violation not in baseline" in joined
    assert "heatguard.types" in joined
    assert "heatguard.api" in joined


def test_stale_baseline_ratchet_fails() -> None:
    result = _eval_report(
        FIXTURES / "stale_baseline.txt",
        FIXTURES / "baseline_partial.json",
    )
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "stale baseline entry" in joined
    assert "heatguard.hydration" in joined
    assert "delete" in joined


def test_undeclared_module_is_a_new_violation(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    result = _eval_report(FIXTURES / "undeclared.txt", baseline)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "heatguard.brand_new" in joined
    assert cl.UNASSIGNED_IMPORTED in joined or "unassigned" in joined.lower() or "new violation" in joined


def test_unparseable_broken_report_fails_closed() -> None:
    result = _eval_report(FIXTURES / "unparseable.txt", BASELINE)
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "unrecognized output" in joined
    assert "fail open" in joined


def test_forbidden_contract_cannot_be_baselined(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "importer": "heatguard.types",
                        "imported": "heatguard.api",
                        "contract": "types leaf purity",
                        "reason": "must not be allowed",
                        "owner": "architecture",
                        "dated_at": "2026-09-07",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = _eval_report(FIXTURES / "clean.txt", baseline)
    assert not result.ok
    assert any("empty baseline" in err for err in result.errors)


def test_import_linter_is_hash_pinned_in_dev_export() -> None:
    dev = (REPO / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "import-linter==2.13" in dev
    assert "--hash=sha256:" in dev
    prod = (REPO / "requirements.txt").read_text(encoding="utf-8")
    assert "import-linter" not in prod


def test_script_subprocess_against_real_tree() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPO)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK — layering contracts match baseline" in proc.stdout


def _copy_tree_for_break(tmp_path: Path) -> Path:
    dest = tmp_path / "tree"
    dest.mkdir()
    shutil.copy2(CONTRACTS, dest / ".importlinter")
    shutil.copytree(REPO / "src" / "heatguard", dest / "src" / "heatguard")
    arch = dest / "infra" / "architecture"
    arch.mkdir(parents=True)
    shutil.copy2(BASELINE, arch / "layering_baseline.json")
    return dest


def test_direct_service_import_in_legal_precedence_fails(tmp_path: Path) -> None:
    dest = _copy_tree_for_break(tmp_path)
    target = dest / "src" / "heatguard" / "legal_precedence.py"
    text = target.read_text(encoding="utf-8")
    target.write_text(
        text + "\nfrom . import service  # WO-011 deliberate forbidden import\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(dest)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    joined = proc.stdout + proc.stderr
    assert "legal_precedence never imports service or api" in joined
    assert "heatguard.legal_precedence" in joined
    assert "heatguard.service" in joined


def test_unassigned_module_fails_exhaustive(tmp_path: Path) -> None:
    dest = _copy_tree_for_break(tmp_path)
    (dest / "src" / "heatguard" / "brand_new.py").write_text(
        '"""WO-011 exhaustive probe — not assigned to a layer."""\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(dest)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    joined = proc.stdout + proc.stderr
    assert "heatguard.brand_new" in joined
    assert "unassigned" in joined or "not listed as layers" in joined or "new violation" in joined


def test_internal_import_in_types_fails(tmp_path: Path) -> None:
    dest = _copy_tree_for_break(tmp_path)
    target = dest / "src" / "heatguard" / "types.py"
    text = target.read_text(encoding="utf-8")
    target.write_text(
        text + "\nfrom . import calendar_ban  # WO-011 deliberate leaf break\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(dest)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    joined = proc.stdout + proc.stderr
    assert "types leaf purity" in joined
