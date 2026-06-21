#!/usr/bin/env python
"""Train the personal risk classifier from real cached Open-Meteo weather + PHS labels.

Usage (from repo root, with heatguard env active)::

    python scripts/train_risk_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heatguard.risk_model import train_and_save  # noqa: E402


def main() -> int:
    summary = train_and_save()
    print(f"Trained on {summary.rows} rows ({summary.positive_rate:.1%} elevated)")
    print(f"  in-sample accuracy: {summary.train_accuracy:.3f}")
    print(f"  saved -> {summary.model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
