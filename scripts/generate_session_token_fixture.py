#!/usr/bin/env python3
"""Write the synthetic session-token fixture (no production secrets).

Usage:
  python scripts/generate_session_token_fixture.py
  python scripts/generate_session_token_fixture.py --print-env
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "session_tokens.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-env",
        action="store_true",
        help="Print HEATGUARD_SESSION_* / IDENTITY_SNAPSHOT exports.",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT / "src"))
    from heatguard.boundary.session_tokens import (
        ENV_KID,
        ENV_SIGNING_SECRET,
        ENV_SNAPSHOT,
        synthetic_session_fixture,
    )

    payload = synthetic_session_fixture()
    if args.print_env:
        snapshot = json.dumps(payload["principals"], separators=(",", ":"))
        print(f"export {ENV_SIGNING_SECRET}={payload['signing_secret']!r}")
        print(f"export {ENV_KID}={payload['kid']!r}")
        print(f"export {ENV_SNAPSHOT}={snapshot!r}")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
