"""Prometheus SLI registry and typed observation helpers (WO-014).

Uses a single explicit ``CollectorRegistry`` (not the global default) so tests can
reset cleanly. The container runs uvicorn with ``--workers 1``; raising the worker
count without ``PROMETHEUS_MULTIPROC_DIR`` would under-report — see
``docs/OBSERVABILITY.md``.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Iterable

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

# Forbidden label names — cardinality / PII guard (tested).
FORBIDDEN_LABELS = frozenset({
    "day",
    "date",
    "hour",
    "crew",
    "worker_id",
    "request_id",
    "ip",
    "user_agent",
})

_DURATION_BUCKETS = (0.005, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_BYTES_BUCKETS = (
    64,
    256,
    1024,
    4096,
    16384,
    65536,
    262144,
    1_048_576,
    4_194_304,
)
_COMPRESSION_BUCKETS = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 15.0, 20.0)
_WEATHER_DURATION_BUCKETS = (0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 60.0, 90.0)

_lock = threading.Lock()
_registry: CollectorRegistry | None = None
_instrumentation_errors_logged: set[str] = set()

# Metric objects rebound on ``reset_registry()``.
http_requests_total: Counter
http_request_duration_seconds: Histogram
http_response_bytes: Histogram
panel_cache_events_total: Counter
http_not_modified_total: Counter
response_compression_ratio: Histogram
weather_fetch_total: Counter
weather_fetch_duration_seconds: Histogram
compliance_chain_verify_total: Counter
compliance_records_appended_total: Counter
engine_decisions_total: Counter
wbgt_source_total: Counter
wbgt_path_total: Counter
weather_field_substituted_total: Counter
risk_model_fallback_total: Counter
degraded_conditions_total: Counter
ratelimit_rejected_total: Counter
ratelimit_would_reject_total: Counter
quota_bucket_evicted_total: Counter
quota_store_breaker_open: Gauge
auth_outcome_total: Counter
process_start_duration_seconds: Gauge


def metrics_enabled() -> bool:
    return os.environ.get("HEATGUARD_METRICS_ENABLED", "").lower() in ("1", "true", "yes")


def _safe(metric_name: str, fn: Any) -> None:
    """Never let metrics failures affect the request path."""
    try:
        fn()
    except Exception:
        if metric_name not in _instrumentation_errors_logged:
            _instrumentation_errors_logged.add(metric_name)
            try:
                from .logging import get_logger

                get_logger("heatguard.metrics").error(
                    "metrics.instrumentation_error",
                    metric=metric_name,
                    message=f"instrumentation failed for {metric_name}",
                )
            except Exception:
                pass


def _register(registry: CollectorRegistry) -> None:
    global http_requests_total, http_request_duration_seconds, http_response_bytes
    global panel_cache_events_total, http_not_modified_total, response_compression_ratio
    global weather_fetch_total, weather_fetch_duration_seconds
    global compliance_chain_verify_total, compliance_records_appended_total
    global engine_decisions_total, wbgt_source_total, ratelimit_rejected_total
    global ratelimit_would_reject_total, quota_bucket_evicted_total
    global quota_store_breaker_open
    global wbgt_path_total, weather_field_substituted_total
    global risk_model_fallback_total, degraded_conditions_total
    global process_start_duration_seconds, auth_outcome_total

    http_requests_total = Counter(
        "heatguard_http_requests_total",
        "HTTP requests by route template, method, and status class",
        ["route", "method", "status_class"],
        registry=registry,
    )
    http_request_duration_seconds = Histogram(
        "heatguard_http_request_duration_seconds",
        "HTTP request latency in seconds (buckets tuned to 500 ms p95)",
        ["route"],
        buckets=_DURATION_BUCKETS,
        registry=registry,
    )
    http_response_bytes = Histogram(
        "heatguard_http_response_bytes",
        "HTTP response body size in bytes",
        ["route"],
        buckets=_BYTES_BUCKETS,
        registry=registry,
    )
    panel_cache_events_total = Counter(
        "heatguard_panel_cache_events_total",
        "Panel cache outcomes (hit / miss / stale)",
        ["panel", "result"],
        registry=registry,
    )
    http_not_modified_total = Counter(
        "heatguard_http_not_modified_total",
        "HTTP 304 Not Modified responses by route template",
        ["route"],
        registry=registry,
    )
    response_compression_ratio = Histogram(
        "heatguard_response_compression_ratio",
        "Uncompressed/compressed size ratio (1.0 when gzip not applied)",
        buckets=_COMPRESSION_BUCKETS,
        registry=registry,
    )
    weather_fetch_total = Counter(
        "heatguard_weather_fetch_total",
        "Weather ingest outcomes",
        ["site_key", "source", "outcome"],
        registry=registry,
    )
    weather_fetch_duration_seconds = Histogram(
        "heatguard_weather_fetch_duration_seconds",
        "Weather fetch wall time by source",
        ["source"],
        buckets=_WEATHER_DURATION_BUCKETS,
        registry=registry,
    )
    compliance_chain_verify_total = Counter(
        "heatguard_compliance_chain_verify_total",
        "Compliance chain verification results",
        ["site_key", "result"],
        registry=registry,
    )
    compliance_records_appended_total = Counter(
        "heatguard_compliance_records_appended_total",
        "Compliance records appended",
        ["site_key", "kind"],
        registry=registry,
    )
    engine_decisions_total = Counter(
        "heatguard_engine_decisions_total",
        "Scheduler decisions by signal",
        ["signal"],
        registry=registry,
    )
    wbgt_source_total = Counter(
        "heatguard_wbgt_source_total",
        "WBGT provenance mix",
        ["source"],
        registry=registry,
    )
    wbgt_path_total = Counter(
        "heatguard_wbgt_path_total",
        "WBGT computation path selected (liljegren / fallback branches)",
        ["path"],
        registry=registry,
    )
    weather_field_substituted_total = Counter(
        "heatguard_weather_field_substituted_total",
        "Null Open-Meteo fields replaced with conservative defaults",
        ["field"],
        registry=registry,
    )
    risk_model_fallback_total = Counter(
        "heatguard_risk_model_fallback_total",
        "Personal-risk assessments served by the heuristic fallback",
        registry=registry,
    )
    degraded_conditions_total = Counter(
        "heatguard_degraded_conditions_total",
        "Degraded-mode reports by stable reason code",
        ["reason_code"],
        registry=registry,
    )
    ratelimit_rejected_total = Counter(
        "heatguard_ratelimit_rejected_total",
        "Rate-limit rejections by route and key class",
        ["route", "key_class"],
        registry=registry,
    )
    ratelimit_would_reject_total = Counter(
        "heatguard_ratelimit_would_reject_total",
        "Would-be rate-limit rejections counted in observe-only mode (WO-007)",
        ["route", "key_class"],
        registry=registry,
    )
    quota_bucket_evicted_total = Counter(
        "heatguard_quota_bucket_evicted_total",
        "In-process quota buckets evicted by the LRU cap (WO-007)",
        registry=registry,
    )
    quota_store_breaker_open = Gauge(
        "heatguard_quota_store_breaker_open",
        "1 when the shared quota store breaker is open (WO-008)",
        registry=registry,
    )
    auth_outcome_total = Counter(
        "heatguard_auth_outcome_total",
        "Authentication outcomes by endpoint group and key class (WO-005)",
        ["route_group", "key_class", "outcome"],
        registry=registry,
    )
    process_start_duration_seconds = Gauge(
        "heatguard_process_start_duration_seconds",
        "Cold-start warm-up duration (lifespan) once per process",
        registry=registry,
    )


def get_registry() -> CollectorRegistry:
    global _registry
    with _lock:
        if _registry is None:
            _registry = CollectorRegistry()
            _register(_registry)
        return _registry


def reset_registry() -> CollectorRegistry:
    """Replace the process registry (tests). Clears one-shot error log state."""
    global _registry, _instrumentation_errors_logged
    with _lock:
        _registry = CollectorRegistry()
        _register(_registry)
        _instrumentation_errors_logged = set()
        return _registry


# Ensure metrics exist at import for helpers and cardinality tests.
get_registry()


def status_class(status_code: int) -> str:
    return f"{int(status_code) // 100}xx"


def observe_http_request(
    *,
    route: str,
    method: str,
    status_code: int,
    duration_seconds: float,
    response_bytes: int,
    content_encoding: str | None = None,
    uncompressed_bytes: int | None = None,
) -> None:
    """Record request SLIs. Skips byte/compression samples when size is unknown/zero."""

    def _do() -> None:
        get_registry()
        sc = status_class(status_code)
        http_requests_total.labels(route=route, method=method, status_class=sc).inc()
        http_request_duration_seconds.labels(route=route).observe(duration_seconds)
        if response_bytes > 0:
            http_response_bytes.labels(route=route).observe(float(response_bytes))
            # Without gzip middleware, ratio is 1.0; with gzip, use uncompressed/compressed.
            if uncompressed_bytes is not None and uncompressed_bytes > 0 and response_bytes > 0:
                ratio = uncompressed_bytes / response_bytes
            elif content_encoding and "gzip" in content_encoding.lower():
                # Compressed but no pre-size — skip rather than invent a ratio.
                ratio = None
            else:
                ratio = 1.0
            if ratio is not None:
                response_compression_ratio.observe(ratio)
        if status_code == 304:
            http_not_modified_total.labels(route=route).inc()

    _safe("heatguard_http_requests_total", _do)


def observe_panel_cache(panel: str, result: str) -> None:
    """Increment panel cache SLI. ``result`` must be hit|miss|stale."""

    def _do() -> None:
        get_registry()
        if result not in ("hit", "miss", "stale"):
            raise ValueError(f"invalid panel cache result: {result}")
        panel_cache_events_total.labels(panel=panel, result=result).inc()

    _safe("heatguard_panel_cache_events_total", _do)


def observe_not_modified(route: str) -> None:
    """Helper for the caching epic when 304 is decided outside middleware."""

    def _do() -> None:
        get_registry()
        http_not_modified_total.labels(route=route).inc()

    _safe("heatguard_http_not_modified_total", _do)


def observe_compression_ratio(ratio: float) -> None:
    """Helper for the caching epic when compression is measured at serialize time."""

    def _do() -> None:
        get_registry()
        if ratio > 0:
            response_compression_ratio.observe(ratio)

    _safe("heatguard_response_compression_ratio", _do)


def observe_weather_fetch(
    *,
    site_key: str,
    source: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    def _do() -> None:
        get_registry()
        weather_fetch_total.labels(
            site_key=site_key, source=source, outcome=outcome
        ).inc()
        weather_fetch_duration_seconds.labels(source=source).observe(duration_seconds)

    _safe("heatguard_weather_fetch_total", _do)


def observe_compliance_append(*, site_key: str, kind: str) -> None:
    def _do() -> None:
        get_registry()
        compliance_records_appended_total.labels(site_key=site_key, kind=kind).inc()

    _safe("heatguard_compliance_records_appended_total", _do)


def observe_compliance_verify(*, site_key: str, ok: bool) -> None:
    def _do() -> None:
        get_registry()
        result = "ok" if ok else "failed"
        compliance_chain_verify_total.labels(site_key=site_key, result=result).inc()

    _safe("heatguard_compliance_chain_verify_total", _do)


def observe_engine_decision(*, signal: str, wbgt_source: str, amount: float = 1.0) -> None:
    def _do() -> None:
        get_registry()
        engine_decisions_total.labels(signal=signal).inc(amount)
        wbgt_source_total.labels(source=wbgt_source).inc(amount)

    _safe("heatguard_engine_decisions_total", _do)


def observe_engine_decisions_batch(
    pairs: Iterable[tuple[str, str]],
) -> None:
    """Aggregate season-replay decisions into one increment per label combo."""
    from collections import Counter

    counts: Counter[tuple[str, str]] = Counter(pairs)

    def _do() -> None:
        get_registry()
        for (signal, source), n in counts.items():
            engine_decisions_total.labels(signal=signal).inc(n)
            wbgt_source_total.labels(source=source).inc(n)

    _safe("heatguard_engine_decisions_total", _do)


def observe_wbgt_path(*, path: str) -> None:
    def _do() -> None:
        get_registry()
        wbgt_path_total.labels(path=path).inc()

    _safe("heatguard_wbgt_path_total", _do)


def observe_weather_field_substituted(*, field: str, count: float = 1.0) -> None:
    def _do() -> None:
        get_registry()
        weather_field_substituted_total.labels(field=field).inc(count)

    _safe("heatguard_weather_field_substituted_total", _do)


def observe_risk_model_fallback() -> None:
    def _do() -> None:
        get_registry()
        risk_model_fallback_total.inc()

    _safe("heatguard_risk_model_fallback_total", _do)


def observe_degraded_condition(*, reason_code: str) -> None:
    def _do() -> None:
        get_registry()
        degraded_conditions_total.labels(reason_code=reason_code).inc()

    _safe("heatguard_degraded_conditions_total", _do)


def observe_ratelimit_rejected(*, route: str, key_class: str) -> None:
    """Public helper for the trust-boundary epic (contract declared here)."""

    def _do() -> None:
        get_registry()
        ratelimit_rejected_total.labels(route=route, key_class=key_class).inc()

    _safe("heatguard_ratelimit_rejected_total", _do)


def observe_ratelimit_would_reject(*, route: str, key_class: str) -> None:
    """Count observe-only over-limit events. Labels stay bounded — never origin."""

    def _do() -> None:
        get_registry()
        ratelimit_would_reject_total.labels(route=route, key_class=key_class).inc()

    _safe("heatguard_ratelimit_would_reject_total", _do)


def observe_quota_bucket_evicted() -> None:
    """Count LRU evictions of in-process quota buckets."""

    def _do() -> None:
        get_registry()
        quota_bucket_evicted_total.inc()

    _safe("heatguard_quota_bucket_evicted_total", _do)


def observe_quota_store_breaker(*, open_: bool) -> None:
    """Breaker open=1 / closed=0. Bounded — never labels the Redis URL."""

    def _do() -> None:
        get_registry()
        quota_store_breaker_open.set(1.0 if open_ else 0.0)

    _safe("heatguard_quota_store_breaker_open", _do)


def observe_auth_outcome(
    *,
    route_group: str,
    key_class: str,
    outcome: str,
) -> None:
    """Count dual/enforce outcomes. Labels stay bounded — never path or principal."""

    def _do() -> None:
        get_registry()
        auth_outcome_total.labels(
            route_group=route_group,
            key_class=key_class,
            outcome=outcome,
        ).inc()

    _safe("heatguard_auth_outcome_total", _do)


def record_process_start_duration(seconds: float) -> None:
    def _do() -> None:
        get_registry()
        process_start_duration_seconds.set(seconds)

    _safe("heatguard_process_start_duration_seconds", _do)


def render_prometheus() -> bytes:
    return generate_latest(get_registry())


def registered_metric_label_names() -> dict[str, frozenset[str]]:
    """Contract map of metric name -> label names for the cardinality guard.

    Declared (not sample-derived) so unobserved series still appear and
    prometheus histogram ``le`` sample labels never leak into the guard.
    """
    return {
        "heatguard_http_requests_total": frozenset({"route", "method", "status_class"}),
        "heatguard_http_request_duration_seconds": frozenset({"route"}),
        "heatguard_http_response_bytes": frozenset({"route"}),
        "heatguard_panel_cache_events_total": frozenset({"panel", "result"}),
        "heatguard_http_not_modified_total": frozenset({"route"}),
        "heatguard_response_compression_ratio": frozenset(),
        "heatguard_weather_fetch_total": frozenset({"site_key", "source", "outcome"}),
        "heatguard_weather_fetch_duration_seconds": frozenset({"source"}),
        "heatguard_compliance_chain_verify_total": frozenset({"site_key", "result"}),
        "heatguard_compliance_records_appended_total": frozenset({"site_key", "kind"}),
        "heatguard_engine_decisions_total": frozenset({"signal"}),
        "heatguard_wbgt_source_total": frozenset({"source"}),
        "heatguard_wbgt_path_total": frozenset({"path"}),
        "heatguard_weather_field_substituted_total": frozenset({"field"}),
        "heatguard_risk_model_fallback_total": frozenset(),
        "heatguard_degraded_conditions_total": frozenset({"reason_code"}),
        "heatguard_ratelimit_rejected_total": frozenset({"route", "key_class"}),
        "heatguard_ratelimit_would_reject_total": frozenset({"route", "key_class"}),
        "heatguard_quota_bucket_evicted_total": frozenset(),
        "heatguard_quota_store_breaker_open": frozenset(),
        "heatguard_auth_outcome_total": frozenset({"route_group", "key_class", "outcome"}),
        "heatguard_process_start_duration_seconds": frozenset(),
    }


def warn_if_multiprocess_unconfigured() -> None:
    workers = os.environ.get("WEB_CONCURRENCY") or os.environ.get("UVICORN_WORKERS") or "1"
    try:
        n = int(workers)
    except ValueError:
        n = 1
    if n > 1 and not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        try:
            from .logging import get_logger

            get_logger("heatguard.metrics").warning(
                "metrics.multiprocess_unconfigured",
                workers=n,
                message=(
                    "Metrics are per-process only; set PROMETHEUS_MULTIPROC_DIR "
                    "or keep --workers 1 (docker-entrypoint.sh)."
                ),
            )
        except Exception:
            pass


def maybe_configure_export() -> None:
    """Optional Cloud Monitoring / OTLP export flag (scrape remains primary)."""
    mode = os.environ.get("HEATGUARD_METRICS_EXPORT", "").strip().lower()
    if not mode:
        return
    try:
        from .logging import get_logger

        get_logger("heatguard.metrics").info(
            "metrics.export_configured",
            mode=mode,
            message="HEATGUARD_METRICS_EXPORT set; scrape private GET /metrics as primary surface",
        )
    except Exception:
        pass
