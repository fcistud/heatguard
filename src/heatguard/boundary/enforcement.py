"""Single-pass EnforcementMiddleware (WO-002 skeleton).

Classifies every HTTP request, stamps group/exempt on the ASGI scope,
attaches an empty principal, and never fails open: unexpected errors
become a structured 403. Credential verification and quota attach to
this pass in later stories; this story still admits classified requests.
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from heatguard.observability.events import ENFORCEMENT_INTERNAL_ERROR
from heatguard.observability.logging import current_request_id, get_logger
from heatguard.types import (
    PRINCIPAL_SCOPE_KEY,
    REQUEST_ID_SCOPE_KEY,
    ROUTE_CLASSIFICATION_SCOPE_KEY,
    PrincipalContext,
)

EMPTY_PRINCIPAL = PrincipalContext()

REFUSAL_CODE_INTERNAL = "enforcement_internal_error"
REFUSAL_MESSAGE = "Request refused."
REFUSAL_STATUS = 403

# (pattern, group, exempt) — most specific first; compiled once at import.
_ROUTE_SPEC: tuple[tuple[str, str, bool], ...] = (
    (r"^/health/live$", "probes", True),
    (r"^/health/ready$", "probes", True),
    (r"^/health$", "probes", True),
    (r"^/metrics$", "metrics", True),
    (r"^/auth(/|$)", "session", False),
    (r"^/decide$", "advisory", False),
    (r"^/hour(/|$)", "advisory", False),
    (r"^/timeline(/|$)", "advisory", False),
    (r"^/demo(/|$)", "advisory", False),
    (r"^/forecast(/|$)", "advisory", False),
    (r"^/sites$", "reference", False),
    (r"^/demos$", "reference", False),
    (r"^/backtest$", "reference", False),
    (r"^/datasets$", "reference", False),
    (r"^/policy(/|$)", "reference", False),
    (r"^/impact(/|$)", "reference", False),
    (r"^/economics(/|$)", "reference", False),
    (r"^/sensitivity(/|$)", "reference", False),
    (r"^/scale(/|$)", "reference", False),
    (r"^/compliance(/|$)", "reference", False),
    (r"^/dashboard(/|$)", "static", False),
    (r"^/landing(/|$)", "static", False),
    (r"^/(openapi\.json|docs|redoc)(/|$)", "reference", False),
    (r"^/$", "static", False),
)

_COMPILED: tuple[tuple[re.Pattern[str], str, bool], ...] | None = tuple(
    (re.compile(pattern), group, exempt) for pattern, group, exempt in _ROUTE_SPEC
)

ClassifyFn = Callable[[str, str], "RouteClassification"]
ReceiveFn = Callable[[], Awaitable[Any]]
SendFn = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RouteClassification:
    """Static route-group result — no FastAPI router lookup."""

    group: str
    exempt: bool
    pattern: str


def canonical_path(path: str) -> str:
    """Strip a trailing slash except for the root so /health/ == /health."""
    if not path:
        return "/"
    if len(path) > 1 and path.endswith("/"):
        return path.rstrip("/") or "/"
    return path


def classify_request(path: str, method: str) -> RouteClassification:
    """Match ``path`` against the precompiled table. Ambiguity → ``unknown``.

    ``method`` is accepted so later stories can split OPTIONS/HEAD without
    changing the call site; exemption is path-based in this story.
    """
    del method
    compiled = _COMPILED
    if compiled is None:
        raise RuntimeError("enforcement_tables_uninitialised")
    norm = canonical_path(path)
    for regex, group, exempt in compiled:
        if regex.search(norm):
            return RouteClassification(group=group, exempt=exempt, pattern=regex.pattern)
    return RouteClassification(group="unknown", exempt=False, pattern="")


UNKNOWN_CLASSIFICATION = RouteClassification(group="unknown", exempt=False, pattern="")


def principal_from_scope(scope: Mapping[str, Any]) -> PrincipalContext:
    """Read the request-scoped principal; missing key → empty context."""
    value = scope.get(PRINCIPAL_SCOPE_KEY)
    if isinstance(value, PrincipalContext):
        return value
    return EMPTY_PRINCIPAL


def classification_from_scope(scope: Mapping[str, Any]) -> RouteClassification:
    """Read the request-scoped route group; missing key → unknown / not exempt."""
    value = scope.get(ROUTE_CLASSIFICATION_SCOPE_KEY)
    if isinstance(value, RouteClassification):
        return value
    return UNKNOWN_CLASSIFICATION


def access_decision(
    classification: RouteClassification,
    _principal: PrincipalContext,
) -> str:
    """Admit or deny after classification.

    Exempt routes skip credential checks. Non-exempt routes will consult
    ``_principal`` in WO-003+; this story still admits so demo/dashboard stay up.
    """
    if classification.exempt:
        return "admit"
    return "admit"


def refusal_body(request_id: str, *, code: str = REFUSAL_CODE_INTERNAL) -> dict[str, str]:
    return {
        "code": code,
        "message": REFUSAL_MESSAGE,
        "request_id": request_id,
    }


def _request_id_from_scope(scope: Mapping[str, Any]) -> str:
    rid = scope.get(REQUEST_ID_SCOPE_KEY)
    if isinstance(rid, str) and rid:
        return rid
    bound = current_request_id()
    if bound:
        return bound
    return "missing"


async def _send_refusal(
    send: SendFn,
    *,
    request_id: str,
    code: str = REFUSAL_CODE_INTERNAL,
) -> None:
    payload = json.dumps(
        refusal_body(request_id, code=code),
        separators=(",", ":"),
    ).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"cache-control", b"no-store"),
        (b"x-request-id", request_id.encode("ascii", errors="replace")),
        (b"content-length", str(len(payload)).encode("ascii")),
    ]
    await send({"type": "http.response.start", "status": REFUSAL_STATUS, "headers": headers})
    await send({"type": "http.response.body", "body": payload, "more_body": False})


class EnforcementMiddleware:
    """Raw-ASGI chokepoint. Never raises; never admits on internal failure."""

    def __init__(
        self,
        app: Any,
        *,
        classify: ClassifyFn | None = classify_request,
    ) -> None:
        self.app = app
        self._classify = classify

    async def __call__(self, scope: dict[str, Any], receive: ReceiveFn, send: SendFn) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from_scope(scope)
        group = "unknown"
        try:
            classifier = self._classify
            if classifier is None or _COMPILED is None:
                raise RuntimeError("enforcement_tables_uninitialised")
            path = scope.get("path") or "/"
            method = scope.get("method") or "GET"
            classification = classifier(path, method)
            group = classification.group
            scope[ROUTE_CLASSIFICATION_SCOPE_KEY] = classification
            scope[PRINCIPAL_SCOPE_KEY] = EMPTY_PRINCIPAL
            if access_decision(classification, EMPTY_PRINCIPAL) != "admit":
                await _send_refusal(send, request_id=request_id, code="forbidden")
                return
        except Exception as exc:
            log = get_logger("heatguard.enforcement")
            log.error(
                ENFORCEMENT_INTERNAL_ERROR,
                request_id=request_id,
                route_group=group,
                exception_type=type(exc).__name__,
            )
            await _send_refusal(send, request_id=request_id)
            return

        await self.app(scope, receive, send)
