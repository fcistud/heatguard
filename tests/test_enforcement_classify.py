"""Unit tests for EnforcementMiddleware classification and refusal (WO-002)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from heatguard.boundary.enforcement import (
    EMPTY_PRINCIPAL,
    REFUSAL_CODE_INTERNAL,
    REFUSAL_MESSAGE,
    EnforcementMiddleware,
    UNKNOWN_CLASSIFICATION,
    access_decision,
    canonical_path,
    classification_from_scope,
    classify_request,
    principal_from_scope,
    refusal_body,
)
from heatguard.types import (
    PRINCIPAL_SCOPE_KEY,
    ROUTE_CLASSIFICATION_SCOPE_KEY,
    PrincipalContext,
)

FIXTURE = Path(__file__).parent / "fixtures" / "enforcement_routes.json"
SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "heatguard"
    / "boundary"
    / "enforcement.py"
)


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _route_cases() -> list[dict]:
    return list(_fixture()["routes"])


@pytest.mark.parametrize("case", _route_cases(), ids=lambda c: c["id"])
def test_classify_fixture_routes(case: dict) -> None:
    result = classify_request(case["path"], case["method"])
    assert result.group == case["group"]
    assert result.exempt is case["exempt"]


def test_exempt_path_set_matches_fixture() -> None:
    for path in _fixture()["exempt_paths"]:
        result = classify_request(path, "GET")
        assert result.exempt is True
        assert result.group in {"probes", "metrics"}


def test_canonical_path_trailing_slash() -> None:
    assert canonical_path("/health/") == "/health"
    assert canonical_path("/") == "/"
    assert canonical_path("") == "/"


def test_unknown_path_is_not_exempt() -> None:
    result = classify_request("/totally-unknown", "GET")
    assert result.group == "unknown"
    assert result.exempt is False


def test_refusal_body_shape_matches_fixture() -> None:
    expected = _fixture()["refusal_body"]
    body = refusal_body("abc-123")
    assert set(body) == set(expected["keys"])
    assert body["code"] == expected["code"] == REFUSAL_CODE_INTERNAL
    assert body["message"] == expected["message"] == REFUSAL_MESSAGE
    assert body["request_id"] == "abc-123"
    assert "traceback" not in json.dumps(body).lower()
    assert "stack" not in json.dumps(body).lower()


def test_principal_from_scope_empty_default() -> None:
    assert principal_from_scope({}) == EMPTY_PRINCIPAL
    ctx = PrincipalContext(principal_id="u1", roles=("inspector",))
    attached = principal_from_scope({PRINCIPAL_SCOPE_KEY: ctx})
    assert attached.principal_id == "u1"
    assert attached.roles == ("inspector",)
    assert attached.to_dict()["roles"] == ["inspector"]


def test_classification_from_scope_defaults_unknown() -> None:
    assert classification_from_scope({}) == UNKNOWN_CLASSIFICATION
    classified = classify_request("/health/live", "GET")
    assert classification_from_scope(
        {ROUTE_CLASSIFICATION_SCOPE_KEY: classified}
    ) == classified


def test_access_decision_exempt_and_non_exempt_both_admit() -> None:
    live = classify_request("/health/live", "GET")
    sites = classify_request("/sites", "GET")
    assert live.exempt is True
    assert sites.exempt is False
    assert access_decision(live, EMPTY_PRINCIPAL) == "admit"
    assert access_decision(sites, EMPTY_PRINCIPAL) == "admit"


def test_enforcement_source_has_no_io_calls() -> None:
    """Decision path must stay in-process: no open/Path/httpx in this module."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    forbidden = {"open", "Path", "urlopen"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden:
            raise AssertionError(f"I/O name {node.id!r} in enforcement.py")
        if isinstance(node, ast.Attribute) and node.attr in {"open", "urlopen"}:
            raise AssertionError(f"I/O attribute {node.attr!r} in enforcement.py")
    src = SOURCE.read_text(encoding="utf-8")
    assert "httpx" not in src
    assert "pathlib" not in src
    assert "socket" not in src


def test_websocket_and_lifespan_pass_through() -> None:
    import asyncio

    seen: list[str] = []

    async def inner(scope: dict, receive: object, send: object) -> None:
        seen.append(scope["type"])

    mw = EnforcementMiddleware(inner)

    async def run() -> None:
        await mw({"type": "lifespan"}, _receive, _send)
        await mw({"type": "websocket", "path": "/ws"}, _receive, _send)

    asyncio.run(run())
    assert seen == ["lifespan", "websocket"]


async def _receive() -> dict:
    return {"type": "http.disconnect"}


async def _send(_message: dict) -> None:
    return None
