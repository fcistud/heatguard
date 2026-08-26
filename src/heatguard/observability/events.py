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
AUTH_API_KEY = "auth.api_key"
AUTH_SESSION = "auth.session"
WBGT_PATH_SELECTED = "wbgt.path_selected"
WEATHER_FIELD_SUBSTITUTED = "weather.field_substituted"
POLICY_INDEX_UNAVAILABLE = "policy.index_unavailable"
POLICY_INDEX_BUILD_FAILED = "policy.index_build_failed"
RISK_MODEL_HEURISTIC_FALLBACK = "risk_model.heuristic_fallback"
RISK_MODEL_LOAD_FAILED = "risk_model.load_failed"
ENGINE_PHS_WARNING = "engine.phs_warning"
ENFORCEMENT_INTERNAL_ERROR = "enforcement.internal_error"

ALL_EVENT_NAMES: tuple[str, ...] = (
    HTTP_REQUEST,
    WEATHER_FETCH,
    ENGINE_DECIDE,
    COMPLIANCE_APPEND,
    COMPLIANCE_VERIFY,
    POLICY_QUERY,
    AUTH_DEPRECATED_ANONYMOUS,
    AUTH_API_KEY,
    AUTH_SESSION,
    WBGT_PATH_SELECTED,
    WEATHER_FIELD_SUBSTITUTED,
    POLICY_INDEX_UNAVAILABLE,
    POLICY_INDEX_BUILD_FAILED,
    RISK_MODEL_HEURISTIC_FALLBACK,
    RISK_MODEL_LOAD_FAILED,
    ENGINE_PHS_WARNING,
    ENFORCEMENT_INTERNAL_ERROR,
)
