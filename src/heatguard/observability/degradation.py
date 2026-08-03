"""Process-level degradation registry (WO-016).

Stable reason codes feed ``GET /health/ready``'s ``degraded`` array without ever
escalating to ``not_ready`` / 503. Reporting is failure-proof and deduplicated
so season-replay loops cannot flood logs.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

# Stable readiness reason codes (alerting keys off these strings).
WBGT_FALLBACK_ACTIVE = "wbgt_fallback_active"
WEATHER_FIELDS_SUBSTITUTED = "weather_fields_substituted"
POLICY_INDEX_UNAVAILABLE = "policy_index_unavailable"
RISK_MODEL_HEURISTIC = "risk_model_heuristic"

REASON_CODES: frozenset[str] = frozenset({
    WBGT_FALLBACK_ACTIVE,
    WEATHER_FIELDS_SUBSTITUTED,
    POLICY_INDEX_UNAVAILABLE,
    RISK_MODEL_HEURISTIC,
})

# Structured event names.
WBGT_PATH_SELECTED = "wbgt.path_selected"
WEATHER_FIELD_SUBSTITUTED = "weather.field_substituted"
POLICY_INDEX_UNAVAILABLE_EVENT = "policy.index_unavailable"
RISK_MODEL_HEURISTIC_FALLBACK = "risk_model.heuristic_fallback"
ENGINE_PHS_WARNING = "engine.phs_warning"
DEGRADATION_REPORTING_FAILED = "degradation.reporting_failed"

_DEFAULT_TTL_SECONDS = 300.0

_lock = threading.Lock()
_active: dict[str, "_Entry"] = {}
_logged_once: set[str] = set()
_reporting_failed_logged = False


@dataclass
class _Entry:
    code: str
    detail: str
    expires_at: float


def _ttl() -> float:
    import os

    raw = os.environ.get("HEATGUARD_DEGRADATION_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS))
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_TTL_SECONDS


def clear_degradation_state() -> None:
    """Test helper — wipe snapshot and one-shot log keys."""
    global _reporting_failed_logged
    with _lock:
        _active.clear()
        _logged_once.clear()
        _reporting_failed_logged = False


def active_reason_codes(*, now: float | None = None) -> list[str]:
    """Return non-expired degradation codes (sorted, stable)."""
    t = time.monotonic() if now is None else now
    with _lock:
        expired = [k for k, e in _active.items() if e.expires_at <= t]
        for k in expired:
            del _active[k]
        return sorted(_active.keys())


def emit_once(
    once_key: str,
    log_event: str,
    **log_fields: Any,
) -> None:
    """Emit a structured log event at most once per process for ``once_key``."""
    global _reporting_failed_logged
    try:
        with _lock:
            if once_key in _logged_once:
                return
            _logged_once.add(once_key)
        from .logging import get_logger

        get_logger("heatguard.degradation").info(log_event, **log_fields)
    except Exception:
        if not _reporting_failed_logged:
            _reporting_failed_logged = True
            try:
                from .logging import get_logger

                get_logger("heatguard.degradation").error(
                    DEGRADATION_REPORTING_FAILED,
                    message="emit_once failed",
                )
            except Exception:
                pass


def report_degraded(
    code: str,
    detail: str = "",
    *,
    once_key: str | None = None,
    ttl_seconds: float | None = None,
    log_event: str | None = None,
    log_fields: dict[str, Any] | None = None,
    increment_metric: Any | None = None,
) -> None:
    """Record a degraded condition: snapshot + optional one-shot log + metric.

    Never raises. On internal failure emits at most one
    ``degradation.reporting_failed`` event.
    """
    global _reporting_failed_logged
    try:
        if code not in REASON_CODES:
            # Still allow snapshot for known ops codes; unknown codes are ignored
            # for readiness but may still log if log_event is set.
            pass
        ttl = _ttl() if ttl_seconds is None else ttl_seconds
        expires = time.monotonic() + ttl if ttl > 0 else time.monotonic() + 1e9

        should_log = True
        with _lock:
            if code in REASON_CODES:
                _active[code] = _Entry(code=code, detail=detail or "", expires_at=expires)
            if once_key is not None:
                if once_key in _logged_once:
                    should_log = False
                else:
                    _logged_once.add(once_key)

        if should_log and increment_metric is not None:
            try:
                increment_metric()
            except Exception:
                pass

        if should_log and log_event:
            from .logging import get_logger

            fields = dict(log_fields or {})
            if detail and "detail" not in fields:
                fields["detail"] = detail
            fields.setdefault("reason_code", code)
            get_logger("heatguard.degradation").info(log_event, **fields)
    except Exception:
        if not _reporting_failed_logged:
            _reporting_failed_logged = True
            try:
                from .logging import get_logger

                get_logger("heatguard.degradation").error(
                    DEGRADATION_REPORTING_FAILED,
                    message="report_degraded failed",
                )
            except Exception:
                pass
