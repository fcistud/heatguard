"""Resolve the repo-level ``data/`` directory regardless of working directory.

For an editable install (``pip install -e .``) ``__file__`` lives at
``<repo>/src/heatguard/_paths.py`` so the repo root is ``parents[2]``. An explicit
``HEATGUARD_DATA_DIR`` env var overrides everything (useful for packaged deploys).
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("HEATGUARD_DATA_DIR", _REPO_ROOT / "data"))
CACHE_DIR = DATA_DIR / "cache"


def data_file(name: str) -> Path:
    """Path to a file in ``data/`` (does not check existence)."""
    return DATA_DIR / name


def cache_file(name: str) -> Path:
    return CACHE_DIR / name
