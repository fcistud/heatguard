#!/usr/bin/env python3
"""Build the deterministic offline identity SQLite fixture (WO-017).

Reads tests/fixtures/identity/seed_users.json and writes
tests/fixtures/identity/heatguard-identity-test.db.

Synthetic principals only — no production usernames or credentials.

Usage:
  uv run python scripts/build_identity_fixture.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "tests" / "fixtures" / "identity" / "seed_users.json"
OUT = ROOT / "tests" / "fixtures" / "identity" / "heatguard-identity-test.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        type=Path,
        default=SEED,
        help="JSON seed document (default: tests/fixtures/identity/seed_users.json)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT,
        help="SQLite destination (default: tests/fixtures/identity/heatguard-identity-test.db)",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT / "src"))
    from heatguard.identity.schema import load_seed_document, write_seeded_database

    rows = load_seed_document(args.seed)
    dest = write_seeded_database(args.out, rows)
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
