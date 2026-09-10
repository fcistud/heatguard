"""structlog configuration, request context binding, and PII redaction (WO-013)."""
from __future__ import annotations

import logging
import logging.config
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

_CONFIGURED = False

# Bound per-request; deep call sites inherit without threading a logger.
_request_context: ContextVar[dict[str, Any]] = ContextVar("heatguard_request_context", default={})

# When True, ComplianceLog.append skips per-record events (season replay).
_compliance_bulk: ContextVar[bool] = ContextVar("heatguard_compliance_bulk", default=False)

_REDACT_KEYS = frozenset({
    "age",
    "weight_kg",
    "height_m",
    "has_comorbidity",
    "worker_id",
    "crew_id",
    "lat",
    "lon",
})
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|auth[_-]?token|access[_-]?token|secret|password|passwd|bearer)",
    re.IGNORECASE,
)
_REDACTED = "REDACTED"

_LEVEL_MAP = {
    "critical": "CRITICAL",
    "fatal": "CRITICAL",
    "error": "ERROR",
    "err": "ERROR",
    "warning": "WARNING",
    "warn": "WARNING",
    "info": "INFO",
    "debug": "DEBUG",
    "notset": "DEBUG",
}


def _iso_utc_timestamp(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return event_dict


def _cloud_severity(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Map structlog method name to Cloud Logging ``severity``."""
    event_dict["severity"] = _LEVEL_MAP.get(method_name.lower(), "INFO")
    # Prefer ``message`` for Cloud Logging textPayload / display.
    if "event" in event_dict and "message" not in event_dict:
        event_dict["message"] = event_dict["event"]
    return event_dict


def _merge_request_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    ctx = _request_context.get()
    for key, value in ctx.items():
        event_dict.setdefault(key, value)
    # Join active OTEL span ids when present (WO-015).
    try:
        from .tracing import current_trace_ids

        tid, sid = current_trace_ids()
        if tid:
            event_dict.setdefault("trace_id", tid)
        if sid:
            event_dict.setdefault("span_id", sid)
    except Exception:
        pass
    return event_dict


def _redact_value(key: str, value: Any) -> Any:
    if key in _REDACT_KEYS or _SECRET_KEY_RE.search(key):
        return _REDACTED
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, v) for v in value]
    return value


def redact_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Drop/mask PII and secret-like keys before rendering."""
    return {k: _redact_value(k, v) for k, v in event_dict.items()}


def configure_logging(level: str | None = None) -> None:
    """Idempotent structlog + stdlib logging setup for API/CLI."""
    global _CONFIGURED
    level_name = (level or os.environ.get("HEATGUARD_LOG_LEVEL", "INFO")).upper()
    numeric = getattr(logging, level_name, logging.INFO)

    structlog.reset_defaults()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _merge_request_context,
        _iso_utc_timestamp,
        structlog.stdlib.add_log_level,
        _cloud_severity,
        redact_processor,
    ]

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.processors.JSONRenderer(),
                    "foreign_pre_chain": shared_processors,
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                },
            },
            "loggers": {
                "": {"handlers": ["default"], "level": numeric},
                # Silence unstructured Uvicorn / httpx access lines — middleware emits http.request.
                "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": numeric, "propagate": False},
                "httpx": {"handlers": [], "level": "WARNING", "propagate": False},
                "httpcore": {"handlers": [], "level": "WARNING", "propagate": False},
            },
        }
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name or "heatguard")


def bind_request_context(**kwargs: Any) -> None:
    """Replace the request-scoped context dict (middleware entry)."""
    _request_context.set({k: v for k, v in kwargs.items() if v is not None})


def clear_request_context() -> None:
    _request_context.set({})


def current_request_id() -> str | None:
    return _request_context.get().get("request_id")


def sanitize_request_id(raw: str | None) -> str | None:
    """Return a safe ASCII request id token, or None if unsuitable to echo."""
    if not raw:
        return None
    token = str(raw).strip()
    if not token or len(token) > 128:
        return None
    # Restrict to printable ASCII token chars safe for HTTP header values.
    if not re.fullmatch(r"[A-Za-z0-9._\-:/]+", token):
        return None
    try:
        token.encode("ascii")
    except UnicodeEncodeError:
        return None
    return token


def resolve_request_id(headers: Any) -> str:
    """Honour X-Request-Id or X-Cloud-Trace-Context; else mint a UUID4.

    Inbound values are sanitized to a safe ASCII token before use/echo.
    """
    rid = None
    try:
        rid = headers.get("x-request-id") or headers.get("X-Request-Id")
    except Exception:  # noqa: BLE001
        rid = None
    cleaned = sanitize_request_id(rid)
    if cleaned:
        return cleaned
    try:
        trace = headers.get("x-cloud-trace-context") or headers.get("X-Cloud-Trace-Context")
    except Exception:  # noqa: BLE001
        trace = None
    if trace:
        # Format: TRACE_ID/SPAN_ID;o=TRACE_TRUE
        cleaned = sanitize_request_id(str(trace).split("/", 1)[0].strip())
        if cleaned:
            return cleaned
    return str(uuid4())


def compliance_bulk_mode(enabled: bool = True) -> Any:
    """Return a ContextVar token that suppresses per-append compliance events.

    Pair with ``compliance_bulk_reset(token)`` in a ``finally`` block.
    """
    return _compliance_bulk.set(enabled)


def compliance_bulk_reset(token: Any) -> None:
    _compliance_bulk.reset(token)


def in_compliance_bulk() -> bool:
    return bool(_compliance_bulk.get())


def emit_auth_deprecated_anonymous(
    *,
    route: str,
    origin: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    route_group: str | None = None,
) -> None:
    """Reserved helper for the trust-boundary epic (do not redefine elsewhere)."""
    from .events import AUTH_DEPRECATED_ANONYMOUS

    get_logger("heatguard.auth").info(
        AUTH_DEPRECATED_ANONYMOUS,
        route=route,
        origin=origin,
        user_agent=user_agent,
        request_id=request_id or current_request_id(),
        route_group=route_group,
    )
