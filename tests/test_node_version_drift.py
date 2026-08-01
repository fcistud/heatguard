"""Unit tests for Node version drift helper."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from heatguard._paths import _REPO_ROOT


def _load_drift():
    path = _REPO_ROOT / "scripts" / "ci_node_version_drift.py"
    spec = importlib.util.spec_from_file_location("ci_node_version_drift", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dockerfile_node_parses_web_build():
    drift = _load_drift()
    text = "FROM node:24-bookworm-slim AS web-build\nFROM python:3.11-slim AS runtime\n"
    assert drift.dockerfile_node(text) == "24"


def test_engines_node_parses():
    drift = _load_drift()
    assert drift.package_engines_node({"engines": {"node": ">=24 <25"}}) == "24"


def test_match_and_mismatch():
    drift = _load_drift()
    assert drift.dockerfile_node("FROM node:22-bookworm-slim AS web-build\n") == "22"
    assert drift.package_engines_node({"engines": {"node": "24.x"}}) == "24"
