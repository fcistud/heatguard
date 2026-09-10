"""CI workflow meta-gate: guardrail jobs cannot be quietly removed (WO-016)."""
from __future__ import annotations

import copy
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from heatguard._paths import _REPO_ROOT

REPO = _REPO_ROOT
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

REQUIRED_GUARDRAIL_JOBS = (
    "arch-contract",
    "openapi-contract",
    "guardrail-copy-lint",
    "legal-lane-regression",
    "guardrail-drill",
    "identity-db-ceiling",
)

SHA_USES_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$"
)


def load_workflow(path: Path = WORKFLOW) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path}: workflow is not a mapping")
    return payload


def _iter_uses(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        uses = node.get("uses")
        if isinstance(uses, str):
            found.append(uses.split("#", 1)[0].strip())
        for value in node.values():
            found.extend(_iter_uses(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_iter_uses(item))
    return found


def collect_errors(workflow: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return ["workflow has no jobs mapping"]
    for name in REQUIRED_GUARDRAIL_JOBS:
        if name not in jobs:
            errors.append(f"missing guardrail job: {name}")
            continue
        job = jobs[name]
        if not isinstance(job, dict):
            errors.append(f"{name}: job is not a mapping")
            continue
        if job.get("continue-on-error"):
            errors.append(f"{name}: continue-on-error would make the gate non-blocking")
        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{name}: missing steps")
            continue
        run_steps = [
            step
            for step in steps
            if isinstance(step, dict) and isinstance(step.get("run"), str)
        ]
        if not run_steps:
            errors.append(f"{name}: missing failure-propagating run step")
        for step in run_steps:
            if step.get("continue-on-error"):
                errors.append(
                    f"{name}: run step has continue-on-error and would not block merge"
                )
        for uses in _iter_uses(job):
            if not SHA_USES_RE.match(uses):
                errors.append(f"{name}: action is not SHA-pinned: {uses}")
    for uses in _iter_uses(workflow):
        if not SHA_USES_RE.match(uses):
            errors.append(f"workflow action is not SHA-pinned: {uses}")
    perms = workflow.get("permissions")
    if isinstance(perms, dict) and perms.get("contents") not in {"read", None}:
        if perms.get("contents") != "read":
            errors.append("workflow permissions.contents must stay 'read'")
    return sorted(set(errors))


def test_committed_workflow_has_guardrail_jobs() -> None:
    errors = collect_errors(load_workflow())
    assert errors == [], errors


def test_missing_job_fails() -> None:
    workflow = load_workflow()
    jobs = dict(workflow["jobs"])
    jobs.pop("arch-contract")
    mutated = {**workflow, "jobs": jobs}
    errors = collect_errors(mutated)
    assert any("arch-contract" in err for err in errors)


def test_removed_run_step_fails() -> None:
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"]["arch-contract"]["steps"] = [
        {"uses": "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"}
    ]
    errors = collect_errors(workflow)
    assert any("run step" in err for err in errors)


def test_continue_on_error_rejected() -> None:
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"]["guardrail-drill"]["continue-on-error"] = True
    errors = collect_errors(workflow)
    assert any("continue-on-error" in err for err in errors)


def test_tag_pinned_action_rejected() -> None:
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"]["identity-db-ceiling"]["steps"].insert(
        0, {"uses": "actions/checkout@v4"}
    )
    errors = collect_errors(workflow)
    assert any("not SHA-pinned" in err and "checkout@v4" in err for err in errors)


def test_meta_gate_subprocess() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(Path(__file__)), "-q", "--tb=no", "-k", "committed_workflow"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
