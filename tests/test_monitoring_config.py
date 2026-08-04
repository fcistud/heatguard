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


def test_cli_fixtures_only_still_validates_policies() -> None:
    assert vm.main([str(FIXTURES / "valid_policy.yaml"), "--fixtures-only"]) == 0
    assert vm.main([str(FIXTURES / "bad_metric.yaml"), "--fixtures-only"]) == 1


def test_require_channels_false_ignores_unknown_channel_ref(tmp_path: Path) -> None:
    path = tmp_path / "unknown_channel.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: unknown-channel
    display_name: Unknown channel ok when not required
    severity: warning
    notification_channel_ref: not-a-real-channel
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    relaxed = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert relaxed.ok, relaxed.errors
    strict = vm.validate_policies(path, repo_root=REPO, require_channels=True)
    assert not strict.ok
    assert any("notification_channel_ref" in e for e in strict.errors)


def test_collect_markdown_anchors_skips_fenced_code(tmp_path: Path) -> None:
    md = tmp_path / "sample.md"
    md.write_text(
        """
# Real Heading

```bash
# Not A Heading
# also-not-an-anchor
```

## Another Real
""",
        encoding="utf-8",
    )
    anchors = vm.collect_markdown_anchors(md)
    assert "real-heading" in anchors
    assert "another-real" in anchors
    assert "not-a-heading" not in anchors
    assert "also-not-an-anchor" not in anchors


def test_file_scheme_runbook_url_rejected(tmp_path: Path) -> None:
    path = tmp_path / "file_scheme.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: file-scheme
    display_name: File scheme rejected
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: file://docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("unsupported runbook_url scheme" in e for e in result.errors)


def test_runbooks_do_not_anchor_shell_comment_lines() -> None:
    anchors = vm.collect_markdown_anchors(REPO / "docs" / "RUNBOOKS.md")
    assert "log-filter" not in anchors
    assert "metric-query" not in anchors
    assert "list-revisions" not in anchors


def test_auth_gate_policy_uses_known_event() -> None:
    data = vm.load_yaml(POLICIES)
    auth = next(p for p in data["policies"] if p["id"] == "auth-deprecated-anonymous-quiet")
    assert "auth.deprecated_anonymous" in auth["log_events"]
    assert auth["metrics"] == []


def test_forecast_cache_stale_uses_ops_check() -> None:
    data = vm.load_yaml(POLICIES)
    stale = next(p for p in data["policies"] if p["id"] == "forecast-cache-stale")
    assert "forecast_cache_age_hours" in stale["ops_checks"]


def test_runbook_url_escaping_repo_root_fails(tmp_path: Path) -> None:
    path = tmp_path / "escape.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: escape
    display_name: Path escape
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: ../../etc/passwd#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("escapes repo root" in e for e in result.errors)


def test_ensure_src_on_path_is_idempotent() -> None:
    import sys

    src = str(REPO / "src")
    before = sys.path.count(src)
    vm._ensure_src_on_path()
    vm._ensure_src_on_path()
    vm.load_metric_names()
    vm.load_event_names()
    assert sys.path.count(src) == max(before, 1)


def test_missing_policies_file_reports_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    result = vm.validate_policies(missing, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("file not found" in e for e in result.errors)
    assert not any("YAML parse error" in e for e in result.errors)


def test_non_string_log_event_reports_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "bad_event.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: bad-event
    display_name: Bad event type
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics: []
    log_events:
      - key: auth.deprecated_anonymous
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("log_events entry must be a non-empty string" in e for e in result.errors)


def test_non_string_ops_check_reports_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "bad_ops.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: bad-ops
    display_name: Bad ops type
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_weather_fetch_total
    ops_checks:
      - [forecast_cache_age_hours]
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("ops_checks entry must be a non-empty string" in e for e in result.errors)


def test_unhashable_severity_reports_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "bad_severity.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: bad-severity
    display_name: Bad severity type
    severity:
      - critical
    notification_channel_ref: ops-email
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("'severity' must be a non-empty string" in e for e in result.errors)


def test_unhashable_channel_ref_reports_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "bad_channel_ref.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: bad-channel-ref
    display_name: Bad channel ref type
    severity: warning
    notification_channel_ref:
      - oncall-pager
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=True)
    assert not result.ok
    assert any(
        "'notification_channel_ref' must be a non-empty string" in e for e in result.errors
    )


def test_missing_channels_file_is_not_noisy_per_policy(tmp_path: Path) -> None:
    policies = tmp_path / "policies.yaml"
    policies.write_text(
        """
version: 1
policies:
  - id: one
    display_name: One
    severity: warning
    notification_channel_ref: oncall-pager
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
  - id: two
    display_name: Two
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    missing_channels = tmp_path / "no-channels.yaml"
    result = vm.validate_policies(
        policies,
        repo_root=REPO,
        channels_path=missing_channels,
        require_channels=True,
    )
    assert not result.ok
    assert sum("notification channels file missing" in e for e in result.errors) == 1
    assert not any("cannot resolve notification_channel_ref" in e for e in result.errors)
    assert not any("not in no-channels.yaml" in e for e in result.errors)


def test_non_string_runbook_url_reports_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "bad_runbook.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: bad-runbook
    display_name: Bad runbook type
    severity: warning
    notification_channel_ref: ops-email
    runbook_url:
      - docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("'runbook_url' must be a non-empty string" in e for e in result.errors)
    assert not any("unsupported runbook_url scheme" in e for e in result.errors)


def test_empty_id_uses_index_in_error_location(tmp_path: Path) -> None:
    path = tmp_path / "empty_id.yaml"
    path.write_text(
        """
version: 1
policies:
  - id: ""
    display_name: Empty id
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(path, repo_root=REPO, require_channels=False)
    assert not result.ok
    assert any("policy[#0]" in e for e in result.errors)
    assert any("'id' must be a non-empty string" in e for e in result.errors)


def test_missing_runbooks_is_not_noisy_per_policy(tmp_path: Path) -> None:
    policies = tmp_path / "policies.yaml"
    policies.write_text(
        """
version: 1
policies:
  - id: one
    display_name: One
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: docs/RUNBOOKS.md#weather-ingest-failure
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
  - id: two
    display_name: Two
    severity: warning
    notification_channel_ref: ops-email
    runbook_url: docs/RUNBOOKS.md#cold-start-or-latency-regression
    auto_close: after_ok_15m
    metrics:
      - heatguard_http_requests_total
""",
        encoding="utf-8",
    )
    result = vm.validate_policies(
        policies,
        repo_root=tmp_path,
        require_channels=False,
    )
    assert not result.ok
    assert sum("RUNBOOKS.md missing" in e for e in result.errors) == 1
    assert not any("runbook file not found" in e for e in result.errors)
    assert not any("runbook anchor" in e for e in result.errors)
