#!/usr/bin/env python3
"""Architecture layering gate (WO-011).

Runs ``lint-imports``, parses the report, and diffs detected violations against
``infra/architecture/layering_baseline.json``. New violations and stale baseline
entries both fail. Forbidden contracts cannot be baselined.

Usage:
  uv run python scripts/check_layering.py
  uv run python scripts/check_layering.py --root /path/to/repo
  uv run python scripts/check_layering.py --report-file tests/fixtures/layering/clean.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "infra" / "architecture" / "layering_baseline.json"
DEFAULT_CONTRACTS = ROOT / ".importlinter"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
NOT_ALLOWED_RE = re.compile(
    r"^(\S+) is not allowed to import (\S+):?\s*$"
)
UNDECLARED_ITEM_RE = re.compile(r"^-\s+(\S+)\s*$")
CONTRACT_RESULT_RE = re.compile(r"^(.+?)\s+(KEPT|BROKEN)(?:\s|\(|$)")
UNDECLARED_HEADER = "the following modules are not listed as layers:"
UNASSIGNED_IMPORTED = "(unassigned)"

REQUIRED_BASELINE_KEYS = (
    "importer",
    "imported",
    "contract",
    "reason",
    "owner",
    "dated_at",
)

FORBIDDEN_CONTRACT_MARKERS = (
    "types leaf purity",
    "legal_precedence never imports service or api",
)


@dataclass(frozen=True)
class Violation:
    importer: str
    imported: str
    contract: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.importer, self.imported, self.contract)


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    broken: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def _repo_root() -> Path:
    return ROOT


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_contracts_file(path: Path) -> dict[str, str]:
    """Return ``{contract_id: display_name}`` from ``.importlinter``."""
    if not path.is_file():
        raise FileNotFoundError(f"{path}: contracts file not found")
    names: dict[str, str] = {}
    current_id: str | None = None
    header_re = re.compile(r"^\[importlinter:contract:([^\]]+)\]\s*$")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        match = header_re.match(line)
        if match:
            current_id = match.group(1)
            continue
        if current_id and line.startswith("name"):
            _, _, value = line.partition("=")
            names[current_id] = value.strip()
            current_id = None
    if not names:
        raise ValueError(f"{path}: no import-linter contracts found")
    return names


def is_forbidden_contract(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in FORBIDDEN_CONTRACT_MARKERS)


def parse_lint_imports_report(
    text: str, *, known_names: Iterable[str]
) -> tuple[list[Violation], list[str], list[str], list[str]]:
    """Parse lint-imports stdout into violations plus kept/broken names.

    Returns ``(violations, kept, broken, parse_errors)``. Unrecognized BROKEN
    output is a parse error so the gate never fail-opens.
    """
    known = list(known_names)
    known_by_lower = {name.lower(): name for name in known}
    violations: list[Violation] = []
    kept: list[str] = []
    broken: list[str] = []
    parse_errors: list[str] = []
    current_contract: str | None = None
    in_undeclared = False
    saw_broken_heading = False

    def _resolve_contract(label: str) -> str | None:
        if label in known_by_lower:
            return known_by_lower[label]
        for name in known:
            if label == name.lower() or name.lower().startswith(label):
                return name
        return None

    for raw in _strip_ansi(text).splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            # Keep undeclared-list state across the blank line after the header.
            continue
        if stripped.startswith("-") and set(stripped) <= {"-", " "}:
            continue

        lower = stripped.lower()
        if lower == "broken contracts":
            saw_broken_heading = True
            current_contract = None
            in_undeclared = False
            continue
        if lower == UNDECLARED_HEADER:
            in_undeclared = True
            continue
        if in_undeclared:
            item = UNDECLARED_ITEM_RE.match(stripped)
            if item and current_contract:
                violations.append(
                    Violation(
                        importer=item.group(1),
                        imported=UNASSIGNED_IMPORTED,
                        contract=current_contract,
                    )
                )
                continue
            if stripped.startswith("("):
                in_undeclared = False
                continue

        result = CONTRACT_RESULT_RE.match(stripped)
        if result and not saw_broken_heading:
            label = result.group(1).strip()
            status = result.group(2)
            resolved = _resolve_contract(label.lower())
            if resolved:
                if status == "KEPT":
                    kept.append(resolved)
                else:
                    broken.append(resolved)
                continue

        if saw_broken_heading:
            resolved = _resolve_contract(lower)
            if resolved:
                current_contract = resolved
                in_undeclared = False
                continue

        allowed = NOT_ALLOWED_RE.match(stripped)
        if allowed:
            if current_contract is None and len(broken) == 1:
                current_contract = broken[0]
            if current_contract is None:
                parse_errors.append(
                    f"violation without contract context: {stripped}"
                )
                continue
            violations.append(
                Violation(
                    importer=allowed.group(1),
                    imported=allowed.group(2).rstrip(":"),
                    contract=current_contract,
                )
            )

    if broken and not violations:
        parse_errors.append(
            "lint-imports reported BROKEN contracts but no parseable "
            "violations were found (unrecognized output — refusing to fail open)"
        )
    return violations, kept, broken, parse_errors


def load_baseline(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return [], [f"{path}: baseline file not found"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"{path}: malformed JSON: {exc}"]
    except OSError as exc:
        return [], [f"{path}: cannot read file: {exc}"]

    if not isinstance(raw, dict):
        return [], [f"{path}: baseline must be a JSON object"]
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return [], [f"{path}: missing 'entries' list"]

    cleaned: list[dict[str, str]] = []
    for idx, entry in enumerate(entries):
        loc = f"{path}:entries[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"{loc}: entry must be an object")
            continue
        missing = [key for key in REQUIRED_BASELINE_KEYS if not entry.get(key)]
        if missing:
            errors.append(f"{loc}: missing required fields {missing}")
            continue
        cleaned.append({key: str(entry[key]) for key in REQUIRED_BASELINE_KEYS})
    return cleaned, errors


def validate_baseline_schema(entries: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        key = (entry["importer"], entry["imported"], entry["contract"])
        if key in seen:
            errors.append(f"duplicate baseline entry: {key}")
        seen.add(key)
        if is_forbidden_contract(entry["contract"]):
            errors.append(
                f"forbidden contract {entry['contract']!r} must have an empty "
                "baseline; delete this entry"
            )
    return errors


def diff_ratchet(
    live: Iterable[Violation],
    baseline: Iterable[dict[str, str]],
) -> list[str]:
    live_map = {item.key: item for item in live}
    base_map = {
        (row["importer"], row["imported"], row["contract"]): row
        for row in baseline
    }
    errors: list[str] = []
    for key, violation in sorted(live_map.items()):
        if is_forbidden_contract(violation.contract):
            errors.append(
                f"{violation.contract}: new forbidden violation "
                f"{violation.importer} -> {violation.imported} "
                "(forbidden contracts cannot be baselined)"
            )
            continue
        if key not in base_map:
            errors.append(
                f"{violation.contract}: new violation not in baseline: "
                f"{violation.importer} -> {violation.imported}"
            )
    for key, row in sorted(base_map.items()):
        if key not in live_map:
            errors.append(
                f"{row['contract']}: stale baseline entry — delete "
                f"importer={row['importer']!r} imported={row['imported']!r} "
                f"contract={row['contract']!r}"
            )
    return errors


def lint_imports_command() -> list[str]:
    sibling = Path(sys.executable).resolve().parent / "lint-imports"
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return [str(sibling)]
    found = shutil.which("lint-imports")
    if found:
        return [found]
    raise FileNotFoundError(
        "lint-imports not found; install the 'dev' extra "
        "(import-linter>=2.13,<2.14) and re-run via `uv run`."
    )


def run_lint_imports(root: Path) -> tuple[int, str, str]:
    src = root / "src"
    if not (root / ".importlinter").is_file():
        raise FileNotFoundError(
            f"{root / '.importlinter'}: contracts file missing "
            "(run this from a HeatGuard checkout)."
        )
    if not (src / "heatguard").is_dir():
        raise FileNotFoundError(
            f"{src / 'heatguard'}: package tree missing "
            "(is this a HeatGuard checkout?)"
        )
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{src}{os.pathsep}{existing}" if existing else str(src)
    )
    proc = subprocess.run(
        lint_imports_command(),
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def evaluate(
    *,
    report_text: str,
    returncode: int,
    baseline_path: Path,
    contracts_path: Path,
) -> CheckResult:
    result = CheckResult()
    try:
        names = parse_contracts_file(contracts_path)
    except (OSError, ValueError) as exc:
        result.fail(str(exc))
        return result

    if returncode not in {0, 1}:
        result.fail(
            f"lint-imports exited {returncode} (expected 0 or 1). "
            "Install import-linter from the 'dev' extra."
        )
        return result

    combined = report_text
    lowered = _strip_ansi(combined).lower()
    if "is not configured correctly" in lowered or "could not run" in lowered:
        result.fail("lint-imports could not run: invalid contract configuration")
        return result

    violations, kept, broken, parse_errors = parse_lint_imports_report(
        combined, known_names=names.values()
    )
    result.violations = violations
    result.kept = kept
    result.broken = broken
    for err in parse_errors:
        result.fail(err)
    if parse_errors:
        return result

    entries, load_errors = load_baseline(baseline_path)
    for err in load_errors:
        result.fail(err)
    if load_errors:
        return result
    for err in validate_baseline_schema(entries):
        result.fail(err)
    for err in diff_ratchet(violations, entries):
        result.fail(err)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(_repo_root()),
        help="Repository root containing .importlinter and src/heatguard",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="Baseline JSON (default: <root>/infra/architecture/layering_baseline.json)",
    )
    parser.add_argument(
        "--contracts",
        default=None,
        help="Contracts file (default: <root>/.importlinter)",
    )
    parser.add_argument(
        "--report-file",
        default=None,
        help="Parse a saved lint-imports report instead of invoking lint-imports",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"Layering check FAILED:\n  - {root}: repository root is not a directory")
        return 1

    contracts = Path(args.contracts) if args.contracts else root / ".importlinter"
    baseline = (
        Path(args.baseline)
        if args.baseline
        else root / "infra" / "architecture" / "layering_baseline.json"
    )

    try:
        if args.report_file:
            report_path = Path(args.report_file)
            text = report_path.read_text(encoding="utf-8")
            returncode = 1 if "BROKEN" in text else 0
        else:
            returncode, stdout, stderr = run_lint_imports(root)
            text = stdout if stdout.strip() else stderr
            if stderr.strip() and "BROKEN" not in stdout and returncode not in {0, 1}:
                text = f"{stdout}\n{stderr}"
    except FileNotFoundError as exc:
        print(f"Layering check FAILED:\n  - {exc}")
        return 1
    except OSError as exc:
        print(f"Layering check FAILED:\n  - cannot invoke lint-imports: {exc}")
        return 1

    result = evaluate(
        report_text=text,
        returncode=returncode,
        baseline_path=baseline,
        contracts_path=contracts,
    )
    if result.errors:
        print("Layering check FAILED:")
        for err in result.errors:
            print(f"  - {err}")
        return 1

    print(
        f"OK — layering contracts match baseline "
        f"({len(result.violations)} tolerated layers violation(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
