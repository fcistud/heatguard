"""OpenTelemetry tracing spans, nesting, and log correlation (WO-015)."""
from __future__ import annotations

import io
import json
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("opentelemetry")

import structlog
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace import StatusCode

from heatguard._paths import _REPO_ROOT
from heatguard.api import app
from heatguard.observability import configure_logging, get_logger
from heatguard.observability import logging as obs_logging
from heatguard.observability import tracing as t
from heatguard.observability.tracing import (
    FORBIDDEN_SPAN_ATTRS,
    current_trace_ids,
    force_reconfigure,
    reset_tracing_for_tests,
    sample_ratio,
    span,
)

FIXTURE = json.loads(
    (_REPO_ROOT / "tests" / "fixtures" / "tracing" / "expected_span_tree.json").read_text()
)


@pytest.fixture
def memory_tracer(monkeypatch):
    monkeypatch.setenv("HEATGUARD_ENV", "test")
    monkeypatch.setenv("HEATGUARD_TRACE_SAMPLE_RATIO", "1.0")
    monkeypatch.setenv("HEATGUARD_TRACE_EXPORTER", "none")
    monkeypatch.setenv("HEATGUARD_TRACE_SIMPLE", "1")
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    force_reconfigure()
    # Re-bind FastAPI middleware to this provider — import-time instrumentation
    # otherwise keeps a tracer from the process-global provider (often 5% sampled).
    reset_tracing_for_tests(provider, app=app)
    yield exporter, provider
    exporter.clear()


def _by_name(spans):
    out: dict[str, list] = {}
    for s in spans:
        out.setdefault(s.name, []).append(s)
    return out


def test_sample_ratio_defaults(monkeypatch) -> None:
    monkeypatch.delenv("HEATGUARD_TRACE_SAMPLE_RATIO", raising=False)
    monkeypatch.setenv("HEATGUARD_ENV", "production")
    assert sample_ratio() == 0.05
    monkeypatch.setenv("HEATGUARD_ENV", "dev")
    assert sample_ratio() == 1.0
    monkeypatch.setenv("HEATGUARD_TRACE_SAMPLE_RATIO", "0.25")
    assert sample_ratio() == 0.25


def test_forbidden_attrs_constant_matches_fixture() -> None:
    assert FORBIDDEN_SPAN_ATTRS == frozenset(FIXTURE["forbidden_attribute_keys"])


def test_engine_spans_suppressed_in_bulk(memory_tracer) -> None:
    exporter, _ = memory_tracer
    with span("outer"):
        with t.suppress_engine_spans():
            with span("engine.decide"):
                pass
            with span("engine.phs"):
                pass
        with span("engine.decide"):
            pass
    names = [s.name for s in exporter.get_finished_spans()]
    assert names.count("engine.decide") == 1
    assert "engine.phs" not in names
    assert "outer" in names


def test_span_records_exception(memory_tracer) -> None:
    exporter, _ = memory_tracer
    with pytest.raises(ValueError):
        with span("boom.path"):
            raise ValueError("explode")
    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    sp = finished[0]
    assert sp.status.status_code == StatusCode.ERROR
    assert sp.attributes.get("exception.type") == "ValueError"


def test_log_trace_correlation(memory_tracer) -> None:
    exporter, _ = memory_tracer
    entries: list[dict[str, Any]] = []

    def _capture(logger, method_name, event_dict):
        entries.append(dict(event_dict))
        return event_dict

    sink = io.StringIO()
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            obs_logging._merge_request_context,
            _capture,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(file=sink),
        cache_logger_on_first_use=False,
    )
    try:
        with span("log.corr"):
            tid, sid = current_trace_ids()
            get_logger("heatguard.test").info("corr.probe", marker=True)
        assert entries, "expected a captured log event"
        ev = entries[-1]
        assert ev.get("trace_id") == tid
        assert ev.get("span_id") == sid
        assert tid and sid
    finally:
        sink.close()
        configure_logging(level="INFO")


def test_health_and_metrics_excluded(memory_tracer, monkeypatch) -> None:
    exporter, _ = memory_tracer
    monkeypatch.setenv("HEATGUARD_METRICS_ENABLED", "1")
    client = TestClient(app)
    exporter.clear()
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.get("/metrics").status_code == 200
    # FastAPI auto-instrumentation must not create spans for excluded URLs.
    http_spans = [
        s for s in exporter.get_finished_spans() if s.name.startswith("GET")
    ]
    assert http_spans == []


