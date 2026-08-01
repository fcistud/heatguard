#!/usr/bin/env python3
"""Alias for scripts/ci_version_drift.py (WO-008 naming)."""
from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("ci_version_drift.py")), run_name="__main__")
