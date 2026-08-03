"""Structured logging, redaction, and correlation tests (WO-013)."""
from __future__ import annotations

import io
import json
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("structlog")

import structlog
from fastapi.testclient import TestClient

from heatguard._paths import _REPO_ROOT
from heatguard.api import app
from heatguard.observability import (
    AUTH_DEPRECATED_ANONYMOUS,
    ENGINE_DECIDE,
    HTTP_REQUEST,
    WEATHER_FETCH,
    configure_logging,
    emit_auth_deprecated_anonymous,
)
from heatguard.observability.events import (
    ENGINE_PHS_WARNING,
    POLICY_INDEX_BUILD_FAILED,
    POLICY_INDEX_UNAVAILABLE,
    RISK_MODEL_HEURISTIC_FALLBACK,
    RISK_MODEL_LOAD_FAILED,
    WEATHER_FIELD_SUBSTITUTED,
)
from heatguard.observability import logging as obs_logging
from heatguard.observability.logging import redact_processor

EXPECTED = json.loads(
    (_REPO_ROOT / "tests" / "fixtures" / "logging" / "expected_event_keys.json").read_text()
)


@pytest.fixture
def captured_logs():
    """Capture structlog event dicts while keeping request-context + redaction processors."""
    from heatguard.observability import degradation as deg

    # One-shot degradation events must be re-emit-able per capture window.
    deg.clear_degradation_state()
    entries: list[dict[str, Any]] = []

    def _capture(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        entries.append(dict(event_dict))
        return event_dict

    sink = io.StringIO()
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            obs_logging._merge_request_context,
            obs_logging._iso_utc_timestamp,
            structlog.stdlib.add_log_level,
            obs_logging._cloud_severity,
            obs_logging.redact_processor,
            _capture,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(file=sink),
        cache_logger_on_first_use=False,
    )
    yield entries
    sink.close()
    deg.clear_degradation_state()
    configure_logging(level="INFO")


def _events(cap: list[dict], name: str) -> list[dict]:
    return [e for e in cap if e.get("event") == name]


def test_expected_event_keys_fixture_covers_all_named_events() -> None:
    from heatguard.observability.events import ALL_EVENT_NAMES

    assert set(EXPECTED) == set(ALL_EVENT_NAMES)


def test_sanitize_request_id_rejects_unsafe_tokens() -> None:
    from heatguard.observability.logging import resolve_request_id, sanitize_request_id

    assert sanitize_request_id("ok-id_1.2") == "ok-id_1.2"
    assert sanitize_request_id("bad id with spaces") is None
    assert sanitize_request_id("emoji-🔥") is None
    # Unsafe inbound header must be replaced with a generated UUID.
    rid = resolve_request_id({"x-request-id": "not safe\n"})
    assert sanitize_request_id(rid) == rid
    assert " " not in rid and "\n" not in rid


def test_http_request_emitted_once_per_request(captured_logs: list[dict]) -> None:
    client = TestClient(app)
    resp = client.get("/health/live")
    assert resp.status_code == 200
    http_events = _events(captured_logs, HTTP_REQUEST)
    assert len(http_events) == 1
    ev = http_events[0]
    for key in EXPECTED[HTTP_REQUEST]:
        assert key in ev, f"missing {key} in {ev}"


def test_correlation_id_inbound_to_response_and_events(captured_logs: list[dict]) -> None:
    client = TestClient(app)
    rid = "test-corr-id-wo013"
    live = client.get("/health/live", headers={"X-Request-Id": rid})
    demo = client.get("/demo/dubai", headers={"X-Request-Id": rid})
    decide = client.post(
        "/decide",
        headers={"X-Request-Id": rid},
        json={
            "site_key": "dubai",
            "tdb": 38.0,
            "rh": 40.0,
            "hour": 12,
            "age": 42,
            "weight_kg": 88.5,
            "height_m": 1.82,
            "has_comorbidity": True,
        },
    )
    export = client.get(
        "/compliance/dubai/export?fmt=csv",
        headers={"X-Request-Id": rid},
    )
    assert live.headers.get("x-request-id") == rid
    assert demo.headers.get("x-request-id") == rid
    assert decide.headers.get("x-request-id") == rid
    assert export.headers.get("x-request-id") == rid
    assert demo.status_code == 200
    assert decide.status_code == 200
    assert export.status_code == 200

    http_events = _events(captured_logs, HTTP_REQUEST)
    assert len(http_events) == 4
    assert all(e.get("request_id") == rid for e in http_events)

    decide_events = _events(captured_logs, ENGINE_DECIDE)
    assert decide_events
    assert all(e.get("request_id") == rid for e in decide_events)


