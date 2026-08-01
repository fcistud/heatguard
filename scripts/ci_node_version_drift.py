#!/usr/bin/env python3
"""Assert Dockerfile web-build Node, CI setup-node, and package.json engines agree.

Usage:
  python scripts/ci_node_version_drift.py --ci-node 24
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dockerfile_node(text: str) -> str:
    m = re.search(
        r"^FROM\s+node:([0-9]+)[^\s]*\s+AS\s+web-build",
        text,
        flags=re.MULTILINE,
    )
    if not m:
        m = re.search(r"^FROM\s+node:([0-9]+)", text, flags=re.MULTILINE)
    if not m:
        raise SystemExit("Could not parse Node version from Dockerfile web-build stage")
    return m.group(1)


def package_engines_node(pkg: dict) -> str:
    engines = pkg.get("engines") or {}
    node = str(engines.get("node", ""))
    m = re.search(r"([0-9]+)", node)
    if not m:
        raise SystemExit("Could not parse engines.node from web/package.json")
    return m.group(1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ci-node", required=True, help="Major Node version used by CI")
    args = p.parse_args(argv)

    docker_n = dockerfile_node((ROOT / "Dockerfile").read_text())
    pkg = json.loads((ROOT / "web" / "package.json").read_text())
    eng_n = package_engines_node(pkg)
    ci_n = str(args.ci_node).split(".")[0]

    print("node-version-drift check:")
    print(f"  Dockerfile web-build : {docker_n}")
    print(f"  package.json engines : {eng_n}")
    print(f"  CI setup-node        : {ci_n}")

    if docker_n == eng_n == ci_n:
        print("OK — Node majors agree.")
        return 0
    print("DRIFT DETECTED — Dockerfile / engines / CI Node majors disagree.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
