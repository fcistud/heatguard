"""Characterization and integration tests for EnforcementMiddleware (WO-002)."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from heatguard.api import app  # noqa: E402
from heatguard.boundary.api_keys import load_key_store  # noqa: E402
from heatguard.boundary.session_tokens import (  # noqa: E402
    default_claims,
    load_session_auth,
    mint_session_token,
)
from heatguard.boundary.enforcement import (  # noqa: E402
    EMPTY_PRINCIPAL,
    REFUSAL_CODE_INTERNAL,
    REFUSAL_CODE_UNAUTHENTICATED,
    REFUSAL_MESSAGE,
    EnforcementMiddleware,
    classification_from_scope,
    classify_request,
    principal_from_scope,
)
from heatguard.observability.events import ENFORCEMENT_INTERNAL_ERROR  # noqa: E402
from heatguard.observability.middleware import CorrelationMiddleware  # noqa: E402
from heatguard.types import PRINCIPAL_SCOPE_KEY, ROUTE_CLASSIFICATION_SCOPE_KEY  # noqa: E402

client = TestClient(app)


def _middleware_names() -> list[str]:
    """``user_middleware`` is outermost-first (reverse of ``add_middleware`` order)."""
    return [m.cls.__name__ for m in app.user_middleware]


def test_middleware_order_correlation_cors_enforcement() -> None:
    names = _middleware_names()
    assert names == [
        "CorrelationMiddleware",
        "CORSMiddleware",
        "EnforcementMiddleware",
    ]
    assert app.user_middleware[0].cls is CorrelationMiddleware
    assert app.user_middleware[1].cls is CORSMiddleware
    assert app.user_middleware[2].cls is EnforcementMiddleware


def test_probe_health_alias_unchanged() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["python"]["major"] == 3


def test_probe_health_trailing_slash_unchanged() -> None:
    resp = client.get("/health/", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_probe_liveness_unchanged() -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "uptime_seconds" in body
    assert resp.headers.get("cache-control") == "no-store"


def test_probe_readiness_unchanged() -> None:
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["status"] in {"ready", "degraded", "not_ready"}
    assert "failed" in body and "degraded" in body


def test_metrics_path_still_reachable() -> None:
    resp = client.get("/metrics")
    assert resp.status_code in (200, 404)


def test_exempt_head_and_options_on_live() -> None:
    head = client.head("/health/live")
    # Admitted through enforcement (not a 403); FastAPI may or may not implement HEAD.
    assert head.status_code != 403
    options = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert options.status_code != 403


def test_representative_business_endpoint_unchanged() -> None:
    resp = client.get("/backtest")
    assert resp.status_code == 200
    assert resp.json()["passed"] is True


def _find_enforcement() -> EnforcementMiddleware:
    node: Any = app.middleware_stack
    seen: list[str] = []
    while node is not None:
        seen.append(type(node).__name__)
        if isinstance(node, EnforcementMiddleware):
            return node
        node = getattr(node, "app", None)
    raise AssertionError(f"EnforcementMiddleware not in stack: {seen}")


def test_never_raise_denies_with_structured_body_and_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[tuple[str, dict[str, Any]]] = []

    class _Log:
        def error(self, event: str, **fields: Any) -> None:
            recorded.append((event, fields))

    monkeypatch.setattr(
        "heatguard.boundary.enforcement.get_logger",
        lambda *_a, **_k: _Log(),
    )
    mw = _find_enforcement()
    original = mw._classify

    def boom(_path: str, _method: str) -> None:
        raise RuntimeError("secret-token-must-not-leak")

    mw._classify = boom
    try:
        resp = client.get(
            "/sites",
            headers={"Origin": "http://localhost:5173", "X-Request-Id": "enf-test-1"},
        )
    finally:
        mw._classify = original

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == REFUSAL_CODE_INTERNAL
    assert body["message"] == REFUSAL_MESSAGE
    assert body["request_id"]
    assert "secret-token-must-not-leak" not in resp.text
    assert "traceback" not in resp.text.lower()
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert recorded
    event, fields = recorded[0]
    assert event == ENFORCEMENT_INTERNAL_ERROR
    assert fields["exception_type"] == "RuntimeError"
    assert "secret-token-must-not-leak" not in str(fields)


def test_uninitialised_classifier_denies() -> None:
    captured: list[int] = []

    async def inner(scope: dict, receive: object, send: Any) -> None:
        captured.append(1)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    mw = EnforcementMiddleware(inner, classify=None)
    status: dict[str, int] = {}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            status["code"] = int(message["status"])

    import asyncio

    asyncio.run(
        mw(
            {
                "type": "http",
                "method": "GET",
                "path": "/sites",
                "headers": [],
            },
            _receive,
            send,
        )
    )
    assert status["code"] == 403
    assert captured == []


def test_principal_and_classification_attached_on_http_request() -> None:
    seen: dict[str, Any] = {}

    async def inner(scope: dict, receive: object, send: Any) -> None:
        seen["principal"] = principal_from_scope(scope)
        seen["classification"] = classification_from_scope(scope)
        seen["has_principal"] = PRINCIPAL_SCOPE_KEY in scope
        seen["has_class"] = ROUTE_CLASSIFICATION_SCOPE_KEY in scope
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    mw = EnforcementMiddleware(inner)
    import asyncio

    asyncio.run(
        mw(
            {
                "type": "http",
                "method": "GET",
                "path": "/health/live",
                "headers": [],
            },
            _receive,
            send=_null_send,
        )
    )
    assert seen["has_principal"] is True
    assert seen["has_class"] is True
    assert seen["principal"] == EMPTY_PRINCIPAL
    assert seen["classification"].exempt is True
    assert seen["classification"].group == "probes"

    asyncio.run(
        mw(
            {
                "type": "http",
                "method": "GET",
                "path": "/sites",
                "headers": [],
            },
            _receive,
            send=_null_send,
        )
    )
    assert seen["classification"].exempt is False
    assert seen["classification"].group == "reference"


@pytest.mark.parametrize(
    "path",
    ["/sites", "/hour/dubai/2025-05-16/12", "/demo/dubai"],
)
def test_anonymous_advisory_still_admitted(path: str) -> None:
    """Missing credentials still admit (dual mode until WO-005)."""
    resp = client.get(path)
    assert resp.status_code not in (401, 403)


def _api_key_payload() -> dict:
    path = Path(__file__).parent / "fixtures" / "api_key_digests.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _session_payload() -> dict:
    path = Path(__file__).parent / "fixtures" / "session_tokens.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _live_session_token(*, expired: bool = False, forged: bool = False) -> str:
    payload = _session_payload()
    now = int(time.time())
    iat = now - 3600 if expired else now
    exp = now - 100 if expired else now + 3600
    token = mint_session_token(
        secret=payload["signing_secret"],
        claims=default_claims(
            sub="dashboard-supervisor",
            now=iat,
            lifetime=exp - iat,
            token_version=1,
            roles=["supervisor"],
            sites=["dubai"],
        ),
        kid=payload["kid"],
    )
    if forged:
        header, body, sig = token.split(".")
        return f"{header}.{body}.{sig[:-2]}aa"
    return token


def test_valid_x_api_key_and_bearer_admitted() -> None:
    secret = _api_key_payload()["secrets"]["demo-integrator"]
    via_header = client.get("/sites", headers={"X-API-Key": secret})
    via_bearer = client.get("/sites", headers={"Authorization": f"Bearer {secret}"})
    assert via_header.status_code == 200
    assert via_bearer.status_code == 200
    assert via_header.json() == via_bearer.json()


def test_invalid_and_revoked_keys_are_unauthenticated() -> None:
    payload = _api_key_payload()
    unknown = client.get("/sites", headers={"X-API-Key": "not-a-real-key"})
    revoked = client.get(
        "/sites",
        headers={"X-API-Key": payload["secrets"]["revoked-integrator"]},
    )
    missing_body = unknown.json()
    assert unknown.status_code == 401
    assert revoked.status_code == 401
    assert missing_body["code"] == REFUSAL_CODE_UNAUTHENTICATED
    assert missing_body["message"] == REFUSAL_MESSAGE
    assert "request_id" in missing_body


def test_conflicting_headers_are_unauthenticated() -> None:
    payload = _api_key_payload()
    resp = client.get(
        "/sites",
        headers={
            "X-API-Key": payload["secrets"]["demo-integrator"],
            "Authorization": f"Bearer {payload['secrets']['partner-integrator']}",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == REFUSAL_CODE_UNAUTHENTICATED


def test_valid_session_token_admitted_on_advisory() -> None:
    token = _live_session_token()
    resp = client.get("/sites", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_expired_and_forged_session_tokens_are_unauthenticated() -> None:
    expired = client.get(
        "/sites",
        headers={"Authorization": f"Bearer {_live_session_token(expired=True)}"},
    )
    forged = client.get(
        "/sites",
        headers={"Authorization": f"Bearer {_live_session_token(forged=True)}"},
    )
    assert expired.status_code == 401
    assert forged.status_code == 401
    body = expired.json()
    assert body["code"] == REFUSAL_CODE_UNAUTHENTICATED
    assert body["message"] == REFUSAL_MESSAGE
    assert "request_id" in body
    assert forged.json()["code"] == REFUSAL_CODE_UNAUTHENTICATED


def test_jwt_in_x_api_key_is_not_accepted() -> None:
    token = _live_session_token()
    resp = client.get("/sites", headers={"X-API-Key": token})
    assert resp.status_code == 401


def test_session_token_attaches_dashboard_principal() -> None:
    payload = _session_payload()
    auth = load_session_auth(
        {
            "HEATGUARD_SESSION_SIGNING_SECRET": payload["signing_secret"],
            "HEATGUARD_SESSION_KID": payload["kid"],
            "HEATGUARD_IDENTITY_SNAPSHOT": json.dumps(payload["principals"]),
        }
    )
    token = _live_session_token()
    seen: dict[str, Any] = {}

    async def inner(scope: dict, receive: object, send: Any) -> None:
        seen["principal"] = principal_from_scope(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    import asyncio

    asyncio.run(
        EnforcementMiddleware(inner, session_auth=auth)(
            {
                "type": "http",
                "method": "GET",
                "path": "/sites",
                "headers": [(b"authorization", f"Bearer {token}".encode("ascii"))],
            },
            _receive,
            _null_send,
        )
    )
    assert seen["principal"].principal_id == "dashboard-supervisor"
    assert seen["principal"].key_class == "dashboard"
    assert seen["principal"].roles == ("supervisor",)
    assert seen["principal"].token_version == 1


def test_valid_key_attaches_principal_on_scope() -> None:
    payload = _api_key_payload()
    store = load_key_store(
        {
            "HEATGUARD_API_KEY_PEPPER": payload["pepper"],
            "HEATGUARD_API_KEY_DIGESTS": json.dumps(payload["bundle"]),
        }
    )
    seen: dict[str, Any] = {}

    async def inner(scope: dict, receive: object, send: Any) -> None:
        seen["principal"] = principal_from_scope(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    import asyncio

    asyncio.run(
        EnforcementMiddleware(inner, key_store=store)(
            {
                "type": "http",
                "method": "GET",
                "path": "/sites",
                "headers": [
                    (b"x-api-key", payload["secrets"]["demo-integrator"].encode("ascii")),
                ],
            },
            _receive,
            _null_send,
        )
    )
    assert seen["principal"].principal_id == "demo-integrator"
    assert seen["principal"].key_class == "demo"


def test_access_decision_hook_denies_non_exempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WO-003+ will deny here; prove exempt is consulted, not discarded."""

    def policy(classification: object, _principal: object) -> str:
        return "admit" if getattr(classification, "exempt", False) else "deny"

    monkeypatch.setattr(
        "heatguard.boundary.enforcement.access_decision",
        policy,
    )

    async def inner(scope: dict, receive: object, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    async def send_for(path: str) -> int:
        captured: dict[str, int] = {}

        async def send(message: dict) -> None:
            if message["type"] == "http.response.start":
                captured["code"] = int(message["status"])

        mw = EnforcementMiddleware(inner)
        await mw(
            {"type": "http", "method": "GET", "path": path, "headers": []},
            _receive,
            send,
        )
        return captured["code"]

    import asyncio

    assert asyncio.run(send_for("/health/live")) == 200
    assert asyncio.run(send_for("/sites")) == 403


def test_latency_p99_under_3ms() -> None:
    async def inner(scope: dict, receive: object, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    payload = _api_key_payload()
    session = _session_payload()
    store = load_key_store(
        {
            "HEATGUARD_API_KEY_PEPPER": payload["pepper"],
            "HEATGUARD_API_KEY_DIGESTS": json.dumps(payload["bundle"]),
        }
    )
    session_auth = load_session_auth(
        {
            "HEATGUARD_SESSION_SIGNING_SECRET": session["signing_secret"],
            "HEATGUARD_SESSION_KID": session["kid"],
            "HEATGUARD_IDENTITY_SNAPSHOT": json.dumps(session["principals"]),
        }
    )
    mw = EnforcementMiddleware(inner, key_store=store, session_auth=session_auth)
    keyed = [(b"x-api-key", payload["secrets"]["demo-integrator"].encode("ascii"))]
    jwt_headers = [(b"authorization", f"Bearer {_live_session_token()}".encode("ascii"))]
    import asyncio

    async def once(path: str, headers: list | None = None) -> None:
        await mw(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": headers or [],
            },
            _receive,
            _null_send,
        )

    async def timed(path: str, n: int, headers: list | None = None) -> list[float]:
        samples: list[float] = []
        for _ in range(50):
            await once(path, headers)
        for _ in range(n):
            started = time.perf_counter()
            await once(path, headers)
            samples.append((time.perf_counter() - started) * 1000.0)
        return samples

    def p99(samples: list[float]) -> float:
        ordered = sorted(samples)
        idx = min(len(ordered) - 1, max(0, math.ceil(0.99 * len(ordered)) - 1))
        return ordered[idx]

    probe = asyncio.run(timed("/health/live", 1000))
    business = asyncio.run(timed("/sites", 1000))
    keyed_business = asyncio.run(timed("/sites", 1000, keyed))
    jwt_business = asyncio.run(timed("/sites", 1000, jwt_headers))
    assert p99(probe) < 3.0, p99(probe)
    assert p99(business) < 3.0, p99(business)
    assert p99(keyed_business) < 3.0, p99(keyed_business)
    assert p99(jwt_business) < 3.0, p99(jwt_business)
    # Classifier itself is a pure table lookup (also asserted via AST in unit tests).
    assert classify_request("/health/live", "GET").exempt is True
    assert classify_request("/sites", "GET").exempt is False


async def _receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _null_send(_message: dict) -> None:
    return None
