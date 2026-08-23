"""Single-pass EnforcementMiddleware.

Classifies every HTTP request, stamps group/exempt on the ASGI scope, verifies
integrator API keys (WO-003) when presented, and never fails open: unexpected
errors become a structured 403. Missing credentials still admit (dual mode
until WO-005). Quota attaches later.
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from heatguard.boundary.api_keys import MAX_SECRET_CHARS, KeyStore, KeyStoreRef
from heatguard.observability.events import AUTH_API_KEY, ENFORCEMENT_INTERNAL_ERROR
from heatguard.observability.logging import (
    current_request_id,
    emit_auth_deprecated_anonymous,
    get_logger,
)
from heatguard.types import (
    PRINCIPAL_SCOPE_KEY,
    REQUEST_ID_SCOPE_KEY,
    ROUTE_CLASSIFICATION_SCOPE_KEY,
    PrincipalContext,
)

EMPTY_PRINCIPAL = PrincipalContext()

REFUSAL_CODE_INTERNAL = "enforcement_internal_error"
REFUSAL_CODE_UNAUTHENTICATED = "unauthenticated"
REFUSAL_MESSAGE = "Request refused."
REFUSAL_STATUS = 403
REFUSAL_STATUS_UNAUTH = 401

HEADER_API_KEY = b"x-api-key"
HEADER_AUTHORIZATION = b"authorization"

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


@dataclass(frozen=True, slots=True)
class CredentialExtraction:
    """Presented integrator secret, or a refuse flag for conflict/malformed."""

    secret: str | None
    refuse: bool


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

    Exempt routes skip credential checks. Missing credentials still admit
    (dual mode) until WO-005; presented-but-invalid keys are refused earlier.
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


def _header_values(headers: list[tuple[bytes, bytes]], name: bytes) -> list[bytes]:
    return [value for key, value in headers if key.lower() == name]


def _decode_ascii(raw: bytes) -> str | None:
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def _bearer_token(value: str) -> str | None:
    prefix = "bearer "
    if len(value) < len(prefix) or not value[: len(prefix)].lower() == prefix:
        return None
    return value[len(prefix) :]


def extract_presented_secret(headers: list[tuple[bytes, bytes]]) -> CredentialExtraction:
    """Read X-API-Key and Authorization Bearer. Conflict / malformed → refuse."""
    api_raw = _header_values(headers, HEADER_API_KEY)
    auth_raw = _header_values(headers, HEADER_AUTHORIZATION)

    api_secrets: list[str] = []
    for raw in api_raw:
        text = _decode_ascii(raw)
        if text is None:
            return CredentialExtraction(secret=None, refuse=True)
        stripped = text.strip()
        if not stripped or len(stripped) > MAX_SECRET_CHARS:
            return CredentialExtraction(secret=None, refuse=True)
        api_secrets.append(stripped)

    bearer_secrets: list[str] = []
    for raw in auth_raw:
        text = _decode_ascii(raw)
        if text is None:
            return CredentialExtraction(secret=None, refuse=True)
        token = _bearer_token(text.strip())
        if token is None:
            # Non-Bearer Authorization is ignored (session JWT lands in WO-004).
            continue
        stripped = token.strip()
        if not stripped or len(stripped) > MAX_SECRET_CHARS:
            return CredentialExtraction(secret=None, refuse=True)
        bearer_secrets.append(stripped)

    if len(set(api_secrets)) > 1 or len(set(bearer_secrets)) > 1:
        return CredentialExtraction(secret=None, refuse=True)
    api_secret = api_secrets[0] if api_secrets else None
    bearer_secret = bearer_secrets[0] if bearer_secrets else None
    if api_secret is not None and bearer_secret is not None and api_secret != bearer_secret:
        return CredentialExtraction(secret=None, refuse=True)
    return CredentialExtraction(secret=api_secret or bearer_secret, refuse=False)


def _resolve_key_store(
    *,
    injected: KeyStore | None,
    ref: KeyStoreRef | None,
    app: Any,
    scope: Mapping[str, Any],
) -> KeyStore | None:
    if injected is not None:
        return injected
    if ref is not None and isinstance(ref.store, KeyStore):
        return ref.store
    for candidate in (app, scope.get("app")):
        state = getattr(candidate, "state", None)
        store = getattr(state, "key_store", None)
        if isinstance(store, KeyStore):
            return store
    return None


def _log_api_key(
    *,
    request_id: str,
    route_group: str,
    outcome: str,
    key_class: str | None,
) -> None:
    get_logger("heatguard.enforcement").info(
        AUTH_API_KEY,
        request_id=request_id,
        route_group=route_group,
        outcome=outcome,
        key_class=key_class,
    )


async def _send_refusal(
    send: SendFn,
    *,
    request_id: str,
    code: str = REFUSAL_CODE_INTERNAL,
    status: int = REFUSAL_STATUS,
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
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload, "more_body": False})


class EnforcementMiddleware:
    """Raw-ASGI chokepoint. Never raises; never admits on internal failure."""

    def __init__(
        self,
        app: Any,
        *,
        classify: ClassifyFn | None = classify_request,
        key_store: KeyStore | None = None,
        key_store_ref: KeyStoreRef | None = None,
    ) -> None:
        self.app = app
        self._classify = classify
        self._key_store = key_store
        self._key_store_ref = key_store_ref

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
            principal = EMPTY_PRINCIPAL

            if not classification.exempt:
                presented = extract_presented_secret(list(scope.get("headers") or []))
                if presented.refuse:
                    _log_api_key(
                        request_id=request_id,
                        route_group=group,
                        outcome="conflict",
                        key_class=None,
                    )
                    await _send_refusal(
                        send,
                        request_id=request_id,
                        code=REFUSAL_CODE_UNAUTHENTICATED,
                        status=REFUSAL_STATUS_UNAUTH,
                    )
                    return
                if presented.secret is not None:
                    store = _resolve_key_store(
                        injected=self._key_store,
                        ref=self._key_store_ref,
                        app=self.app,
                        scope=scope,
                    )
                    if store is None:
                        raise RuntimeError("enforcement_key_store_uninitialised")
                    resolved = store.verify(presented.secret)
                    if resolved is None:
                        _log_api_key(
                            request_id=request_id,
                            route_group=group,
                            outcome="unauthenticated",
                            key_class=None,
                        )
                        await _send_refusal(
                            send,
                            request_id=request_id,
                            code=REFUSAL_CODE_UNAUTHENTICATED,
                            status=REFUSAL_STATUS_UNAUTH,
                        )
                        return
                    principal = resolved
                    _log_api_key(
                        request_id=request_id,
                        route_group=group,
                        outcome="authenticated",
                        key_class=resolved.key_class,
                    )
                else:
                    emit_auth_deprecated_anonymous(
                        route=canonical_path(path),
                        request_id=request_id,
                    )

            scope[PRINCIPAL_SCOPE_KEY] = principal
            if access_decision(classification, principal) != "admit":
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
