#!/usr/bin/env python3
"""Assert Dockerfile runtime Python, CI Python, and pyproject requires-python agree.

Exit 0 on success. Exit 1 with all three values printed on drift.

Usage:
  python scripts/ci_version_drift.py --ci-python 3.12
  python scripts/check_python_version_drift.py --ci-python 3.12
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dockerfile_python(text: str) -> str:
    # Prefer the runtime stage FROM line (last python: image, or AS runtime).
    matches = re.findall(
        r"^FROM\s+python:([0-9]+\.[0-9]+)[^\s]*\s+AS\s+runtime",
        text,
        flags=re.MULTILINE,
    )
    if matches:
        return matches[-1]
    matches = re.findall(r"^FROM\s+python:([0-9]+\.[0-9]+)", text, flags=re.MULTILINE)
    if not matches:
        raise SystemExit("Could not parse python version from Dockerfile")
    return matches[-1]


def requires_python_floor(text: str) -> str:
    m = re.search(r'requires-python\s*=\s*["\']>=?\s*([0-9]+\.[0-9]+)', text)
    if not m:
        raise SystemExit("Could not parse requires-python from pyproject.toml")
    return m.group(1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ci-python", required=True, help="Major.minor used by this CI job")
    args = p.parse_args(argv)

    docker_py = dockerfile_python((ROOT / "Dockerfile").read_text())
    floor = requires_python_floor((ROOT / "pyproject.toml").read_text())
    ci_py = args.ci_python

    def majmin(v: str) -> tuple[int, int]:
        a, b, *_ = (v + ".0").split(".")
        return int(a), int(b)

    ok = True
    messages: list[str] = []
    if majmin(docker_py) != majmin(ci_py):
        ok = False
        messages.append(
            f"Dockerfile runtime python ({docker_py}) != CI interpreter ({ci_py})"
        )
    if majmin(floor) != majmin(ci_py):
        ok = False
        messages.append(
            f"pyproject requires-python floor ({floor}) != CI interpreter ({ci_py})"
        )
    if majmin(docker_py) != majmin(floor):
        ok = False
        messages.append(
            f"Dockerfile runtime python ({docker_py}) != pyproject floor ({floor})"
        )

    print("version-drift check:")
    print(f"  Dockerfile runtime : {docker_py}")
    print(f"  pyproject floor    : >={floor}")
    print(f"  CI interpreter     : {ci_py}")
    if not ok:
        print("DRIFT DETECTED:")
        for m in messages:
            print(f"  - {m}")
        return 1
    print("OK — interpreters agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
