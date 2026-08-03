"""OpenTelemetry tracing configuration and span helpers (WO-015).

Sampling defaults: 1.0 when ``HEATGUARD_ENV`` is ``dev``/``test``, else 0.05.
Exporter selected by ``HEATGUARD_TRACE_EXPORTER``: ``console`` | ``otlp`` | ``none``.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from opentelemetry.trace import Span, Status, StatusCode, SpanContext, TraceFlags
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagators.textmap import (
    DefaultGetter,
    DefaultSetter,
    Getter,
    Setter,
    TextMapPropagator,
)

_CONFIGURED = False
_TRACER_NAME = "heatguard"

# Season replay iterates thousands of hours — suppress per-hour engine spans.
_suppress_engine: ContextVar[bool] = ContextVar(
    "heatguard_suppress_engine_spans", default=False
)

# Attribute keys (documented contract) — never worker PII / coordinates.
ATTR_SITE_KEY = "heatguard.site_key"
ATTR_WBGT_SOURCE = "heatguard.wbgt_source"
ATTR_SIGNAL = "heatguard.signal"
ATTR_ROWS = "heatguard.rows"
ATTR_CACHE_HIT = "heatguard.cache_hit"
ATTR_HORIZON_HOURS = "heatguard.horizon_hours"

FORBIDDEN_SPAN_ATTRS = frozenset({
    "age",
    "weight_kg",
    "height_m",
    "has_comorbidity",
    "worker_id",
    "lat",
    "lon",
    "heatguard.age",
    "heatguard.weight_kg",
    "heatguard.height_m",
    "heatguard.has_comorbidity",
    "heatguard.worker_id",
    "heatguard.lat",
    "heatguard.lon",
})

EXCLUDED_URLS = (
    "/health",
    "/health/live",
    "/health/ready",
    "/metrics",
)


def _env_name() -> str:
    return os.environ.get("HEATGUARD_ENV", "").strip().lower()


def sample_ratio() -> float:
    raw = os.environ.get("HEATGUARD_TRACE_SAMPLE_RATIO")
    if raw is not None and raw.strip() != "":
        try:
            return max(0.0, min(1.0, float(raw)))
        except ValueError:
            return 0.05
    if _env_name() in ("dev", "test", "development", "testing"):
        return 1.0
    return 0.05


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_TRACER_NAME)


def _build_exporter():
    mode = os.environ.get("HEATGUARD_TRACE_EXPORTER", "console").strip().lower()
    if mode in ("", "none", "off", "disabled"):
        return None
    if mode == "console":
        return ConsoleSpanExporter()
    if mode in ("otlp", "cloud_trace", "cloud_monitoring"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter()
    # Unknown → console so local misconfig still emits something visible.
    return ConsoleSpanExporter()


class _CloudTraceContextPropagator(TextMapPropagator):
    """Extract/inject Google ``X-Cloud-Trace-Context`` (TRACE_ID/SPAN_ID;o=1)."""

    _HEADER = "x-cloud-trace-context"

    def extract(
        self,
        carrier: Any,
        context: Context | None = None,
        getter: Getter[Any] = DefaultGetter(),
    ) -> Context:
        ctx = context or Context()
        values = getter.get(carrier, self._HEADER)
        if not values:
            return ctx
        raw = values[0]
        try:
            trace_span, _, opts = raw.partition(";")
            trace_id_s, _, span_id_s = trace_span.partition("/")
            if len(trace_id_s) != 32:
                return ctx
            trace_id = int(trace_id_s, 16)
            # GCP X-Cloud-Trace-Context SPAN_ID is a decimal uint64, not hex.
            if not span_id_s:
                return ctx
            span_id = int(span_id_s, 10)
            if span_id == 0:
                return ctx
            sampled = "o=1" in opts.replace(" ", "").lower()
            sc = SpanContext(
                trace_id=trace_id,
                span_id=span_id,
                is_remote=True,
                trace_flags=TraceFlags(0x01 if sampled else 0x00),
            )
            if not sc.is_valid:
                return ctx
            return trace.set_span_in_context(trace.NonRecordingSpan(sc), ctx)
        except (ValueError, TypeError):
            return ctx

    def inject(
        self,
        carrier: Any,
        context: Context | None = None,
        setter: Setter[Any] = DefaultSetter(),
    ) -> None:
        span = trace.get_current_span(context)
        sc = span.get_span_context()
        if not sc or not sc.is_valid:
            return
        o = 1 if sc.trace_flags.sampled else 0
        setter.set(
            carrier,
            self._HEADER,
            # Trace id hex; span id decimal (Cloud Trace wire format).
            f"{format(sc.trace_id, '032x')}/{sc.span_id};o={o}",
        )

    @property
    def fields(self) -> set[str]:
        return {self._HEADER}


def _install_propagators() -> None:
    set_global_textmap(
        CompositePropagator(
            [TraceContextTextMapPropagator(), _CloudTraceContextPropagator()]
        )
    )


def configure_tracing(app: Any | None = None) -> TracerProvider | None:
    """Idempotent TracerProvider setup; optionally instrument FastAPI + httpx."""
    global _CONFIGURED
    if _CONFIGURED:
        if app is not None:
            _instrument_app(app)
        return trace.get_tracer_provider()  # type: ignore[return-value]

    ratio = sample_ratio()
    resource = Resource.create({
        "service.name": os.environ.get("HEATGUARD_SERVICE_NAME", "heatguard"),
        "service.version": "0.1.0",
    })
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBasedTraceIdRatio(ratio),
    )
    exporter = _build_exporter()
    if exporter is not None:
        # Bounded batch processor — backpressure drops rather than blocking requests.
        if os.environ.get("HEATGUARD_TRACE_SIMPLE", "").lower() in ("1", "true", "yes"):
            provider.add_span_processor(SimpleSpanProcessor(exporter))
        else:
            provider.add_span_processor(
                BatchSpanProcessor(
                    exporter,
                    max_queue_size=2048,
                    max_export_batch_size=256,
                    schedule_delay_millis=5000,
                )
            )
    trace.set_tracer_provider(provider)
    _install_propagators()
    _CONFIGURED = True

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception:
        pass

    if app is not None:
        _instrument_app(app)

    return provider


def _instrument_app(app: Any, *, force: bool = False, tracer_provider: Any = None) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        already = getattr(app, "state", None) is not None and getattr(
            app.state, "_heatguard_otel", False
        )
        if already and not force:
            return
        if already:
            try:
                FastAPIInstrumentor.uninstrument_app(app)
            except Exception:
                pass
            if getattr(app, "state", None) is not None:
                app.state._heatguard_otel = False
        kwargs: dict[str, Any] = {"excluded_urls": ",".join(EXCLUDED_URLS)}
        if tracer_provider is not None:
            kwargs["tracer_provider"] = tracer_provider
        FastAPIInstrumentor.instrument_app(app, **kwargs)
        if getattr(app, "state", None) is not None:
            app.state._heatguard_otel = True
    except Exception:
        try:
            from .logging import get_logger

            get_logger("heatguard.tracing").error(
                "tracing.export_failed",
                message="FastAPI instrumentation failed",
            )
        except Exception:
            pass


def reset_tracing_for_tests(
    provider: TracerProvider | None = None,
    app: Any | None = None,
) -> None:
    """Replace the global provider and re-bind FastAPI instrumentation (tests).

    OpenTelemetry's ``set_tracer_provider`` is once-only, and FastAPI
    instrumentation caches a tracer at instrument time — so tests must both
    assign the private provider attribute and force re-instrumentation.
    """
    global _CONFIGURED
    if provider is None:
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON

        provider = TracerProvider(sampler=ALWAYS_ON)

    old = trace.get_tracer_provider()
    if old is not None and old is not provider and hasattr(old, "shutdown"):
        try:
            old.shutdown()
        except Exception:
            pass

    # Bypass Once-guard — required for pytest isolation.
    trace._TRACER_PROVIDER = provider  # noqa: SLF001
    _CONFIGURED = True
    if app is not None:
        _instrument_app(app, force=True, tracer_provider=provider)


def force_reconfigure() -> None:
    """Allow configure_tracing to run again (tests)."""
    global _CONFIGURED
    _CONFIGURED = False


@contextmanager
def suppress_engine_spans() -> Iterator[None]:
    """Disable ``engine.*`` spans (season replay must not emit per-hour trees)."""
    token = _suppress_engine.set(True)
    try:
        yield
    finally:
        _suppress_engine.reset(token)


def engine_spans_suppressed() -> bool:
    return bool(_suppress_engine.get())


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span | None]:
    """Open a named span; never propagate tracing failures into the caller."""
    if name.startswith("engine.") and _suppress_engine.get():
        yield None
        return

    try:
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span(name)
        sp = span_cm.__enter__()
    except Exception:
        yield None
        return

    try:
        for key, value in attributes.items():
            if key in FORBIDDEN_SPAN_ATTRS or value is None:
                continue
            try:
                sp.set_attribute(key, value)
            except Exception:
                pass
        try:
            yield sp
        except Exception as exc:
            try:
                sp.record_exception(exc)
                sp.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
                sp.set_attribute("exception.type", type(exc).__name__)
            except Exception:
                pass
            raise
    finally:
        try:
            import sys

            span_cm.__exit__(*sys.exc_info())
        except Exception:
            pass


def set_attrs(sp: Span | None, **attributes: Any) -> None:
    if sp is None:
        return
    for key, value in attributes.items():
        if key in FORBIDDEN_SPAN_ATTRS or value is None:
            continue
        try:
            sp.set_attribute(key, value)
        except Exception:
            pass


def current_trace_ids() -> tuple[str | None, str | None]:
    """Return (trace_id, span_id) hex strings for the active span, if any."""
    try:
        ctx = trace.get_current_span().get_span_context()
        if not ctx or not ctx.is_valid:
            return None, None
        return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
    except Exception:
        return None, None
