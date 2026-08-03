#!/usr/bin/env python3
"""Validate HeatGuard monitoring policies (WO-017).

Parses declarative alert policies, asserts every referenced Prometheus metric
exists in the WO-014 registry contract, every log event is in the WO-013
catalogue, ops-check identifiers are allow-listed, and every ``runbook_url``
anchor exists in ``docs/RUNBOOKS.md``.

Usage:
  uv run python scripts/validate_monitoring.py
  uv run python scripts/validate_monitoring.py path/to/policies.yaml
  uv run python scripts/validate_monitoring.py --check-docs-links
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Ops checks that are not Prometheus series (file mtime / external probes).
ALLOWED_OPS_CHECKS = frozenset({"forecast_cache_age_hours"})

REQUIRED_POLICY_FIELDS = (
    "id",
    "display_name",
    "severity",
    "notification_channel_ref",
    "runbook_url",
    "auto_close",
)

ALLOWED_SEVERITIES = frozenset({"page", "critical", "warning", "info"})

MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _repo_root() -> Path:
    return ROOT


def _ensure_src_on_path() -> None:
    src = str(_repo_root() / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _is_within_root(path: Path, root: Path) -> bool:
    """True when ``path`` resolves inside ``root`` (no traversal escape)."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def load_metric_names() -> frozenset[str]:
    """Prefer live registry; fall back to committed fixture for offline use."""
    try:
        _ensure_src_on_path()
        from heatguard.observability.metrics import registered_metric_label_names

        return frozenset(registered_metric_label_names())
    except Exception:
        fixture = _repo_root() / "tests" / "fixtures" / "metrics" / "expected_series.txt"
        names: set[str] = set()
        for line in fixture.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            names.add(line.split("|", 1)[0].strip())
        return frozenset(names)


def load_event_names() -> frozenset[str]:
    try:
        _ensure_src_on_path()
        from heatguard.observability.events import ALL_EVENT_NAMES

        return frozenset(ALL_EVENT_NAMES)
    except Exception:
        return frozenset(
            {
                "http.request",
                "weather.fetch",
                "engine.decide",
                "compliance.append",
                "compliance.verify",
                "policy.query",
                "auth.deprecated_anonymous",
                "wbgt.path_selected",
                "weather.field_substituted",
                "policy.index_unavailable",
                "policy.index_build_failed",
                "risk_model.heuristic_fallback",
                "risk_model.load_failed",
                "engine.phs_warning",
            }
        )


