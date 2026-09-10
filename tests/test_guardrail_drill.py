"""Deliberate-break drill (WO-015)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from heatguard._paths import _REPO_ROOT
from heatguard.canonical import dumps

REPO = _REPO_ROOT
SCRIPT = REPO / "scripts" / "guardrail_drill.py"
MANIFEST = REPO / "tests" / "fixtures" / "drill" / "mutations.json"


def _load_drill():
    spec = importlib.util.spec_from_file_location("guardrail_drill", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


drill = _load_drill()


def test_manifest_declares_four_required_gates() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert tuple(payload["gates_covered"]) == drill.REQUIRED_GATES
    ids = [case["id"] for case in payload["cases"]]
    assert len(ids) == len(set(ids))
    assert {case["gate"] for case in payload["cases"]} == set(drill.REQUIRED_GATES)
    for case in payload["cases"]:
        assert (REPO / case["target"]).is_file(), case["target"]


def test_insert_line_end_and_after() -> None:
    assert drill.insert_line("alpha\n", {"text": "beta", "where": "end"}) == "alpha\nbeta\n"
    out = drill.insert_line(
        "keep\nneedle\nrest\n",
        {"text": "inserted\n", "where": "after", "after": "needle\n"},
    )
    assert out == "keep\nneedle\ninserted\nrest\n"


def test_replace_substring_and_delete_key() -> None:
    assert (
        drill.replace_substring("ab-ab", {"old": "ab", "new": "x", "count": 1}) == "x-ab"
    )
    assert (
        drill.replace_substring("ab-ab", {"old": "ab", "new": "x", "count": 0}) == "x-x"
    )
    deleted = drill.delete_key(
        '{"keep": 1, "drop": 2}',
        {"key": "drop"},
    )
    assert json.loads(deleted) == {"keep": 1}


def test_mutation_target_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "gone.py"
    with pytest.raises(drill.DrillError, match="mutation target not found"):
        drill.apply_mutation(missing, "insert_line", {"text": "x\n", "where": "end"})
    with pytest.raises(drill.DrillError, match="mutation target substring not found"):
        drill.replace_substring("abc", {"old": "zzz", "new": "", "count": 1})


def test_score_gate_three_outcomes() -> None:
    assert (
        drill.score_gate(
            exit_code=1,
            output="Layering check FAILED:\n  - types leaf purity: new forbidden",
            expected_exit_code=1,
            expected_diagnostic="types leaf purity",
        )
        == "pass"
    )
    assert (
        drill.score_gate(
            exit_code=1,
            output="ImportError: broken environment",
            expected_exit_code=1,
            expected_diagnostic="types leaf purity",
        )
        == "inconclusive"
    )
    assert (
        drill.score_gate(
            exit_code=0,
            output="OK",
            expected_exit_code=1,
            expected_diagnostic="types leaf purity",
        )
        == "missed"
    )
    missed = drill.outcome_message("layering-types-leaf-import", "missed", "types leaf purity")
    assert missed == "gate did not fail on seeded violation: layering-types-leaf-import"
    inconclusive = drill.outcome_message(
        "layering-types-leaf-import", "inconclusive", "types leaf purity"
    )
    assert "inconclusive drill" in inconclusive
    assert "layering-types-leaf-import" in inconclusive


def test_copy_ignore_drops_heavy_directories(tmp_path: Path) -> None:
    names = [
        ".git",
        "node_modules",
        "src",
        "dist",
        "__pycache__",
        "data",
    ]
    ignored = drill.copy_ignore(str(tmp_path), names)
    assert ".git" in ignored
    assert "node_modules" in ignored
    assert "__pycache__" in ignored
    assert "src" not in ignored
    assert "data" not in ignored
    web = tmp_path / "web"
    web.mkdir()
    web_ignored = drill.copy_ignore(str(web), ["dist", "src"])
    assert "dist" in web_ignored
    assert "src" not in web_ignored


def test_temp_directory_cleanup_on_exception(tmp_path: Path) -> None:
    drill._active_temps.clear()
    td, dest = drill.isolate_tree(REPO)
    nest = dest / "src" / "heatguard"
    assert nest.is_dir()
    name = td.name
    try:
        raise RuntimeError("forced drill failure")
    except RuntimeError:
        errors = drill.cleanup_temps()
    assert errors == []
    assert not Path(name).exists()


def test_report_canonical_and_stable() -> None:
    report = {
        "ok": True,
        "gates_covered": list(drill.REQUIRED_GATES),
        "cases": [
            {
                "duration_ms": 12,
                "exit_code": 1,
                "gate": "layering",
                "id": "layering-types-leaf-import",
                "matched_diagnostic": True,
                "message": "layering-types-leaf-import: pass",
                "mutation": {"operation": "insert_line", "payload": {}, "target": "x"},
                "outcome": "pass",
            }
        ],
    }
    a = dumps(report)
    b = dumps(report)
    assert a == b
    assert a == dumps(json.loads(a))


def test_full_drill_subprocess(tmp_path: Path) -> None:
    out = tmp_path / "guardrail-drill"
    before = drill.git_porcelain(REPO)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(REPO),
            "--manifest",
            str(MANIFEST),
            "--output-dir",
            str(out),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report_path = out / "report.json"
    summary_path = out / "summary.md"
    assert report_path.is_file()
    assert summary_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["gates_covered"] == list(drill.REQUIRED_GATES)
    by_id = {row["id"]: row for row in report["cases"]}
    assert set(by_id) == {case["id"] for case in json.loads(MANIFEST.read_text())["cases"]}
    for row in report["cases"]:
        assert row["outcome"] == "pass", row
        assert row["exit_code"] != 0
        assert row["matched_diagnostic"] is True
    assert "PASS" in summary_path.read_text(encoding="utf-8")
    assert drill.git_porcelain(REPO) == before


def test_same_file_cases_use_separate_copies(tmp_path: Path) -> None:
    """Two mutations of types.py must not share a working tree."""
    drill._active_temps.clear()
    td_a, tree_a = drill.isolate_tree(REPO)
    td_b, tree_b = drill.isolate_tree(REPO)
    try:
        target_a = tree_a / "src" / "heatguard" / "types.py"
        target_b = tree_b / "src" / "heatguard" / "types.py"
        drill.apply_mutation(
            target_a,
            "insert_line",
            {"text": "from . import calendar_ban  # copy-a\n", "where": "end"},
        )
        assert "copy-a" in target_a.read_text(encoding="utf-8")
        assert "copy-a" not in target_b.read_text(encoding="utf-8")
        assert tree_a.resolve() != tree_b.resolve()
    finally:
        drill.cleanup_temps()
        shutil.rmtree(td_a.name, ignore_errors=True)
        shutil.rmtree(td_b.name, ignore_errors=True)
