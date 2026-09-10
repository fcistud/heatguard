"""Guardrail copy-lint (WO-013).

Phrase lists are parsed from docs/SCOPE_GUARDRAIL.md section Appendix A —
that document is the single source of truth, not this module.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from heatguard._paths import _REPO_ROOT

REPO = _REPO_ROOT
SCRIPT = REPO / "scripts" / "check_guardrail_copy.py"
FIXTURES = REPO / "tests" / "fixtures" / "copy"
GUARDRAIL = REPO / "docs" / "SCOPE_GUARDRAIL.md"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_guardrail_copy", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cl = _load_checker()


def _appendix_list_item_count(markdown: str, heading: str) -> int:
    """Count `- ` items under a subsection without using the parser's tuple."""
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    count = 0
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if line.lstrip().startswith(("- ", "* ")):
            count += 1
    return count


def test_parse_appendix_a_from_committed_guardrail() -> None:
    phrases = cl.load_phrase_lists(GUARDRAIL)
    text = GUARDRAIL.read_text(encoding="utf-8")
    assert phrases.prohibited
    assert phrases.approved
    assert len(phrases.prohibited) == _appendix_list_item_count(
        text, cl.PROHIBITED_HEADING
    )
    assert len(phrases.approved) == _appendix_list_item_count(text, cl.APPROVED_HEADING)
    assert "Safe to work now" in phrases.prohibited


def test_parse_skips_fenced_prohibited_list(tmp_path: Path) -> None:
    md = tmp_path / "guardrail.md"
    md.write_text(
        """
## Appendix A — Language dictionary

### Approved phrasebook

- "Keep this approved phrase"

### Prohibited phrasebook

```
- "Ignore this fenced phrase"
```

- "Real prohibited phrase"
""",
        encoding="utf-8",
    )
    phrases = cl.load_phrase_lists(md)
    assert phrases.prohibited == ("Real prohibited phrase",)
    assert "Ignore this fenced phrase" not in phrases.prohibited


def test_missing_appendix_fails_closed(tmp_path: Path) -> None:
    md = tmp_path / "empty.md"
    md.write_text("# No appendix here\n", encoding="utf-8")
    try:
        cl.parse_appendix_a(md.read_text(encoding="utf-8"))
    except ValueError as exc:
        assert "Appendix A heading not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_empty_prohibited_list_fails_closed() -> None:
    markdown = """
## Appendix A — Language dictionary

### Approved phrasebook

- "An approved phrase"

### Prohibited phrasebook

No list items here.
"""
    try:
        cl.parse_appendix_a(markdown)
    except ValueError as exc:
        assert "empty" in str(exc).lower()
        assert "Prohibited" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_renamed_appendix_fails_closed() -> None:
    markdown = """
## Appendix B — Language dictionary

### Approved phrasebook

- "An approved phrase"

### Prohibited phrasebook

- "A prohibited phrase"
"""
    try:
        cl.parse_appendix_a(markdown)
    except ValueError as exc:
        assert "Appendix A heading not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_normalize_case() -> None:
    assert cl.find_phrase_on_line("SAFE TO WORK NOW", ("Safe to work now",))


def test_normalize_whitespace() -> None:
    assert cl.find_phrase_on_line("Safe    to\twork now", ("Safe to work now",))


def test_normalize_markdown_emphasis() -> None:
    assert cl.find_phrase_on_line("**Safe to work now**", ("Safe to work now",))


def test_normalize_curly_apostrophe() -> None:
    assert cl.find_phrase_on_line("don\u2019t override", ("don't override",))


def test_normalize_en_dash() -> None:
    assert cl.find_phrase_on_line("mid\u2013day ban", ("mid-day ban",))


def test_split_across_lines_does_not_match() -> None:
    text = "HeatGuard permits work during\nbanned hours\n"
    assert cl.scan_text(text, ("HeatGuard permits work during banned hours",)) == []


def test_clean_fixture_has_no_hits() -> None:
    text = (FIXTURES / "clean.txt").read_text(encoding="utf-8")
    phrases = cl.load_phrase_lists(GUARDRAIL)
    assert cl.scan_text(text, phrases.prohibited) == []


def test_plain_prohibited_fixture_hits() -> None:
    text = (FIXTURES / "prohibited_plain.txt").read_text(encoding="utf-8")
    phrases = cl.load_phrase_lists(GUARDRAIL)
    hits = cl.scan_text(text, phrases.prohibited)
    assert hits
    assert hits[0][1] == "HeatGuard permits work during banned hours"


def test_disguised_prohibited_fixture_hits() -> None:
    text = (FIXTURES / "prohibited_disguised.txt").read_text(encoding="utf-8")
    phrases = cl.load_phrase_lists(GUARDRAIL)
    hits = cl.scan_text(text, phrases.prohibited)
    assert any(phrase == "Safe to work now" for _line, phrase in hits)
    assert not any(
        phrase == "HeatGuard permits work during banned hours" for _line, phrase in hits
    )


def test_exemptions_are_justified_and_non_production() -> None:
    production_prefixes = ("web/", "landing/", "website/", "src/")
    assert cl.EXEMPTIONS
    for path, reason in cl.exemption_reasons():
        assert reason.strip(), path
        posix = path.replace("\\", "/")
        assert not any(posix.startswith(p) for p in production_prefixes), path
    assert cl.is_exempt("docs/SCOPE_GUARDRAIL.md")
    assert cl.is_exempt("tests/fixtures/copy/prohibited_plain.txt")
    assert not cl.is_exempt("web/src/App.tsx")
    assert not cl.is_exempt("src/heatguard/api.py")


def test_binary_and_undecodable_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    shutil.copy2(GUARDRAIL, tmp_path / "docs" / "SCOPE_GUARDRAIL.md")
    web = tmp_path / "web" / "src"
    web.mkdir(parents=True)
    (web / "ok.txt").write_text("comparison view only\n", encoding="utf-8")
    (web / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    (web / "weird.txt").write_bytes(b"\xff\xfe\x00\x00not utf8")
    result = cl.lint_tree(tmp_path)
    assert result.ok, result.errors


def test_cli_real_tree_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(REPO)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK — no prohibited guardrail phrases" in proc.stdout


def test_cli_injected_web_src_violation_exits_nonzero(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    shutil.copy2(GUARDRAIL, tmp_path / "docs" / "SCOPE_GUARDRAIL.md")
    web = tmp_path / "web" / "src"
    web.mkdir(parents=True)
    (web / "bad.tsx").write_text(
        "export const claim = 'HeatGuard permits work during banned hours';\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    joined = proc.stdout + proc.stderr
    assert "web/src/bad.tsx:1:" in joined
    assert "HeatGuard permits work during banned hours" in joined


def test_cli_missing_guardrail_exits_nonzero(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "not found" in (proc.stdout + proc.stderr).lower()


def test_main_empty_prohibited_fails_closed(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "SCOPE_GUARDRAIL.md"
    md.parent.mkdir()
    md.write_text(
        """
## Appendix A — Language dictionary

### Approved phrasebook

- "An approved phrase"

### Prohibited phrasebook
""",
        encoding="utf-8",
    )
    assert cl.main(["--root", str(tmp_path)]) == 1
