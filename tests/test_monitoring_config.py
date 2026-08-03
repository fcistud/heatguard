"""Offline validation of monitoring policies (WO-017)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "monitoring"
POLICIES = REPO / "infra" / "monitoring" / "policies.yaml"


def _load_validator():
    import sys

    path = REPO / "scripts" / "validate_monitoring.py"
    spec = importlib.util.spec_from_file_location("validate_monitoring", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


vm = _load_validator()


def test_committed_policies_valid() -> None:
    result = vm.validate_policies(POLICIES, repo_root=REPO, require_channels=True)
    assert result.ok, result.errors


def test_valid_fixture_passes() -> None:
    result = vm.validate_policies(
        FIXTURES / "valid_policy.yaml",
        repo_root=REPO,
        require_channels=False,
    )
    assert result.ok, result.errors


def test_bad_metric_fixture_fails_with_metric_name() -> None:
    result = vm.validate_policies(
        FIXTURES / "bad_metric.yaml",
        repo_root=REPO,
        require_channels=False,
    )
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "heatguard_definitely_not_a_real_metric_total" in joined
    assert "undefined metric" in joined


def test_missing_runbook_fixture_fails() -> None:
    result = vm.validate_policies(
        FIXTURES / "missing_runbook.yaml",
        repo_root=REPO,
        require_channels=False,
    )
    assert not result.ok
    joined = "\n".join(result.errors)
    assert "runbook_url" in joined


def test_dangling_runbook_anchor_fails(tmp_path: Path) -> None:
    path = tmp_path / "dangling.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: dangling
    display_name: Dangling anchor
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: docs/RUNBOOKS.md#this-anchor-does-not-exist
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("this-anchor-does-not-exist" in e for e in result.errors)


def test_github_slug_matches_runbook_headings() -> None:
    anchors = vm.collect_markdown_anchors(REPO / "docs" / "RUNBOOKS.md")
    for expected in (
        "weather-ingest-failure",
        "rate-limit-and-cpu-saturation",
        "compliance-chain-verification-failure",
        "cold-start-or-latency-regression",
        "automated-rollback-and-canary",
        "auth-dual-mode-promotion-gate",
        "notification-channel-smoke-test",
    ):
        assert expected in anchors, expected


def test_docs_links_ok() -> None:
    result = vm.check_docs_links(REPO)
    assert result.ok, result.errors


def test_cli_main_succeeds() -> None:
    assert vm.main([str(POLICIES), "--check-docs-links"]) == 0


def test_cli_main_fails_on_bad_fixture() -> None:
    assert vm.main([str(FIXTURES / "bad_metric.yaml")]) == 1


def test_auth_gate_policy_uses_known_event() -> None:
    data = vm.load_yaml(POLICIES)
    auth = next(p for p in data["policies"] if p["id"] == "auth-deprecated-anonymous-quiet")
    assert "auth.deprecated_anonymous" in auth["log_events"]
    assert auth["metrics"] == []


def test_forecast_cache_stale_uses_ops_check() -> None:
    data = vm.load_yaml(POLICIES)
    stale = next(p for p in data["policies"] if p["id"] == "forecast-cache-stale")
    assert "forecast_cache_age_hours" in stale["ops_checks"]