def github_slug(heading: str) -> str:
    """Approximate GitHub / CommonMark heading slug for Markdown anchors."""
    text = heading.strip().lower()
    # Strip markdown emphasis / code markers commonly used in headings.
    text = re.sub(r"[`*_~]", "", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text


def collect_markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEADING_RE.match(line)
        if not m:
            continue
        base = github_slug(m.group(2))
        if not base:
            continue
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def validate_policies(
    policies_path: Path,
    *,
    repo_root: Path | None = None,
    channels_path: Path | None = None,
    require_channels: bool = False,
) -> ValidationResult:
    """Validate one policies YAML document.

    ``require_channels`` is True for the committed production file so channel
    refs must resolve; fixture policies may omit the channels file.
    """
    root = repo_root or _repo_root()
    result = ValidationResult()
    metrics = load_metric_names()
    events = load_event_names()

    try:
        data = load_yaml(policies_path)
    except Exception as exc:  # noqa: BLE001 — surface parse errors clearly
        result.fail(f"{policies_path}: YAML parse error: {exc}")
        return result

    if not isinstance(data, dict) or "policies" not in data:
        result.fail(f"{policies_path}: missing top-level 'policies' list")
        return result

    policies = data["policies"]
    if not isinstance(policies, list) or not policies:
        result.fail(f"{policies_path}: 'policies' must be a non-empty list")
        return result

    channel_ids: set[str] = set()
    ch_path = channels_path or (root / "infra" / "monitoring" / "notification_channels.yaml")
    if ch_path.is_file():
        try:
            ch_data = load_yaml(ch_path)
            for ch in (ch_data or {}).get("channels") or []:
                if isinstance(ch, dict) and ch.get("id"):
                    channel_ids.add(str(ch["id"]))
        except Exception as exc:  # noqa: BLE001
            result.fail(f"{ch_path}: YAML parse error: {exc}")
    elif require_channels:
        result.fail(f"{ch_path}: notification channels file missing")

    runbooks = root / "docs" / "RUNBOOKS.md"
    if not runbooks.is_file():
        result.fail(f"{runbooks}: RUNBOOKS.md missing")
        anchors: set[str] = set()
    else:
        anchors = collect_markdown_anchors(runbooks)

    for idx, policy in enumerate(policies):
        loc = f"{policies_path}:policies[{idx}]"
        if not isinstance(policy, dict):
            result.fail(f"{loc}: policy must be a mapping")
            continue
        pid = policy.get("id", f"#{idx}")
        loc = f"{policies_path}:policy[{pid}]"

        for key in REQUIRED_POLICY_FIELDS:
            if not policy.get(key):
                result.fail(f"{loc}: missing required field '{key}'")

        severity = policy.get("severity")
        if severity and severity not in ALLOWED_SEVERITIES:
            result.fail(
                f"{loc}: severity '{severity}' not in {sorted(ALLOWED_SEVERITIES)}"
            )

        ref = policy.get("notification_channel_ref")
        if ref and channel_ids and ref not in channel_ids:
            result.fail(
                f"{loc}: notification_channel_ref '{ref}' not in {ch_path.name}"
            )
        elif ref and require_channels and not channel_ids:
            result.fail(f"{loc}: cannot resolve notification_channel_ref '{ref}'")

        metric_list = policy.get("metrics")
        if metric_list is None:
            metric_list = []
        if not isinstance(metric_list, list):
            result.fail(f"{loc}: 'metrics' must be a list")
            metric_list = []

        for name in metric_list:
            if not isinstance(name, str) or not name:
                result.fail(f"{loc}: metric entry must be a non-empty string")
                continue
            if name not in metrics:
                result.fail(
                    f"{loc}: undefined metric '{name}' "
                    f"(not in observability registry contract)"
                )

        log_events = policy.get("log_events") or []
        if not isinstance(log_events, list):
            result.fail(f"{loc}: 'log_events' must be a list")
            log_events = []
        for ev in log_events:
            if ev not in events:
                result.fail(f"{loc}: undefined log event '{ev}'")

        ops_checks = policy.get("ops_checks") or []
        if not isinstance(ops_checks, list):
            result.fail(f"{loc}: 'ops_checks' must be a list")
            ops_checks = []
        for op in ops_checks:
            if op not in ALLOWED_OPS_CHECKS:
                result.fail(
                    f"{loc}: unknown ops_check '{op}' "
                    f"(allowed: {sorted(ALLOWED_OPS_CHECKS)})"
                )

        if not metric_list and not log_events and not ops_checks:
            result.fail(
                f"{loc}: must declare at least one of metrics, log_events, ops_checks"
            )

        runbook_url = policy.get("runbook_url")
        if runbook_url:
            _validate_runbook_url(loc, str(runbook_url), root, anchors, result)

    return result


def _validate_runbook_url(
    loc: str,
    runbook_url: str,
    root: Path,
    anchors: set[str],
    result: ValidationResult,
) -> None:
    if "://" in runbook_url and not runbook_url.startswith("file:"):
        # External URLs are allowed but still need a fragment when pointing at RUNBOOKS.
        if "RUNBOOKS" in runbook_url and "#" not in runbook_url:
            result.fail(f"{loc}: runbook_url missing #anchor: {runbook_url}")
        return

    if "#" not in runbook_url:
        result.fail(f"{loc}: runbook_url missing #anchor: {runbook_url}")
        return

    path_part, fragment = runbook_url.split("#", 1)
    if not fragment:
        result.fail(f"{loc}: runbook_url empty #anchor: {runbook_url}")
        return

    root_resolved = root.resolve()
    if path_part:
        target = (root / path_part).resolve()
        if not _is_within_root(target, root_resolved):
            result.fail(f"{loc}: runbook_url escapes repo root: {runbook_url}")
            return
        if not target.is_file():
            result.fail(f"{loc}: runbook file not found: {path_part}")
            return
    else:
        target = (root / "docs" / "RUNBOOKS.md").resolve()

    # Recompute anchors when the URL names a concrete markdown file.
    if path_part and target.is_file():
        file_anchors = collect_markdown_anchors(target)
    else:
        file_anchors = anchors

    if fragment not in file_anchors:
        rel = target.relative_to(root_resolved)
        result.fail(f"{loc}: runbook anchor '#{fragment}' not found in {rel}")


def check_docs_links(repo_root: Path | None = None) -> ValidationResult:
    """Fail on broken relative markdown links in SLO.md and RUNBOOKS.md."""
    root = repo_root or _repo_root()
    result = ValidationResult()
    for rel in ("docs/SLO.md", "docs/RUNBOOKS.md"):
        path = root / rel
        if not path.is_file():
            result.fail(f"{path}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        anchors_cache: dict[Path, set[str]] = {}
        for m in MD_LINK_RE.finditer(text):
            href = m.group(2).strip()
            if href.startswith(("http://", "https://", "mailto:", "#")):
                if href.startswith("#"):
                    anchors = anchors_cache.setdefault(path, collect_markdown_anchors(path))
                    frag = href[1:]
                    if frag and frag not in anchors:
                        result.fail(f"{rel}: broken in-page anchor {href}")
                continue
            if href.startswith("`") or " " in href:
                continue
            link_path, _, frag = href.partition("#")
            if not link_path:
                continue
            target = (path.parent / link_path).resolve()
            if not _is_within_root(target, root):
                result.fail(f"{rel}: link escapes repo root: {href}")
                continue
            if not target.exists():
                result.fail(f"{rel}: broken link to {href}")
                continue
            if frag and target.suffix in {".md", ".markdown"}:
                anchors = anchors_cache.setdefault(target, collect_markdown_anchors(target))
                if frag not in anchors:
                    result.fail(f"{rel}: broken anchor in link {href}")
    return result


def validate_schema_shape(policies_path: Path) -> ValidationResult:
    """Lightweight declarative-format check (YAML structure + required keys)."""
    return validate_policies(policies_path, require_channels=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "policies",
        nargs="?",
        default=str(_repo_root() / "infra" / "monitoring" / "policies.yaml"),
        help="Path to policies YAML (default: infra/monitoring/policies.yaml)",
    )
    parser.add_argument(
        "--check-docs-links",
        action="store_true",
        help="Also validate relative links in docs/SLO.md and docs/RUNBOOKS.md",
    )
    parser.add_argument(
        "--fixtures-only",
        action="store_true",
        help="Skip committed policies (used by unit tests via library API)",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    if not args.fixtures_only:
        path = Path(args.policies)
        res = validate_policies(path, require_channels=True)
        errors.extend(res.errors)

    if args.check_docs_links:
        errors.extend(check_docs_links().errors)

    if errors:
        print("Monitoring validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK — monitoring policies valid ({args.policies})")
    if args.check_docs_links:
        print("OK — docs/SLO.md and docs/RUNBOOKS.md links/anchors valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
