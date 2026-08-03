"""Observability helpers — structured logging, metrics, correlation middleware."""
from __future__ import annotations

from .events import (
    AUTH_DEPRECATED_ANONYMOUS,
    COMPLIANCE_APPEND,
    COMPLIANCE_VERIFY,
    ENGINE_DECIDE,
    HTTP_REQUEST,
    POLICY_QUERY,
    WEATHER_FETCH,
)
from .logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    emit_auth_deprecated_anonymous,
    get_logger,
    resolve_request_id,
)
from .metrics import (
    observe_compression_ratio,
    observe_engine_decision,
    observe_engine_decisions_batch,
    observe_not_modified,
    observe_panel_cache,
    observe_ratelimit_rejected,
    observe_weather_fetch,
)
from .middleware import CorrelationMiddleware
from .tracing import configure_tracing, span, suppress_engine_spans

__all__ = [
    "AUTH_DEPRECATED_ANONYMOUS",
    "COMPLIANCE_APPEND",
    "COMPLIANCE_VERIFY",
    "CorrelationMiddleware",
    "ENGINE_DECIDE",
    "HTTP_REQUEST",
    "POLICY_QUERY",
    "WEATHER_FETCH",
    "bind_request_context",
    "clear_request_context",
    "configure_logging",
    "configure_tracing",
    "emit_auth_deprecated_anonymous",
    "get_logger",
    "observe_compression_ratio",
    "observe_engine_decision",
    "observe_engine_decisions_batch",
    "observe_not_modified",
    "observe_panel_cache",
    "observe_ratelimit_rejected",
    "observe_weather_fetch",
    "resolve_request_id",
    "span",
    "suppress_engine_spans",
]
