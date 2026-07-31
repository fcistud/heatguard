#!/usr/bin/env python3
"""Capture or check HeatGuard golden-master reference artifacts.

Usage:
  python scripts/capture_golden_masters.py           # write tests/golden
  python scripts/capture_golden_masters.py --check   # regenerate + byte-compare
  python scripts/capture_golden_masters.py --idempotent  # two-temp equality

Requires the current Python 3.11 runtime with pinned numerics (see docs/TESTING.md).
Networking is disabled during capture — only committed data/cache files are used.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running without an editable install when PYTHONPATH includes src/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from heatguard import golden  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="byte-compare regenerate vs committed")
    p.add_argument(
        "--idempotent",
        action="store_true",
        help="assert two consecutive captures are byte-identical",
    )
    p.add_argument("--out", default=None, help="capture output directory")
    p.add_argument("--crew", type=int, default=100)
    p.add_argument("--sites", nargs="+", default=None)
    args = p.parse_args(argv)

    if args.idempotent:
        print("Checking capture idempotency …")
        golden.assert_capture_idempotent(sites=args.sites, crew=args.crew)
        print("OK — two consecutive captures are byte-identical.")
        return 0

    if args.check:
        print("Checking committed golden masters …")
        against = Path(args.out) if args.out else None
        diffs = golden.check_against_committed(
            committed=against, sites=args.sites, crew=args.crew
        )
        if diffs:
            print("GOLDEN MISMATCH:")
            for d in diffs:
                print(f"  {d}")
            return 1
        print("OK — byte-identical.")
        return 0

    out = Path(args.out) if args.out else None
    target = golden.capture_all(out_dir=out, sites=args.sites, crew=args.crew)
    print(f"Wrote golden masters to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