def test_demo_span_tree_matches_fixture(memory_tracer) -> None:
    exporter, _ = memory_tracer
    from heatguard.service import _season_hourly

    _season_hourly.cache_clear()
    client = TestClient(app)
    exporter.clear()
    resp = client.get("/demo/dubai")
    assert resp.status_code == 200

    spans = list(exporter.get_finished_spans())
    names = {s.name for s in spans}
    for required in FIXTURE["required_span_names"]:
        assert required in names, f"missing span {required}; got {sorted(names)}"

    by_name = _by_name(spans)

    # Nesting: required children must be descendants of build_demo.
    build = by_name["service.build_demo"][0]
    descendants: set[str] = set()

    def walk(span_id: int, depth: int = 0) -> None:
        if depth > 12:
            return
        for s in spans:
            if s.parent and s.parent.span_id == span_id:
                descendants.add(s.name)
                walk(s.context.span_id, depth + 1)

    walk(build.context.span_id)
    for child in FIXTURE["nesting"]["service.build_demo"]:
        assert child in descendants, (
            f"expected {child} under build_demo; descendants={sorted(descendants)}"
        )

    # Per-hour engine spans must not nest under season_replay.
    season_ids = {s.context.span_id for s in by_name["service.season_replay"]}
    forbidden = set(FIXTURE["forbidden_children_of"]["service.season_replay"])
    for s in spans:
        if s.parent and s.parent.span_id in season_ids and s.name in forbidden:
            pytest.fail(f"{s.name} nested under service.season_replay")

    # Required attributes + no forbidden keys anywhere.
    for span_name, keys in FIXTURE["required_attributes"].items():
        assert by_name[span_name], f"no spans named {span_name}"
        attrs = dict(by_name[span_name][0].attributes or {})
        for key in keys:
            assert key in attrs, f"{span_name} missing {key}"

    for s in spans:
        keys = set((s.attributes or {}).keys())
        bad = keys & set(FIXTURE["forbidden_attribute_keys"])
        assert not bad, f"{s.name} has forbidden attrs {bad}"


def test_weather_timeout_marks_span_error(memory_tracer, monkeypatch) -> None:
    exporter, _ = memory_tracer
    from datetime import date

    from heatguard.sites import get_site
    from heatguard.weather import openmeteo

    site = get_site("dubai")

    def boom(*args, **kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(httpx.TimeoutException):
        openmeteo.fetch_archive(
            site,
            date(2025, 5, 1),
            date(2025, 5, 2),
            use_cache=False,
            refresh=True,
        )
    finished = [s for s in exporter.get_finished_spans() if s.name == "weather.fetch_archive"]
    assert finished
    assert finished[-1].status.status_code == StatusCode.ERROR
    assert finished[-1].attributes.get("exception.type") == "TimeoutException"


def test_cloud_trace_propagator_extracts(memory_tracer) -> None:
    from opentelemetry import trace as otel_trace
    from opentelemetry.propagate import extract

    t._install_propagators()
    # SPAN_ID is decimal per Google Cloud Trace header format.
    carrier = {"x-cloud-trace-context": "4bf92f3577b34da6a3ce929d0e0e4736/123;o=1"}
    ctx = extract(carrier)
    span_ctx = otel_trace.get_current_span(ctx).get_span_context()
    assert span_ctx.is_valid
    assert format(span_ctx.trace_id, "032x") == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert span_ctx.span_id == 123


def test_policy_retrieve_span(memory_tracer) -> None:
    exporter, _ = memory_tracer
    from heatguard.policy_rag import retrieve

    retrieve("What is the UAE midday ban?")
    names = {s.name for s in exporter.get_finished_spans()}
    assert "policy.retrieve" in names
    sp = [s for s in exporter.get_finished_spans() if s.name == "policy.retrieve"][0]
    assert "heatguard.rows" in dict(sp.attributes or {})


def test_forecast_timeline_span(memory_tracer) -> None:
    exporter, _ = memory_tracer
    from heatguard.service import forecast_timeline

    try:
        forecast_timeline("dubai")
    except Exception as exc:  # network/cache may fail offline
        spans = [s for s in exporter.get_finished_spans() if s.name == "service.forecast_timeline"]
        if not spans:
            pytest.skip(f"forecast unavailable offline: {exc}")
        return
    spans = [s for s in exporter.get_finished_spans() if s.name == "service.forecast_timeline"]
    assert spans
    attrs = dict(spans[0].attributes or {})
    assert attrs.get("heatguard.site_key") == "dubai"
    assert "heatguard.horizon_hours" in attrs
