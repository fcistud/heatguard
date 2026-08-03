"""Observability helpers — structured logging, events, correlation middleware."""
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
from .middleware import CorrelationMiddleware

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
    "emit_auth_deprecated_anonymous",
    "get_logger",
    "resolve_request_id",
]
