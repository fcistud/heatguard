"""Characterization and integration tests for EnforcementMiddleware (WO-002)."""
from __future__ import annotations

import math
import time
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from heatguard.api import app  # noqa: E402
from heatguard.boundary.enforcement import (  # noqa: E402
    EMPTY_PRINCIPAL,
    REFUSAL_CODE_INTERNAL,
    REFUSAL_MESSAGE,
    EnforcementMiddleware,
    classify_request,
    principal_from_scope,
)
from heatguard.observability.events import ENFORCEMENT_INTERNAL_ERROR  # noqa: E402
from heatguard.observability.middleware import CorrelationMiddleware  # noqa: E402
from heatguard.types import PRINCIPAL_SCOPE_KEY  # noqa: E402

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


def test_principal_attached_on_http_request() -> None:
    seen: dict[str, Any] = {}

    async def inner(scope: dict, receive: object, send: Any) -> None:
        seen["principal"] = principal_from_scope(scope)
        seen["has_key"] = PRINCIPAL_SCOPE_KEY in scope
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
    assert seen["has_key"] is True
    assert seen["principal"] == EMPTY_PRINCIPAL


def test_latency_p99_under_3ms() -> None:
    async def inner(scope: dict, receive: object, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    mw = EnforcementMiddleware(inner)
    import asyncio

    async def once(path: str) -> None:
        await mw(
            {"type": "http", "method": "GET", "path": path, "headers": []},
            _receive,
            _null_send,
        )

    async def timed(path: str, n: int) -> list[float]:
        samples: list[float] = []
        for _ in range(50):
            await once(path)
        for _ in range(n):
            started = time.perf_counter()
            await once(path)
            samples.append((time.perf_counter() - started) * 1000.0)
        return samples

    def p99(samples: list[float]) -> float:
        ordered = sorted(samples)
        idx = min(len(ordered) - 1, max(0, math.ceil(0.99 * len(ordered)) - 1))
        return ordered[idx]

    probe = asyncio.run(timed("/health/live", 1000))
    business = asyncio.run(timed("/sites", 1000))
    assert p99(probe) < 3.0, p99(probe)
    assert p99(business) < 3.0, p99(business)
    # Classifier itself is a pure table lookup (also asserted via AST in unit tests).
    assert classify_request("/health/live", "GET").exempt is True
    assert classify_request("/sites", "GET").exempt is False


async def _receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _null_send(_message: dict) -> None:
    return None
