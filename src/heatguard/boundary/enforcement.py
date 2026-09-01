"""Single-pass EnforcementMiddleware.

Classifies every HTTP request, stamps group/exempt on the ASGI scope, verifies
integrator API keys (WO-003) and HS256 session tokens (WO-004) when presented,
and never fails open: unexpected errors become a structured 403. Missing
credentials admit in dual mode and receive 401 in enforce (WO-005). Quota
is the one fail-open path: limiter errors admit rather than withhold an
advisory.
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from heatguard.boundary.api_keys import MAX_SECRET_CHARS, KeyStore, KeyStoreRef
from heatguard.boundary.auth_mode import (
    DEFAULT_SNAPSHOT,
    AuthMode,
    AuthModeRef,
    AuthModeSnapshot,
    principal_permits_route,
)
from heatguard.boundary.quota import (
    ANONYMOUS_KEY_CLASS,
    DEFAULT_RUNTIME,
    DEMO_KEY_CLASS,
    QuotaRef,
    QuotaRuntime,
    bucket_key,
    coarse_origin,
)
from heatguard.boundary.session_tokens import (
    MAX_TOKEN_CHARS,
    SessionAuth,
    SessionAuthRef,
    SessionFailure,
    looks_like_compact_jws,
)
from heatguard.observability.events import AUTH_API_KEY, AUTH_SESSION, ENFORCEMENT_INTERNAL_ERROR
from heatguard.observability.logging import (
    current_request_id,
    emit_auth_deprecated_anonymous,
    get_logger,
)
from heatguard.observability.metrics import (
    observe_auth_outcome,
    observe_ratelimit_rejected,
    observe_ratelimit_would_reject,
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
REFUSAL_CODE_FORBIDDEN = "forbidden"
REFUSAL_CODE_QUOTA = "quota_exceeded"
REFUSAL_MESSAGE = "Request refused."
REFUSAL_STATUS = 403
REFUSAL_STATUS_UNAUTH = 401
REFUSAL_STATUS_QUOTA = 429

HEADER_API_KEY = b"x-api-key"
HEADER_AUTHORIZATION = b"authorization"
# Observable proof the chokepoint classified this request (WO-006 traversal).
HEADER_ROUTE_GROUP = b"x-heatguard-route-group"

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
    """Presented X-API-Key and/or Bearer, or a refuse flag for conflict/malformed."""

    api_key: str | None
    bearer: str | None
    refuse: bool

    @property
    def secret(self) -> str | None:
        """Single presented value when headers agree (WO-003 compatibility)."""
        return self.api_key or self.bearer


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
    principal: PrincipalContext,
    *,
    mode: AuthMode = AuthMode.DUAL,
    path: str = "",
) -> str:
    """Admit or deny after classification and optional enforce-mode authz.

    Exempt routes skip credential and site checks. Dual mode still admits
    anonymous callers. Enforce mode denies anonymous (401 at the caller) and
    authenticated principals that fail site-scope (403).
    """
    if classification.exempt:
        return "admit"
    if mode is AuthMode.ENFORCE:
        if principal.principal_id is None and not principal.roles and not principal.sites:
            return "deny"
        if principal.principal_id is not None and not principal_permits_route(
            path, principal
        ):
            return "deny"
    return "admit"


def refusal_body(request_id: str, *, code: str = REFUSAL_CODE_INTERNAL) -> dict[str, str]:
    return {
        "code": code,
        "message": REFUSAL_MESSAGE,
        "request_id": request_id,
    }


def _send_with_route_group(send: SendFn, group_holder: dict[str, str]) -> SendFn:
    """Stamp ``x-heatguard-route-group`` on every HTTP response start."""

    async def wrapped(message: dict[str, Any]) -> None:
        if message.get("type") == "http.response.start":
            headers = list(message.get("headers") or [])
            headers.append(
                (HEADER_ROUTE_GROUP, group_holder["group"].encode("ascii"))
            )
            message = {**message, "headers": headers}
        await send(message)

    return wrapped


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
            return CredentialExtraction(api_key=None, bearer=None, refuse=True)
        stripped = text.strip()
        if not stripped or len(stripped) > MAX_SECRET_CHARS:
            return CredentialExtraction(api_key=None, bearer=None, refuse=True)
        api_secrets.append(stripped)

    bearer_secrets: list[str] = []
    for raw in auth_raw:
        text = _decode_ascii(raw)
        if text is None:
            return CredentialExtraction(api_key=None, bearer=None, refuse=True)
        token = _bearer_token(text.strip())
        if token is None:
            # Non-Bearer schemes are ignored here; compact JWS is still Bearer.
            continue
        stripped = token.strip()
        if not stripped:
            return CredentialExtraction(api_key=None, bearer=None, refuse=True)
        cap = MAX_TOKEN_CHARS if looks_like_compact_jws(stripped) else MAX_SECRET_CHARS
        if len(stripped) > cap:
            return CredentialExtraction(api_key=None, bearer=None, refuse=True)
        bearer_secrets.append(stripped)

    if len(set(api_secrets)) > 1 or len(set(bearer_secrets)) > 1:
        return CredentialExtraction(api_key=None, bearer=None, refuse=True)
    api_secret = api_secrets[0] if api_secrets else None
    bearer_secret = bearer_secrets[0] if bearer_secrets else None
    if api_secret is not None and bearer_secret is not None and api_secret != bearer_secret:
        return CredentialExtraction(api_key=None, bearer=None, refuse=True)
    return CredentialExtraction(api_key=api_secret, bearer=bearer_secret, refuse=False)


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


def _resolve_session_auth(
    *,
    injected: SessionAuth | None,
    ref: SessionAuthRef | None,
    app: Any,
    scope: Mapping[str, Any],
) -> SessionAuth | None:
    if injected is not None:
        return injected
    if ref is not None and isinstance(ref.auth, SessionAuth):
        return ref.auth
    for candidate in (app, scope.get("app")):
        state = getattr(candidate, "state", None)
        auth = getattr(state, "session_auth", None)
        if isinstance(auth, SessionAuth):
            return auth
    return None


def _resolve_quota(
    *,
    injected: QuotaRuntime | None,
    ref: QuotaRef | None,
    app: Any,
    scope: Mapping[str, Any],
) -> QuotaRuntime:
    if injected is not None:
        return injected
    if ref is not None and isinstance(ref.runtime, QuotaRuntime):
        return ref.runtime
    for candidate in (app, scope.get("app")):
        state = getattr(candidate, "state", None)
        runtime = getattr(state, "quota", None)
        if isinstance(runtime, QuotaRuntime):
            return runtime
    return DEFAULT_RUNTIME


def _resolve_auth_modes(
    *,
    injected: AuthModeSnapshot | None,
    ref: AuthModeRef | None,
    app: Any,
    scope: Mapping[str, Any],
) -> AuthModeSnapshot:
    if injected is not None:
        return injected
    if ref is not None and isinstance(ref.snapshot, AuthModeSnapshot):
        return ref.snapshot
    for candidate in (app, scope.get("app")):
        state = getattr(candidate, "state", None)
        snapshot = getattr(state, "auth_modes", None)
        if isinstance(snapshot, AuthModeSnapshot):
            return snapshot
    return DEFAULT_SNAPSHOT


def _header_text(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    values = _header_values(headers, name)
    if not values:
        return None
    raw = values[0]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


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


def _log_session(
    *,
    request_id: str,
    route_group: str,
    outcome: str,
    key_class: str | None,
    reason: str | None,
) -> None:
    get_logger("heatguard.enforcement").info(
        AUTH_SESSION,
        request_id=request_id,
        route_group=route_group,
        outcome=outcome,
        key_class=key_class,
        reason=reason,
    )


async def _send_refusal(
    send: SendFn,
    *,
    request_id: str,
    code: str = REFUSAL_CODE_INTERNAL,
    status: int = REFUSAL_STATUS,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
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
    if extra_headers:
        headers.extend(extra_headers)
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
        session_auth: SessionAuth | None = None,
        session_auth_ref: SessionAuthRef | None = None,
        auth_modes: AuthModeSnapshot | None = None,
        auth_mode_ref: AuthModeRef | None = None,
        quota: QuotaRuntime | None = None,
        quota_ref: QuotaRef | None = None,
    ) -> None:
        self.app = app
        self._classify = classify
        self._key_store = key_store
        self._key_store_ref = key_store_ref
        self._session_auth = session_auth
        self._session_auth_ref = session_auth_ref
        self._auth_modes = auth_modes
        self._auth_mode_ref = auth_mode_ref
        self._quota = quota
        self._quota_ref = quota_ref

    async def __call__(self, scope: dict[str, Any], receive: ReceiveFn, send: SendFn) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from_scope(scope)
        group_holder = {"group": "unknown"}
        send = _send_with_route_group(send, group_holder)
        group = "unknown"
        try:
            classifier = self._classify
            if classifier is None or _COMPILED is None:
                raise RuntimeError("enforcement_tables_uninitialised")
            path = scope.get("path") or "/"
            method = scope.get("method") or "GET"
            classification = classifier(path, method)
            group = classification.group
            group_holder["group"] = group
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
                if presented.api_key is not None:
                    principal = await self._authenticate_api_key(
                        presented.api_key,
                        request_id=request_id,
                        group=group,
                        scope=scope,
                        send=send,
                    )
                    if principal is None:
                        return
                elif presented.bearer is not None:
                    principal = await self._authenticate_bearer(
                        presented.bearer,
                        request_id=request_id,
                        group=group,
                        scope=scope,
                        send=send,
                    )
                    if principal is None:
                        return
                else:
                    snapshot = _resolve_auth_modes(
                        injected=self._auth_modes,
                        ref=self._auth_mode_ref,
                        app=self.app,
                        scope=scope,
                    )
                    mode = snapshot.mode_for(group)
                    if mode is AuthMode.ENFORCE:
                        observe_auth_outcome(
                            route_group=group,
                            key_class="anonymous",
                            outcome="unauthenticated",
                        )
                        await _send_refusal(
                            send,
                            request_id=request_id,
                            code=REFUSAL_CODE_UNAUTHENTICATED,
                            status=REFUSAL_STATUS_UNAUTH,
                        )
                        return
                    headers = list(scope.get("headers") or [])
                    emit_auth_deprecated_anonymous(
                        route=canonical_path(path),
                        origin=_header_text(headers, b"origin"),
                        user_agent=_header_text(headers, b"user-agent"),
                        request_id=request_id,
                        route_group=group,
                    )
                    observe_auth_outcome(
                        route_group=group,
                        key_class="anonymous",
                        outcome="deprecated_anonymous",
                    )

            scope[PRINCIPAL_SCOPE_KEY] = principal
            snapshot = _resolve_auth_modes(
                injected=self._auth_modes,
                ref=self._auth_mode_ref,
                app=self.app,
                scope=scope,
            )
            mode = snapshot.mode_for(group)
            if access_decision(
                classification, principal, mode=mode, path=str(path)
            ) != "admit":
                if principal.principal_id is None:
                    observe_auth_outcome(
                        route_group=group,
                        key_class="anonymous",
                        outcome="unauthenticated",
                    )
                    await _send_refusal(
                        send,
                        request_id=request_id,
                        code=REFUSAL_CODE_UNAUTHENTICATED,
                        status=REFUSAL_STATUS_UNAUTH,
                    )
                    return
                observe_auth_outcome(
                    route_group=group,
                    key_class=principal.key_class or "none",
                    outcome="forbidden",
                )
                await _send_refusal(
                    send,
                    request_id=request_id,
                    code=REFUSAL_CODE_FORBIDDEN,
                    status=REFUSAL_STATUS,
                )
                return
            if principal.principal_id is not None:
                observe_auth_outcome(
                    route_group=group,
                    key_class=principal.key_class or "none",
                    outcome="authenticated",
                )
            if not classification.exempt:
                try:
                    refused = await self._enforce_quota(
                        send,
                        request_id=request_id,
                        path=str(path),
                        group=group,
                        principal=principal,
                        scope=scope,
                    )
                except Exception:
                    get_logger("heatguard.enforcement").warning(
                        "quota.limiter_error",
                        request_id=request_id,
                        route_group=group,
                    )
                    refused = False
                if refused:
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

    async def _enforce_quota(
        self,
        send: SendFn,
        *,
        request_id: str,
        path: str,
        group: str,
        principal: PrincipalContext,
        scope: Mapping[str, Any],
    ) -> bool:
        """Return True when a 429 was sent. Demo keys and limiter errors admit."""
        if principal.key_class == DEMO_KEY_CLASS:
            return False
        runtime = _resolve_quota(
            injected=self._quota,
            ref=self._quota_ref,
            app=self.app,
            scope=scope,
        )
        key_class = principal.key_class or ANONYMOUS_KEY_CLASS
        origin = coarse_origin(
            _header_text(list(scope.get("headers") or []), b"origin")
        )
        capacity, refill = runtime.settings.params_for(key_class, group)
        result = runtime.store.consume(
            bucket_key(
                principal_id=principal.principal_id,
                origin=origin,
                group=group,
            ),
            1.0,
            runtime.now(),
            capacity=capacity,
            refill_per_sec=refill,
        )
        if result.allowed:
            return False
        route = canonical_path(path)
        if runtime.settings.observe_only:
            observe_ratelimit_would_reject(route=route, key_class=key_class)
            return False
        observe_ratelimit_rejected(route=route, key_class=key_class)
        await _send_refusal(
            send,
            request_id=request_id,
            code=REFUSAL_CODE_QUOTA,
            status=REFUSAL_STATUS_QUOTA,
            extra_headers=[
                (b"retry-after", str(result.retry_after_seconds).encode("ascii")),
            ],
        )
        return True

    async def _authenticate_api_key(
        self,
        secret: str,
        *,
        request_id: str,
        group: str,
        scope: Mapping[str, Any],
        send: SendFn,
    ) -> PrincipalContext | None:
        store = _resolve_key_store(
            injected=self._key_store,
            ref=self._key_store_ref,
            app=self.app,
            scope=scope,
        )
        if store is None:
            raise RuntimeError("enforcement_key_store_uninitialised")
        resolved = store.verify(secret)
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
            return None
        _log_api_key(
            request_id=request_id,
            route_group=group,
            outcome="authenticated",
            key_class=resolved.key_class,
        )
        return resolved

    async def _authenticate_bearer(
        self,
        token: str,
        *,
        request_id: str,
        group: str,
        scope: Mapping[str, Any],
        send: SendFn,
    ) -> PrincipalContext | None:
        if looks_like_compact_jws(token):
            auth = _resolve_session_auth(
                injected=self._session_auth,
                ref=self._session_auth_ref,
                app=self.app,
                scope=scope,
            )
            if auth is None:
                raise RuntimeError("enforcement_session_auth_uninitialised")
            result = auth.verify(token)
            if result.principal is None:
                reason = (result.reason or SessionFailure.INVALID).value
                _log_session(
                    request_id=request_id,
                    route_group=group,
                    outcome="unauthenticated",
                    key_class=None,
                    reason=reason,
                )
                await _send_refusal(
                    send,
                    request_id=request_id,
                    code=REFUSAL_CODE_UNAUTHENTICATED,
                    status=REFUSAL_STATUS_UNAUTH,
                )
                return None
            principal = result.principal
            _log_session(
                request_id=request_id,
                route_group=group,
                outcome="authenticated",
                key_class=principal.key_class,
                reason=None,
            )
            return principal
        return await self._authenticate_api_key(
            token,
            request_id=request_id,
            group=group,
            scope=scope,
            send=send,
        )
