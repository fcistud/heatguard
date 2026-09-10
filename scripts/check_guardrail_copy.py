#!/usr/bin/env python3
"""Guardrail copy-lint (WO-013).

Parses prohibited and approved phrases from ``docs/SCOPE_GUARDRAIL.md``
Appendix A and scans application surfaces. An empty or missing phrase list
is a hard failure — never a pass.

Matching is within-line only: a prohibited phrase split across two source
lines by a formatter will not match. That limitation is intentional so the
lint stays a line-oriented reporter (file:line:phrase).

Usage:
  uv run python scripts/check_guardrail_copy.py
  uv run python scripts/check_guardrail_copy.py --root /path/to/repo
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GUARDRAIL_REL = Path("docs") / "SCOPE_GUARDRAIL.md"
APPENDIX_HEADING_PREFIX = "## Appendix A"
PROHIBITED_HEADING = "### Prohibited phrasebook"
APPROVED_HEADING = "### Approved phrasebook"

# Explicit application surfaces (WO-013). data/policy is source material and
# is intentionally absent from this list.
INCLUDE_PATHS = (
    "web/src",
    "landing",
    "website",
    "streamlit_app.py",
    "src/heatguard",
)

SKIP_DIR_NAMES = frozenset(
    {".git", "node_modules", "dist", "__pycache__", ".venv", ".tox"}
)
SKIP_FILE_NAMES = frozenset(
    {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "uv.lock"}
)
BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".pdf",
        ".zip",
        ".gz",
        ".pyc",
        ".so",
        ".dylib",
        ".bin",
        ".map",
    }
)

# Path → one-line justification. Production surfaces must never appear here.
EXEMPTIONS: tuple[tuple[str, str], ...] = (
    (
        "docs/SCOPE_GUARDRAIL.md",
        "Appendix A is the phrasebook source of truth and must quote prohibited wording",
    ),
    (
        "tests/fixtures/copy/",
        "copy-lint fixtures deliberately contain prohibited phrases to prove the gate",
    ),
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+")
_LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
_OPENING_QUOTE_RE = re.compile(r'^[“"‘\'](.+?)[”"’\']', re.DOTALL)
_EMPHASIS_RE = re.compile(r"[*_~`]+")
_WHITESPACE_RE = re.compile(r"\s+")
_QUOTE_DASH_TRANS = str.maketrans(
    {
        chr(0x2018): chr(39),
        chr(0x2019): chr(39),
        chr(0x201A): chr(39),
        chr(0x201B): chr(39),
        chr(0x2032): chr(39),
        chr(0x201C): chr(34),
        chr(0x201D): chr(34),
        chr(0x201E): chr(34),
        chr(0x201F): chr(34),
        chr(0x2033): chr(34),
        chr(0x2010): "-",
        chr(0x2011): "-",
        chr(0x2012): "-",
        chr(0x2013): "-",
        chr(0x2014): "-",
        chr(0x2212): "-",
    }
)


@dataclass(frozen=True, slots=True)
class PhraseLists:
    prohibited: tuple[str, ...]
    approved: tuple[str, ...]


@dataclass
class LintResult:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def normalize(text: str) -> str:
    """Case, emphasis, unicode quotes/dashes, then whitespace collapse."""
    stripped = _EMPHASIS_RE.sub("", text)
    translated = stripped.translate(_QUOTE_DASH_TRANS)
    collapsed = _WHITESPACE_RE.sub(" ", translated).strip()
    return collapsed.lower()


def _iter_unfenced_lines(text: str) -> list[tuple[int, str]]:
    """Yield 1-based (lineno, line) skipping fenced code blocks."""
    rows: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        rows.append((lineno, line))
    return rows


def _phrase_from_list_item(body: str) -> str:
    """Prefer the quoted span so parenthetical notes are not part of the phrase."""
    text = body.strip()
    quoted = _OPENING_QUOTE_RE.match(text)
    if quoted:
        return quoted.group(1).strip()
    return text


def parse_appendix_a(markdown: str) -> PhraseLists:
    """Extract phrase lists from Appendix A. Raises ValueError on fail-closed paths."""
    lines = _iter_unfenced_lines(markdown)
    appendix_at: int | None = None
    for idx, (_lineno, line) in enumerate(lines):
        if line.startswith(APPENDIX_HEADING_PREFIX):
            appendix_at = idx
            break
    if appendix_at is None:
        raise ValueError(
            "Appendix A heading not found "
            f"(expected a line starting with {APPENDIX_HEADING_PREFIX!r})"
        )

    def _collect(heading: str) -> tuple[str, ...]:
        start: int | None = None
        for idx, (_lineno, line) in enumerate(lines[appendix_at:], start=appendix_at):
            if line.startswith(heading):
                start = idx
                break
        if start is None:
            raise ValueError(f"Appendix A subsection missing: {heading}")
        phrases: list[str] = []
        for _lineno, line in lines[start + 1 :]:
            if _HEADING_RE.match(line):
                break
            item = _LIST_ITEM_RE.match(line)
            if not item:
                continue
            phrase = _phrase_from_list_item(item.group(1))
            if phrase:
                phrases.append(phrase)
        if not phrases:
            raise ValueError(f"Appendix A subsection empty: {heading}")
        return tuple(phrases)

    return PhraseLists(
        prohibited=_collect(PROHIBITED_HEADING),
        approved=_collect(APPROVED_HEADING),
    )


def load_phrase_lists(guardrail_path: Path) -> PhraseLists:
    if not guardrail_path.is_file():
        raise ValueError(f"{guardrail_path}: guardrail document not found")
    try:
        text = guardrail_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{guardrail_path}: cannot read file: {exc}") from exc
    return parse_appendix_a(text)


def is_exempt(rel_posix: str) -> bool:
    for prefix, _reason in EXEMPTIONS:
        trimmed = prefix.rstrip("/")
        if rel_posix == trimmed or rel_posix.startswith(trimmed + "/"):
            return True
    return False


def exemption_reasons() -> tuple[tuple[str, str], ...]:
    return EXEMPTIONS


def discover_surfaces(root: Path) -> list[Path]:
    """Walk include paths; skip denylisted dirs, lockfiles, and binary suffixes."""
    root_resolved = root.resolve()
    found: list[Path] = []
    for rel in INCLUDE_PATHS:
        target = (root / rel).resolve()
        if not _is_within_root(target, root_resolved):
            raise ValueError(f"scan path escapes repository root: {rel}")
        if not target.exists():
            continue
        if target.is_file():
            found.append(target)
            continue
        if not target.is_dir():
            raise ValueError(f"{rel}: include root is not a readable directory")
        for path in target.rglob("*"):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if not path.is_file():
                continue
            if path.name in SKIP_FILE_NAMES:
                continue
            if path.suffix.lower() in BINARY_SUFFIXES:
                continue
            if not _is_within_root(path, root_resolved):
                raise ValueError(f"scan path escapes repository root: {path}")
            found.append(path)
    return sorted(found)


def find_phrase_on_line(line: str, phrases: tuple[str, ...]) -> str | None:
    """Return the first prohibited phrase found on this line, else None.

    Matching is within-line only; phrases split by a line break do not match.
    """
    haystack = normalize(line)
    if not haystack:
        return None
    for phrase in phrases:
        needle = normalize(phrase)
        if needle and needle in haystack:
            return phrase
    return None


def scan_text(text: str, phrases: tuple[str, ...]) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        matched = find_phrase_on_line(line, phrases)
        if matched is not None:
            hits.append((lineno, matched))
    return hits


def lint_tree(root: Path, *, guardrail_path: Path | None = None) -> LintResult:
    result = LintResult()
    root_resolved = root.resolve()
    if not root.is_dir():
        result.fail(f"{root}: repository root is not a directory")
        return result

    source = guardrail_path or (root / GUARDRAIL_REL)
    try:
        if not _is_within_root(source, root_resolved) and guardrail_path is None:
            result.fail(f"{source}: guardrail path escapes repository root")
            return result
        phrases = load_phrase_lists(source)
    except ValueError as exc:
        result.fail(str(exc))
        return result

    try:
        files = discover_surfaces(root)
    except ValueError as exc:
        result.fail(str(exc))
        return result

    for path in files:
        rel = path.resolve().relative_to(root_resolved).as_posix()
        if is_exempt(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            result.fail(f"{rel}: cannot read file: {exc}")
            continue
        for lineno, phrase in scan_text(text, phrases.prohibited):
            result.fail(f"{rel}:{lineno}: prohibited phrase {phrase!r}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--guardrail",
        default=None,
        help="Override path to SCOPE_GUARDRAIL.md (default: <root>/docs/SCOPE_GUARDRAIL.md)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    guardrail = Path(args.guardrail) if args.guardrail else None
    result = lint_tree(root, guardrail_path=guardrail)
    if result.errors:
        print("Guardrail copy-lint FAILED:")
        for err in result.errors:
            print(f"  - {err}")
        return 1
    print("OK — no prohibited guardrail phrases on application surfaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
