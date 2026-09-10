#!/usr/bin/env python3
"""Deliberate-break drill for HeatGuard guardrail gates (WO-015).

Copies the repository into throwaway trees, applies one seeded mutation per
case, runs only that case's gate, and scores on both exit code and expected
diagnostic. The checked-out working tree is never mutated; reports land under
``artifacts/guardrail-drill/``.

Usage:
  uv run python scripts/guardrail_drill.py
  uv run python scripts/guardrail_drill.py --manifest tests/fixtures/drill/mutations.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heatguard.canonical import dump  # noqa: E402

DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "drill" / "mutations.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "guardrail-drill"

REQUIRED_GATES = (
    "layering",
    "legal_contract_schema",
    "guardrail_copy",
    "four_lane_regression",
)

REQUIRED_CASE_KEYS = (
    "id",
    "gate",
    "target",
    "operation",
    "payload",
    "gate_command",
    "expected_exit_code",
    "expected_diagnostic",
)

IGNORE_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".eggs",
        "dist",
        "htmlcov",
        "artifacts",
        ".coverage",
        ".cursor",
        ".forge",
    }
)

GATE_TIMEOUT_SEC = 180
MISSED_MESSAGE = "gate did not fail on seeded violation"

_active_temps: list[tempfile.TemporaryDirectory[str]] = []


class DrillError(Exception):
    """Hard drill failure (manifest, copy, mutation target, cleanup)."""


def copy_ignore(directory: str, names: list[str]) -> set[str]:
    """Ignore caches, VCS, and build outputs so the drill fits on CI disks."""
    ignored = {name for name in names if name in IGNORE_DIR_NAMES}
    parent = Path(directory).name
    if parent == "web" and "dist" in names:
        ignored.add("dist")
    return ignored


def insert_line(text: str, payload: Mapping[str, Any]) -> str:
    raw = payload.get("text")
    if not isinstance(raw, str) or not raw:
        raise DrillError("insert_line payload.text must be a non-empty string")
    line = raw if raw.endswith("\n") else raw + "\n"
    where = payload.get("where", "end")
    if where == "end":
        body = text if text.endswith("\n") or text == "" else text + "\n"
        return body + line
    if where == "after":
        needle = payload.get("after")
        if not isinstance(needle, str) or not needle:
            raise DrillError("insert_line where=after requires payload.after")
        idx = text.find(needle)
        if idx < 0:
            raise DrillError("mutation target substring not found")
        at = idx + len(needle)
        return text[:at] + line + text[at:]
    raise DrillError(f"unknown insert_line where={where!r}")


def replace_substring(text: str, payload: Mapping[str, Any]) -> str:
    old = payload.get("old")
    new = payload.get("new")
    if not isinstance(old, str) or not old:
        raise DrillError("replace_substring payload.old must be a non-empty string")
    if not isinstance(new, str):
        raise DrillError("replace_substring payload.new must be a string")
    if old not in text:
        raise DrillError("mutation target substring not found")
    raw_count = payload.get("count", 1)
    if not isinstance(raw_count, int) or raw_count < 0:
        raise DrillError("replace_substring payload.count must be an int >= 0")
    found = text.count(old)
    if raw_count == 0:
        return text.replace(old, new)
    if found < raw_count:
        raise DrillError(
            f"replace_substring expected {raw_count} occurrence(s) of old, found {found}"
        )
    return text.replace(old, new, raw_count)


def delete_key(text: str, payload: Mapping[str, Any]) -> str:
    key = payload.get("key")
    if not isinstance(key, str) or not key:
        raise DrillError("delete_key payload.key must be a non-empty string")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DrillError("delete_key target is not valid JSON") from exc
    if not isinstance(data, dict):
        raise DrillError("delete_key target JSON must be an object")
    if key not in data:
        raise DrillError(f"mutation target key not found: {key!r}")
    del data[key]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


MUTATIONS: dict[str, Callable[[str, Mapping[str, Any]], str]] = {
    "insert_line": insert_line,
    "replace_substring": replace_substring,
    "delete_key": delete_key,
}


def apply_mutation(path: Path, operation: str, payload: Mapping[str, Any]) -> None:
    if not path.is_file():
        raise DrillError(f"mutation target not found: {path}")
    handler = MUTATIONS.get(operation)
    if handler is None:
        raise DrillError(f"unknown mutation operation: {operation!r}")
    original = path.read_text(encoding="utf-8")
    path.write_text(handler(original, payload), encoding="utf-8")


def score_gate(
    *,
    exit_code: int,
    output: str,
    expected_exit_code: int,
    expected_diagnostic: str,
) -> str:
    """Return ``pass``, ``inconclusive``, or ``missed``.

    ``expected_exit_code`` is the gate's documented non-zero status (usually 1).
    Scoring follows the AC: any non-zero exit plus the diagnostic substring
    is a pass, so an unexpected but still failing code cannot be mistaken
    for a miss.
    """
    del expected_exit_code
    diagnostic_hit = expected_diagnostic in output
    if exit_code != 0 and diagnostic_hit:
        return "pass"
    if exit_code == 0:
        return "missed"
    return "inconclusive"


def outcome_message(case_id: str, outcome: str, expected_diagnostic: str) -> str:
    if outcome == "missed":
        return f"{MISSED_MESSAGE}: {case_id}"
    if outcome == "inconclusive":
        return (
            f"inconclusive drill: {case_id}: gate failed without expected "
            f"diagnostic {expected_diagnostic!r}"
        )
    return f"{case_id}: pass"


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DrillError(f"unparseable mutations manifest {path}: {exc}") from exc
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise DrillError("mutations manifest must contain a non-empty cases array")
    for case in cases:
        if not isinstance(case, dict):
            raise DrillError("each drill case must be an object")
        missing = [key for key in REQUIRED_CASE_KEYS if key not in case]
        if missing:
            raise DrillError(f"case {case.get('id')!r} missing keys: {missing}")
    gates = payload.get("gates_covered")
    if not isinstance(gates, list) or not gates:
        raise DrillError("mutations manifest must list gates_covered")
    return payload


def expand_command(command: Sequence[str], *, python: str, tree: Path) -> list[str]:
    mapping = {"{python}": python, "{tree}": str(tree)}
    expanded: list[str] = []
    for part in command:
        for token, value in mapping.items():
            part = part.replace(token, value)
        expanded.append(part)
    return expanded


def isolate_tree(repo: Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    td = tempfile.TemporaryDirectory(prefix="heatguard-drill-")
    _active_temps.append(td)
    dest = Path(td.name) / "repo"
    try:
        shutil.copytree(repo, dest, ignore=copy_ignore, symlinks=False)
    except OSError as exc:
        raise DrillError(f"copytree failed: {exc}") from exc
    return td, dest


def git_porcelain(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise DrillError(
            f"git status failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout}"
        )
    kept: list[str] = []
    for line in proc.stdout.splitlines():
        path = line[3:].split(" -> ")[-1]
        if path == "artifacts" or path.startswith("artifacts/"):
            continue
        kept.append(line)
    return "\n".join(kept)


def invoke_gate(
    command: Sequence[str],
    *,
    tree: Path,
    timeout: int = GATE_TIMEOUT_SEC,
) -> tuple[int, str]:
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    src = str(tree / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{existing}" if existing else src
    try:
        proc = subprocess.run(
            list(command),
            cwd=tree,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise DrillError(f"gate command not found: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + (exc.stderr or "")
        return 124, f"{out}\ngate timed out after {timeout}s"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def cleanup_temps() -> list[str]:
    errors: list[str] = []
    while _active_temps:
        td = _active_temps.pop()
        try:
            td.cleanup()
        except OSError as exc:
            errors.append(str(exc))
    return errors


def _install_signal_handlers() -> None:
    def handler(signum: int, _frame: object) -> None:
        errors = cleanup_temps()
        extra = f" cleanup errors: {errors}" if errors else ""
        raise SystemExit(f"drill interrupted by signal {signum}.{extra}")

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def run_case(
    case: Mapping[str, Any],
    *,
    repo: Path,
    python: str,
) -> dict[str, Any]:
    td, tree = isolate_tree(repo)
    started = time.perf_counter()
    try:
        target = tree / str(case["target"])
        apply_mutation(target, str(case["operation"]), case["payload"])
        command = expand_command(
            [str(part) for part in case["gate_command"]],
            python=python,
            tree=tree,
        )
        exit_code, output = invoke_gate(command, tree=tree)
        expected_exit = int(case["expected_exit_code"])
        expected_diag = str(case["expected_diagnostic"])
        outcome = score_gate(
            exit_code=exit_code,
            output=output,
            expected_exit_code=expected_exit,
            expected_diagnostic=expected_diag,
        )
        duration_ms = int(round((time.perf_counter() - started) * 1000))
        return {
            "id": case["id"],
            "gate": case["gate"],
            "mutation": {
                "target": case["target"],
                "operation": case["operation"],
                "payload": case["payload"],
            },
            "exit_code": exit_code,
            "matched_diagnostic": expected_diag in output,
            "duration_ms": duration_ms,
            "outcome": outcome,
            "message": outcome_message(str(case["id"]), outcome, expected_diag),
        }
    finally:
        try:
            td.cleanup()
        except OSError:
            pass
        if td in _active_temps:
            _active_temps.remove(td)


def markdown_summary(report: Mapping[str, Any], generated_at_utc: str) -> str:
    lines = [
        "# Guardrail deliberate-break drill",
        "",
        f"Generated: {generated_at_utc}",
        f"Result: {'PASS' if report['ok'] else 'FAIL'}",
        "",
        "## Gates covered",
        "",
    ]
    for gate in report["gates_covered"]:
        lines.append(f"- `{gate}`")
    lines.extend(["", "## Cases", ""])
    for case in report["cases"]:
        lines.append(
            f"- `{case['id']}` ({case['gate']}): **{case['outcome']}** "
            f"exit={case['exit_code']} matched_diagnostic={case['matched_diagnostic']} "
            f"duration_ms={case['duration_ms']}"
        )
        if case["outcome"] != "pass":
            lines.append(f"  - {case['message']}")
    lines.append("")
    return "\n".join(lines)


def run_drill(
    *,
    repo: Path,
    manifest_path: Path,
    python: str,
) -> dict[str, Any]:
    before = git_porcelain(repo)
    manifest = load_manifest(manifest_path)
    covered = [str(g) for g in manifest["gates_covered"]]
    missing_gates = [g for g in REQUIRED_GATES if g not in covered]
    if missing_gates:
        raise DrillError(f"manifest gates_covered missing required gates: {missing_gates}")
    case_gates = {str(case["gate"]) for case in manifest["cases"]}
    uncovered = [g for g in covered if g not in case_gates]
    if uncovered:
        raise DrillError(f"gates listed as covered have no case: {uncovered}")

    results: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        results.append(run_case(case, repo=repo, python=python))

    ok = all(row["outcome"] == "pass" for row in results)
    report = {
        "ok": ok,
        "gates_covered": covered,
        "cases": results,
    }

    after = git_porcelain(repo)
    if after != before:
        raise DrillError(
            "real working tree changed during the drill "
            f"(beyond artifacts/):\nbefore:\n{before}\nafter:\n{after}"
        )
    return report


def write_reports(report: Mapping[str, Any], output_dir: Path, generated_at_utc: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    dump(report, output_dir / "report.json")
    (output_dir / "summary.md").write_text(
        markdown_summary(report, generated_at_utc),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(ROOT), help="Real repository root")
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Committed mutations manifest",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT),
        help="Report directory (real tree; gitignored under artifacts/)",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo_root).resolve()
    _install_signal_handlers()
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        report = run_drill(
            repo=repo,
            manifest_path=Path(args.manifest),
            python=sys.executable,
        )
        write_reports(report, Path(args.output_dir), generated_at)
    except DrillError as exc:
        print(f"Guardrail drill FAILED: {exc}", file=sys.stderr)
        cleanup_errors = cleanup_temps()
        if cleanup_errors:
            print(f"cleanup errors: {cleanup_errors}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Guardrail drill FAILED: {exc}", file=sys.stderr)
        cleanup_errors = cleanup_temps()
        if cleanup_errors:
            print(f"cleanup errors: {cleanup_errors}", file=sys.stderr)
        return 1
    finally:
        leftover = cleanup_temps()
        if leftover:
            print(f"Guardrail drill FAILED: cleanup errors: {leftover}", file=sys.stderr)
            return 1

    print(f"Wrote {Path(args.output_dir) / 'report.json'}")
    print(f"Wrote {Path(args.output_dir) / 'summary.md'}")
    for case in report["cases"]:
        print(f"  {case['id']}: {case['outcome']}")
    if not report["ok"]:
        for case in report["cases"]:
            if case["outcome"] != "pass":
                print(case["message"], file=sys.stderr)
        return 1
    print("OK — every seeded violation tripped its gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
