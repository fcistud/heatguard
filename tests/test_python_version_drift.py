"""Unit tests for Python interpreter version drift helper."""
from __future__ import annotations

import importlib.util

from heatguard._paths import _REPO_ROOT


def _load_drift():
    path = _REPO_ROOT / "scripts" / "ci_version_drift.py"
    spec = importlib.util.spec_from_file_location("ci_version_drift", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dockerfile_python_prefers_runtime_stage():
    drift = _load_drift()
    text = "FROM python:3.11-slim AS builder\nFROM python:3.12-slim AS runtime\n"
    assert drift.dockerfile_python(text) == "3.12"


def test_requires_python_floor():
    drift = _load_drift()
    assert drift.requires_python_floor('requires-python = ">=3.12"\n') == "3.12"


def test_workflow_canonical_python():
    drift = _load_drift()
    text = 'env:\n  CANONICAL_PYTHON: "3.12"\n  CANONICAL_NODE: "24"\n'
    assert drift.workflow_canonical_python(text) == "3.12"


def test_matrix_inline_literals():
    drift = _load_drift()
    text = 'matrix:\n  python-version: ["3.12", "3.13"]\n'
    assert drift.workflow_matrix_python_versions(text) == ["3.12", "3.13"]


def test_matrix_multiline_literals():
    drift = _load_drift()
    text = "matrix:\n  python-version:\n    - \"3.12\"\n    - 3.13\n"
    assert drift.workflow_matrix_python_versions(text) == ["3.12", "3.13"]


def test_matrix_skips_env_expressions():
    drift = _load_drift()
    text = (
        "steps:\n"
        "  - uses: actions/setup-python@v5\n"
        "    with:\n"
        "      python-version: ${{ env.CANONICAL_PYTHON }}\n"
        'matrix:\n  python-version: ["${{ env.CANONICAL_PYTHON }}"]\n'
    )
    assert drift.workflow_matrix_python_versions(text) == []


def test_committed_workflow_has_no_matrix_literal_drift():
    drift = _load_drift()
    workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    canonical = drift.workflow_canonical_python(workflow)
    assert canonical == "3.12"
    for ver in drift.workflow_matrix_python_versions(workflow):
        assert drift.majmin(ver) == drift.majmin(canonical)
