"""Static check: tooling scripts' third-party imports are declared in pyproject."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import tomllib

from heatguard._paths import _REPO_ROOT

# stdlib / local modules that are not PyPI distributions
_SKIP = {
    "sys",
    "os",
    "pathlib",
    "re",
    "json",
    "math",
    "warnings",
    "datetime",
    "typing",
    "collections",
    "functools",
    "itertools",
    "dataclasses",
    "argparse",
    "heatguard",
    "__future__",
}

# import name → distribution name when they differ
_DIST = {
    "pptx": "python-pptx",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "nbformat": "nbformat",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
}


def _declared_dists() -> set[str]:
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    deps = set()
    for raw in data["project"].get("dependencies", []):
        deps.add(re.split(r"[<>=!\[]", raw, maxsplit=1)[0].strip().lower())
    for extra_deps in data["project"].get("optional-dependencies", {}).values():
        for raw in extra_deps:
            deps.add(re.split(r"[<>=!\[]", raw, maxsplit=1)[0].strip().lower())
    return deps


def _imports_from_source(src: str) -> set[str]:
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _cell_imports_from_builder(src: str) -> set[str]:
    """Pull imports from string literals passed to ``code(...)`` in the notebook builder."""
    names: set[str] = set()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "code" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                try:
                    names |= _imports_from_source(arg.value)
                except SyntaxError:
                    pass
    return names


def test_deck_and_notebook_imports_are_declared():
    declared = _declared_dists()
    deck = (_REPO_ROOT / "scripts" / "build_deck.py").read_text()
    nb = (_REPO_ROOT / "notebooks" / "build_validation_notebook.py").read_text()
    imports = _imports_from_source(deck) | _imports_from_source(nb) | _cell_imports_from_builder(nb)
    missing: list[str] = []
    for name in sorted(imports):
        if name in _SKIP or name.startswith("_"):
            continue
        dist = _DIST.get(name, name).lower()
        if dist not in declared and name.lower() not in declared:
            missing.append(f"{name} (dist={dist})")
    assert not missing, f"Undeclared third-party imports: {missing}"
