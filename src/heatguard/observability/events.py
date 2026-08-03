"""Canonical structured event names (WO-013).

Auth dual-mode promotion later keys off the absence of
``auth.deprecated_anonymous`` over a sustained window — keep that contract here.
"""
from __future__ import annotations

HTTP_REQUEST = "http.request"
WEATHER_FETCH = "weather.fetch"
ENGINE_DECIDE = "engine.decide"
COMPLIANCE_APPEND = "compliance.append"
COMPLIANCE_VERIFY = "compliance.verify"
POLICY_QUERY = "policy.query"
AUTH_DEPRECATED_ANONYMOUS = "auth.deprecated_anonymous"

ALL_EVENT_NAMES: tuple[str, ...] = (
    HTTP_REQUEST,
    WEATHER_FETCH,
    ENGINE_DECIDE,
    COMPLIANCE_APPEND,
    COMPLIANCE_VERIFY,
    POLICY_QUERY,
    AUTH_DEPRECATED_ANONYMOUS,
)
