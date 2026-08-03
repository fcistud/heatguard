#!/usr/bin/env python3
"""Assert Dockerfile runtime Python, CI Python, and pyproject requires-python agree.

Also guards ``.github/workflows/ci.yml``:
  - top-level ``CANONICAL_PYTHON`` matches ``--ci-python``
  - any ``strategy.matrix`` ``python-version`` literal lists match ``--ci-python``
    (``env.*`` is illegal in matrix; literals can drift if reintroduced)

Exit 0 on success. Exit 1 with all values printed on drift.

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
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


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


def workflow_canonical_python(text: str) -> str:
    m = re.search(
        r"(?m)^[ \t]*CANONICAL_PYTHON:\s*[\"']?([0-9]+\.[0-9]+)[\"']?\s*$",
        text,
    )
    if not m:
        raise SystemExit("Could not parse CANONICAL_PYTHON from ci.yml")
    return m.group(1)


def workflow_matrix_python_versions(text: str) -> list[str]:
    """Literal major.minor values under ``python-version`` YAML lists.

    Captures inline ``python-version: ["3.12"]`` and multi-line ``- "3.12"``
    lists. Skips expression-only forms (``${{ ... }}``) used in job steps.
    """
    found: list[str] = []

    for m in re.finditer(r"python-version:\s*\[([^\]]*)\]", text):
        body = m.group(1)
        if "${{" in body:
            continue
        found.extend(re.findall(r"[\"']([0-9]+\.[0-9]+)[\"']", body))

    for m in re.finditer(
        r"(?ms)^[ \t]*python-version:\s*\n((?:^[ \t]+-[ \t]*.+\n)+)",
        text,
    ):
        block = m.group(1)
        if "${{" in block:
            continue
        found.extend(re.findall(r"[\"']([0-9]+\.[0-9]+)[\"']", block))
        # Allow bare YAML numbers: - 3.12
        found.extend(re.findall(r"^[ \t]+-[ \t]*([0-9]+\.[0-9]+)[ \t]*$", block, re.M))

    seen: set[str] = set()
    out: list[str] = []
    for v in found:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def majmin(v: str) -> tuple[int, int]:
    a, b, *_ = (v + ".0").split(".")
    return int(a), int(b)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ci-python", required=True, help="Major.minor used by this CI job")
    args = p.parse_args(argv)

    docker_py = dockerfile_python((ROOT / "Dockerfile").read_text())
    floor = requires_python_floor((ROOT / "pyproject.toml").read_text())
    workflow = CI_WORKFLOW.read_text()
    canonical = workflow_canonical_python(workflow)
    matrix_versions = workflow_matrix_python_versions(workflow)
    ci_py = args.ci_python

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
    if majmin(canonical) != majmin(ci_py):
        ok = False
        messages.append(
            f"ci.yml CANONICAL_PYTHON ({canonical}) != --ci-python ({ci_py})"
        )
    for mv in matrix_versions:
        if majmin(mv) != majmin(ci_py):
            ok = False
            messages.append(
                f"ci.yml strategy.matrix python-version ({mv}) != CI interpreter ({ci_py})"
            )

    print("version-drift check:")
    print(f"  Dockerfile runtime : {docker_py}")
    print(f"  pyproject floor    : >={floor}")
    print(f"  CI interpreter     : {ci_py}")
    print(f"  CANONICAL_PYTHON   : {canonical}")
    print(
        "  matrix python-version literals: "
        f"{', '.join(matrix_versions) if matrix_versions else '(none)'}"
    )
    if not ok:
        print("DRIFT DETECTED:")
        for m in messages:
            print(f"  - {m}")
        return 1
    print("OK — interpreters agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
