#!/usr/bin/env python3
"""Write the synthetic integrator digest fixture (no production secrets).

Usage:
  python scripts/generate_api_key_digests.py
  python scripts/generate_api_key_digests.py --print-env
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "api_key_digests.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-env",
        action="store_true",
        help="Print HEATGUARD_API_KEY_* exports instead of writing the fixture.",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT / "src"))
    from heatguard.boundary.api_keys import ENV_DIGESTS, ENV_PEPPER, synthetic_bundle

    payload = synthetic_bundle()
    if args.print_env:
        bundle = json.dumps(payload["bundle"], separators=(",", ":"))
        print(f"export {ENV_PEPPER}={payload['pepper']!r}")
        print(f"export {ENV_DIGESTS}={bundle!r}")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