def test_redaction_drops_pii_from_decide_logs(captured_logs: list[dict]) -> None:
    client = TestClient(app)
    resp = client.post(
        "/decide",
        json={
            "site_key": "riyadh",
            "tdb": 40.0,
            "rh": 20.0,
            "hour": 13,
            "age": 55,
            "weight_kg": 99.1,
            "height_m": 1.91,
            "has_comorbidity": True,
        },
    )
    assert resp.status_code == 200
    for ev in captured_logs:
        for banned in ("age", "weight_kg", "height_m", "has_comorbidity", "worker_id", "crew_id"):
            if banned in ev:
                assert ev[banned] == "REDACTED", ev
        dumped = json.dumps(ev, default=str)
        assert "99.1" not in dumped
        assert '"age": 55' not in dumped and "'age': 55" not in dumped


def test_redact_processor_masks_secret_like_keys() -> None:
    out = redact_processor(
        None,
        "info",
        {
            "event": "x",
            "authorization": "Bearer secret-token",
            "api_key": "abc",
            "lat": 25.0,
            "safe": "ok",
        },
    )
    assert out["authorization"] == "REDACTED"
    assert out["api_key"] == "REDACTED"
    assert out["lat"] == "REDACTED"
    assert out["safe"] == "ok"


def test_auth_deprecated_anonymous_helper_schema(captured_logs: list[dict]) -> None:
    emit_auth_deprecated_anonymous(
        route="/decide",
        origin="https://example.test",
        user_agent="pytest",
        request_id="r1",
    )
    events = _events(captured_logs, AUTH_DEPRECATED_ANONYMOUS)
    assert len(events) == 1
    for key in EXPECTED[AUTH_DEPRECATED_ANONYMOUS]:
        assert key in events[0]


def test_event_schemas_for_instrumented_paths(captured_logs: list[dict]) -> None:
    client = TestClient(app)
    client.get("/demo/dubai")
    client.post(
        "/policy/query",
        json={"question": "When does the UAE midday ban start?", "top_k": 2},
    )
    client.post(
        "/decide",
        json={"site_key": "dubai", "tdb": 36.0, "rh": 50.0, "hour": 11},
    )
    client.get("/compliance/dubai/export?fmt=csv")

    # Degraded-path / dual-mode events are schema-covered by the fixture and
    # exercised in dedicated tests — not expected on this happy-path smoke.
    skip_presence = {
        AUTH_DEPRECATED_ANONYMOUS,
        WEATHER_FIELD_SUBSTITUTED,
        POLICY_INDEX_UNAVAILABLE,
        POLICY_INDEX_BUILD_FAILED,
        RISK_MODEL_HEURISTIC_FALLBACK,
        RISK_MODEL_LOAD_FAILED,
        ENGINE_PHS_WARNING,
    }
    for name, keys in EXPECTED.items():
        if name in skip_presence:
            continue
        matched = _events(captured_logs, name)
        assert matched, f"expected at least one {name} event in {[e.get('event') for e in captured_logs]}"
        for key in keys:
            assert key in matched[0], f"{name} missing {key}: {matched[0]}"


def test_log_volume_ceiling_for_demo_compliance_summary(captured_logs: list[dict]) -> None:
    """Season-day compliance replay emits one summary append, not one per hour."""
    client = TestClient(app)
    client.get("/demo/dubai")
    appends = [
        e
        for e in _events(captured_logs, "compliance.append")
        if e.get("kind") == "season_day_summary"
    ]
    assert len(appends) == 1
    assert appends[0].get("record_count", 0) >= 1
    # weather.fetch still recorded
    assert _events(captured_logs, WEATHER_FETCH)
