"""Prometheus SLI metrics registry and private /metrics exposition (WO-014)."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("prometheus_client")

from fastapi.testclient import TestClient

from heatguard._paths import _REPO_ROOT
from heatguard.compliance import ComplianceLog
from heatguard.observability import metrics as obs_metrics
from heatguard.sites import get_site
from heatguard.types import MetabolicCategory, Weather, Worker
from heatguard.weather import openmeteo

FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "metrics" / "expected_series.txt"


def _parse_expected() -> dict[str, frozenset[str]]:
    out: dict[str, frozenset[str]] = {}
    for line in FIXTURE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, labels = line.partition("|")
        labs = frozenset(x for x in labels.split(",") if x) if labels else frozenset()
        out[name] = labs
    return out


@pytest.fixture(autouse=True)
def _fresh_registry():
    obs_metrics.reset_registry()
    yield
    obs_metrics.reset_registry()


def test_expected_series_fixture_matches_registry() -> None:
    expected = _parse_expected()
    declared = obs_metrics.registered_metric_label_names()
    assert set(expected) == set(declared)
    for name, labels in expected.items():
        assert declared[name] == labels, f"{name}: {declared[name]} != {labels}"


def test_forbidden_label_cardinality_guard() -> None:
    for name, labels in obs_metrics.registered_metric_label_names().items():
        bad = labels & obs_metrics.FORBIDDEN_LABELS
        assert not bad, f"{name} has forbidden labels {bad}"


def test_ratelimit_helper_registered_at_zero() -> None:
    assert hasattr(obs_metrics, "observe_ratelimit_rejected")
    text = obs_metrics.render_prometheus().decode()
    assert "heatguard_ratelimit_rejected_total" in text
    # Helper increments when called.
    obs_metrics.observe_ratelimit_rejected(route="/decide", key_class="ip")
    text2 = obs_metrics.render_prometheus().decode()
    assert 'heatguard_ratelimit_rejected_total{key_class="ip",route="/decide"} 1.0' in text2


def test_observe_http_and_helpers_move_counters() -> None:
    obs_metrics.observe_http_request(
        route="/health/live",
        method="GET",
        status_code=200,
        duration_seconds=0.02,
        response_bytes=32,
    )
    obs_metrics.observe_panel_cache("demo", "hit")
    obs_metrics.observe_not_modified("/demo/{site_key}")
    obs_metrics.observe_compression_ratio(6.5)
    obs_metrics.observe_weather_fetch(
        site_key="dubai", source="archive", outcome="cache_hit", duration_seconds=0.001
    )
    obs_metrics.observe_engine_decision(signal="WORK", wbgt_source="liljegren")
    obs_metrics.record_process_start_duration(1.25)

    body = obs_metrics.render_prometheus().decode()
    assert 'heatguard_http_requests_total{method="GET",route="/health/live",status_class="2xx"} 1.0' in body
    assert 'heatguard_panel_cache_events_total{panel="demo",result="hit"} 1.0' in body
    assert 'heatguard_http_not_modified_total{route="/demo/{site_key}"} 1.0' in body
    assert "heatguard_response_compression_ratio_bucket" in body
    assert 'outcome="cache_hit"' in body
    assert 'signal="WORK"' in body
    assert "heatguard_process_start_duration_seconds 1.25" in body


def test_compliance_verify_ok_and_failed() -> None:
    clog = ComplianceLog("test", site_key="dubai")
    assert clog.verify_chain() is True
    body = obs_metrics.render_prometheus().decode()
    assert 'heatguard_compliance_chain_verify_total{result="ok",site_key="dubai"} 1.0' in body

    # Tamper via broken linkage (records are frozen dataclasses).
    from heatguard.scheduler import schedule

    site = get_site("dubai")
    w = Weather(
        timestamp=datetime(2025, 5, 16, 12, tzinfo=timezone.utc),
        tdb_c=38.0,
        rh_pct=40.0,
        wind_ms=2.0,
        shortwave_wm2=800.0,
        direct_wm2=700.0,
        dew_point_c=20.0,
        pressure_hpa=1013.0,
    )
    worker = Worker("t", days_on_job=120, acclimatized=True)
    adv = schedule(w, site, worker, MetabolicCategory.HEAVY)
    clog.append(adv)
    assert clog.records
    object.__setattr__(clog.records[0], "prev_hash", "tampered-prev")
    assert clog.verify_chain() is False
    body2 = obs_metrics.render_prometheus().decode()
    assert 'result="failed"' in body2
    assert "heatguard_compliance_records_appended_total" in body2


def test_weather_timeout_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    site = get_site("dubai")

    def boom(*_a, **_k):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(httpx.TimeoutException):
        openmeteo.fetch_forecast(site, use_cache=False, refresh=True)
    body = obs_metrics.render_prometheus().decode()
    assert 'outcome="timeout"' in body
    assert 'source="forecast"' in body


def test_metrics_not_on_public_surface_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEATGUARD_METRICS_ENABLED", raising=False)
    from heatguard.api import app

    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 404


def test_private_metrics_scrape_after_traffic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEATGUARD_METRICS_ENABLED", "1")
    from heatguard import api

    api.mount_private_routes(api.app)
    client = TestClient(api.app)

    assert client.get("/health/live").status_code == 200
    assert client.get("/sites").status_code == 200
    client.get("/demo/dubai")
    client.get("/forecast/dubai")
    client.get("/compliance/dubai/export?fmt=csv")
    client.get("/no-such-scanner-path-xyz")

    scrape = client.get("/metrics")
    assert scrape.status_code == 200
    assert "text/plain" in scrape.headers.get("content-type", "")
    body = scrape.text
    expected = _parse_expected()
    for name in expected:
        assert name in body, f"missing series {name}"
    assert 'route="/health/live"' in body
    assert 'status_class="2xx"' in body
    assert 'route="unmatched"' in body


def test_http_error_still_records_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEATGUARD_METRICS_ENABLED", "1")
    from heatguard import api

    api.mount_private_routes(api.app)
    client = TestClient(api.app, raise_server_exceptions=False)
    resp = client.get("/demo/not_a_real_site")
    assert resp.status_code == 404
    body = client.get("/metrics").text
    assert "heatguard_http_requests_total" in body
    assert 'status_class="4xx"' in body