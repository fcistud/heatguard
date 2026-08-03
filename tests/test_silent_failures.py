"""Silent-failure → degraded-mode signals (WO-016)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from heatguard._paths import _REPO_ROOT
from heatguard.health import clear_readiness_cache, get_readiness
from heatguard.observability import degradation as deg
from heatguard.observability import metrics as obs_metrics
from heatguard.sites import get_site
from heatguard.types import MetabolicCategory, Weather, Worker
from heatguard.weather import openmeteo

FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "degraded"


@pytest.fixture(autouse=True)
def _reset_degradation():
    import heatguard.policy_rag as pr
    import heatguard.risk_model as rm

    deg.clear_degradation_state()
    obs_metrics.reset_registry()
    clear_readiness_cache()
    rm._load_model.cache_clear()
    if hasattr(pr._build_index, "cache_clear"):
        pr._build_index.cache_clear()
    yield
    deg.clear_degradation_state()
    obs_metrics.reset_registry()
    clear_readiness_cache()
    rm._load_model.cache_clear()
    if hasattr(pr._build_index, "cache_clear"):
        pr._build_index.cache_clear()


@pytest.fixture
def captured_events(monkeypatch):
    """Capture structured log events from degradation helpers."""
    events: list[dict] = []

    class _Recorder:
        def info(self, event: str, **kw):
            events.append({"event": event, **kw})

        def error(self, event: str, **kw):
            events.append({"event": event, **kw})

    monkeypatch.setattr(
        "heatguard.observability.logging.get_logger",
        lambda *_a, **_k: _Recorder(),
    )
    return events


def test_wbgt_exception_path_emits_event_and_metric(monkeypatch, captured_events):
    from heatguard import wbgt

    def boom(*_a, **_k):
        raise RuntimeError("thermofeel down")

    monkeypatch.setattr(wbgt, "wbgt_liljegren", boom)
    site = get_site("dubai")
    w = Weather(
        datetime(2025, 5, 16, 12, tzinfo=timezone.utc),
        40.0,
        40.0,
        2.0,
        800.0,
        700.0,
        20.0,
        1013.0,
    )
    est = wbgt.estimate_wbgt(w, site)
    assert est.source == "fallback"
    assert "wbgt_fallback_active" in deg.active_reason_codes()
    body = obs_metrics.render_prometheus().decode()
    assert 'heatguard_wbgt_path_total{path="fallback_exception"}' in body
    path_ev = [e for e in captured_events if e.get("event") == "wbgt.path_selected"]
    assert path_ev and path_ev[0].get("path") == "fallback_exception"
    assert path_ev[0].get("exception_type") == "RuntimeError"


def test_wbgt_invalid_liljegren_latches_degraded(monkeypatch, captured_events):
    from heatguard import wbgt

    monkeypatch.setattr(wbgt, "wbgt_liljegren", lambda *_a, **_k: 999.0)
    site = get_site("dubai")
    w = Weather(
        datetime(2025, 5, 16, 12, tzinfo=timezone.utc),
        40.0,
        40.0,
        2.0,
        800.0,
        700.0,
        20.0,
        1013.0,
    )
    est = wbgt.estimate_wbgt(w, site)
    assert est.source == "fallback"
    assert "wbgt_fallback_active" in deg.active_reason_codes()
    body = obs_metrics.render_prometheus().decode()
    assert 'heatguard_wbgt_path_total{path="fallback_invalid"}' in body
    assert any(
        e.get("event") == "wbgt.path_selected" and e.get("path") == "fallback_invalid"
        for e in captured_events
    )


def test_degradation_ttl_env_override(monkeypatch):
    monkeypatch.setenv("HEATGUARD_DEGRADATION_TTL_SECONDS", "0.05")
    clock = {"t": 1_000.0}
    monkeypatch.setattr(deg.time, "monotonic", lambda: clock["t"])

    deg.report_degraded(deg.WBGT_FALLBACK_ACTIVE, detail="ttl")
    assert "wbgt_fallback_active" in deg.active_reason_codes()
    clock["t"] += 0.06
    assert "wbgt_fallback_active" not in deg.active_reason_codes()


def test_degradation_ttl_zero_disables_snapshot_latch(monkeypatch, captured_events):
    monkeypatch.setenv("HEATGUARD_DEGRADATION_TTL_SECONDS", "0")
    calls: list[int] = []
    deg.report_degraded(
        deg.WBGT_FALLBACK_ACTIVE,
        detail="no-latch",
        once_key="wbgt:ttl0",
        log_event=deg.WBGT_PATH_SELECTED,
        log_fields={"path": "ttl0"},
        increment_metric=lambda: calls.append(1),
    )
    assert "wbgt_fallback_active" not in deg.active_reason_codes()
    assert len(calls) == 1
    assert any(e.get("event") == "wbgt.path_selected" for e in captured_events)


def test_report_degraded_dedupes_logs_but_always_increments_metric(captured_events):
    calls: list[int] = []

    def bump() -> None:
        calls.append(1)

    deg.report_degraded(
        deg.WBGT_FALLBACK_ACTIVE,
        detail="a",
        once_key="wbgt:test",
        log_event=deg.WBGT_PATH_SELECTED,
        log_fields={"path": "test"},
        increment_metric=bump,
    )
    deg.report_degraded(
        deg.WBGT_FALLBACK_ACTIVE,
        detail="b",
        once_key="wbgt:test",
        log_event=deg.WBGT_PATH_SELECTED,
        log_fields={"path": "test"},
        increment_metric=bump,
    )
    assert len(calls) == 2
    assert len([e for e in captured_events if e.get("event") == "wbgt.path_selected"]) == 1


def test_weather_null_fields_substitute_and_count(captured_events):
    site = get_site("dubai")
    payload = json.loads((FIXTURES / "openmeteo_null_fields.json").read_text())
    rows = openmeteo._parse(payload, site)
    assert len(rows) == 3
    assert all(r.rh_pct == 30.0 for r in rows)
    assert all(r.pressure_hpa == 1013.0 for r in rows)
    summary = openmeteo.last_parse_substitutions()
    assert summary.get("relative_humidity_2m") == 3
    assert summary.get("surface_pressure") == 3
    assert "weather_fields_substituted" in deg.active_reason_codes()
    body = obs_metrics.render_prometheus().decode()
    assert "heatguard_weather_field_substituted_total" in body
    assert any(e.get("event") == "weather.field_substituted" for e in captured_events)


def test_weather_parse_failure_clears_stale_substitutions():
    site = get_site("dubai")
    good = json.loads((FIXTURES / "openmeteo_null_fields.json").read_text())
    openmeteo._parse(good, site)
    assert openmeteo.last_parse_substitutions()
    try:
        openmeteo._parse({"hourly": {}}, site)  # missing "time"
    except Exception:
        pass
    assert openmeteo.last_parse_substitutions() == {}


def test_policy_index_unavailable_when_sklearn_missing(monkeypatch, captured_events):
    import heatguard.policy_rag as pr

    monkeypatch.setattr(pr, "_HAS_SKLEARN", False)
    pr._build_index.cache_clear()
    ans = pr.query_policy("When does the UAE midday ban start?")
    assert ans.degraded is True
    assert ans.degraded_reason == "sklearn missing"
    assert ans.sources == []
    assert "unavailable" in ans.answer.lower() or "Policy index unavailable" in ans.answer
    assert "policy_index_unavailable" in deg.active_reason_codes()
    assert any(e.get("event") == "policy.index_unavailable" for e in captured_events)


def test_policy_index_build_failure_sanitizes_api_reason(monkeypatch, captured_events):
    import heatguard.policy_rag as pr

    def boom():
        raise RuntimeError("/secret/path/policy.bin: corrupt header XYZ")

    monkeypatch.setattr(pr, "_build_index", boom)
    ans = pr.query_policy("midday ban?")
    assert ans.degraded is True
    assert ans.degraded_reason == "index build failed"
    dumped = json.dumps(ans.to_dict())
    assert "/secret/path" not in dumped
    assert "corrupt header" not in dumped
    assert any(e.get("event") == "policy.index_unavailable" for e in captured_events)


def test_risk_model_corrupt_joblib_heuristic(monkeypatch, captured_events):
    import heatguard.risk_model as rm

    monkeypatch.setattr(rm, "model_path", lambda: FIXTURES / "risk_model.joblib")
    rm._load_model.cache_clear()
    site = get_site("dubai")
    from heatguard.scheduler import build_conditions

    w = Weather(
        datetime(2025, 5, 16, 12, tzinfo=timezone.utc),
        38.0,
        50.0,
        2.0,
        700.0,
        600.0,
        22.0,
        1013.0,
    )
    c = build_conditions(w, site, MetabolicCategory.HEAVY)
    worker = Worker("t", days_on_job=0, acclimatized=False)
    risk = rm.assess(c, worker)
    assert risk.model_source == "heuristic"
    assert "risk_model_heuristic" in deg.active_reason_codes()
    body = obs_metrics.render_prometheus().decode()
    assert "heatguard_risk_model_fallback_total" in body
    fallback_ev = [e for e in captured_events if e.get("event") == "risk_model.heuristic_fallback"]
    assert fallback_ev
    reason = fallback_ev[0].get("reason", "")
    assert reason.startswith("load failed:")
    assert "/" not in reason and "\\" not in reason
    assert len(reason) < 80


def test_phs_warning_captured(monkeypatch, captured_events):
    import warnings

    import heatguard.hydration as hyd
    from heatguard.scheduler import build_conditions
    from heatguard.sites import get_site

    site = get_site("dubai")
    w = Weather(
        datetime(2025, 5, 16, 12, tzinfo=timezone.utc),
        48.0,
        90.0,
        0.5,
        1000.0,
        900.0,
        30.0,
        1013.0,
    )
    c = build_conditions(w, site, MetabolicCategory.HEAVY)
    worker = Worker("t", days_on_job=120, acclimatized=True)

    real_phs = hyd.phs
    msgs = iter(["out of envelope A", "out of envelope B"])

    def noisy_phs(*a, **k):
        warnings.warn(next(msgs), UserWarning)
        return real_phs(*a, **k)

    monkeypatch.setattr(hyd, "phs", noisy_phs)
    hyd.max_safe_minutes(c, worker)
    hyd.max_safe_minutes(c, worker)
    phs_ev = [e for e in captured_events if e.get("event") == "engine.phs_warning"]
    # One emit per warning category — message stays a field, not part of once_key.
    assert len(phs_ev) == 1
    assert phs_ev[0].get("category") == "UserWarning"
    assert "message" in phs_ev[0]


def test_ready_includes_stable_degraded_codes():
    deg.report_degraded(deg.WBGT_FALLBACK_ACTIVE, detail="test")
    deg.report_degraded(deg.WEATHER_FIELDS_SUBSTITUTED, detail="test")
    clear_readiness_cache()
    result = get_readiness(force=True)
    assert result.status == "degraded"
    codes = set(result.degraded)
    assert "wbgt_fallback_active" in codes
    assert "weather_fields_substituted" in codes
    assert result.failed == []


def test_api_ready_degraded_fixture_integration(monkeypatch):
    import heatguard.policy_rag as pr
    import heatguard.risk_model as rm

    monkeypatch.setattr(pr, "_HAS_SKLEARN", False)
    monkeypatch.setattr(rm, "model_path", lambda: FIXTURES / "risk_model.joblib")
    pr._build_index.cache_clear()
    rm._load_model.cache_clear()
    # Touch paths so snapshot latches.
    pr.query_policy("test?")
    from heatguard.scheduler import build_conditions

    site = get_site("dubai")
    w = Weather(
        datetime(2025, 5, 16, 12, tzinfo=timezone.utc),
        38.0,
        50.0,
        2.0,
        700.0,
        600.0,
        22.0,
        1013.0,
    )
    rm.assess(build_conditions(w, site, MetabolicCategory.HEAVY), Worker("t"))

    from heatguard.api import app

    client = TestClient(app)
    clear_readiness_cache()
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    degraded = set(body["degraded"])
    assert "policy_index_unavailable" in degraded or any(
        "policy_index_unavailable" in x for x in degraded
    )
    assert "risk_model_heuristic" in degraded or any(
        "risk_model_heuristic" in x for x in degraded
    )
