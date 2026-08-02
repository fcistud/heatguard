#!/usr/bin/env python3
"""Fail if any Dockerfile FROM line lacks an immutable @sha256: digest pin.

Usage:
  python scripts/check_dockerfile_digests.py
  python scripts/check_dockerfile_digests.py path/to/Dockerfile
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROM_RE = re.compile(r"^\s*FROM\s+(\S+)", re.IGNORECASE)
DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}\b", re.IGNORECASE)


def check(text: str) -> list[str]:
    errors: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = FROM_RE.match(line)
        if not m:
            continue
        ref = m.group(1)
        # Scratch / stage aliases without a registry image are rare; we require
        # every FROM that looks like an external image to carry a digest.
        if ref.startswith("--"):
            # FROM --platform=... image
            parts = stripped.split()
            ref = parts[2] if len(parts) >= 3 else ref
        if not DIGEST_RE.search(ref):
            errors.append(f"line {i}: FROM without @sha256 digest: {stripped}")
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "dockerfile",
        nargs="?",
        default=str(ROOT / "Dockerfile"),
        help="Path to Dockerfile (default: repo root)",
    )
    args = p.parse_args(argv)
    path = Path(args.dockerfile)
    errors = check(path.read_text(encoding="utf-8"))
    if errors:
        print(f"Dockerfile digest lint FAILED ({path}):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK — all FROM lines in {path} are digest-pinned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
