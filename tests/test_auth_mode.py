"""Auth-mode resolver and dual→enforce cutover (WO-005).

Characterization of *today* (after WO-003/004): anonymous non-exempt requests
still admit, and ``auth.deprecated_anonymous`` is already emitted. The work
order's ``current_behavior`` (no caller) is stale — do not assert the old
silence.
"""
from __future__ import annotations

import ast
import io
import json
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("structlog")

import structlog
from fastapi.testclient import TestClient

from heatguard.api import app, bind_auth_modes
from heatguard.boundary.auth_mode import (
    AuthMode,
    principal_permits_route,
    resolve_auth_modes,
    site_key_from_path,
)
from heatguard.boundary.cors_config import ConfigurationError
from heatguard.boundary.enforcement import (
    EMPTY_PRINCIPAL,
    REFUSAL_CODE_FORBIDDEN,
    REFUSAL_CODE_UNAUTHENTICATED,
    access_decision,
    classify_request,
)
from heatguard.boundary.session_tokens import default_claims, mint_session_token
from heatguard.observability import AUTH_DEPRECATED_ANONYMOUS, configure_logging
from heatguard.observability import logging as obs_logging
from heatguard.types import PrincipalContext

client = TestClient(app)


@pytest.fixture
def captured_logs():
    from heatguard.observability import degradation as deg

    deg.clear_degradation_state()
    entries: list[dict[str, Any]] = []

    def _capture(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        entries.append(dict(event_dict))
        return event_dict

    sink = io.StringIO()
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            obs_logging._merge_request_context,
            obs_logging._iso_utc_timestamp,
            structlog.stdlib.add_log_level,
            obs_logging._cloud_severity,
            obs_logging.redact_processor,
            _capture,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(file=sink),
        cache_logger_on_first_use=False,
    )
    yield entries
    sink.close()
    deg.clear_degradation_state()
    configure_logging(level="INFO")


def test_characterization_anonymous_business_route_succeeds() -> None:
    resp = client.get("/sites")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert resp.json()


def test_characterization_anonymous_emits_deprecated_anonymous(
    captured_logs: list[dict],
) -> None:
    resp = client.get("/sites")
    assert resp.status_code == 200
    events = [e for e in captured_logs if e.get("event") == AUTH_DEPRECATED_ANONYMOUS]
    assert len(events) == 1
    assert events[0]["route"] == "/sites"
    assert "request_id" in events[0]


FIXTURE = Path(__file__).parent / "fixtures" / "auth_modes.json"
SESSION_FIXTURE = Path(__file__).parent / "fixtures" / "session_tokens.json"
SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "heatguard"
    / "boundary"
    / "auth_mode.py"
)


def _matrix() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def set_auth_modes():
    def _apply(env: dict[str, str]) -> None:
        bind_auth_modes(app, env)

    yield _apply
    bind_auth_modes(app, {})


def _session_token(*, sub: str, roles: list[str], sites: list[str]) -> str:
    payload = json.loads(SESSION_FIXTURE.read_text(encoding="utf-8"))
    now = int(time.time())
    return mint_session_token(
        secret=payload["signing_secret"],
        claims=default_claims(
            sub=sub,
            now=now,
            roles=roles,
            sites=sites,
            token_version=payload["principals"][sub]["token_version"],
        ),
        kid=payload["kid"],
    )


@pytest.mark.parametrize("case", _matrix()["cases"], ids=lambda c: c["id"])
def test_resolve_auth_modes_matrix(case: dict) -> None:
    snapshot = resolve_auth_modes(case["env"])
    assert snapshot.baseline.value == case["baseline"]
    got_overrides = {name: mode.value for name, mode in snapshot.overrides}
    assert got_overrides == case["overrides"]
    for group, expected in case["expect"].items():
        assert snapshot.mode_for(group).value == expected


@pytest.mark.parametrize("case", _matrix()["invalid"], ids=lambda c: c["id"])
def test_resolve_auth_modes_invalid_fails_boot(case: dict) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        resolve_auth_modes(case["env"])
    assert case["variable"] in str(excinfo.value)


def test_unknown_group_follows_baseline() -> None:
    dual = resolve_auth_modes({})
    assert dual.mode_for("unknown") is AuthMode.DUAL
    enforce = resolve_auth_modes({"HEATGUARD_AUTH_MODE": "enforce"})
    assert enforce.mode_for("unknown") is AuthMode.ENFORCE


def test_site_key_from_path() -> None:
    assert site_key_from_path("/demo/dubai") == "dubai"
    assert site_key_from_path("/hour/riyadh/2025-05-16/12") == "riyadh"
    assert site_key_from_path("/compliance/dubai/export") == "dubai"
    assert site_key_from_path("/sites") is None
    assert site_key_from_path("/decide") is None


def test_principal_permits_route_site_scope() -> None:
    supervisor = PrincipalContext(
        principal_id="dashboard-supervisor",
        key_class="dashboard",
        roles=("supervisor",),
        sites=("dubai",),
    )
    inspector = PrincipalContext(
        principal_id="dashboard-inspector",
        key_class="dashboard",
        roles=("inspector",),
        sites=("*",),
    )
    wildcard_supervisor = PrincipalContext(
        principal_id="bad",
        roles=("supervisor",),
        sites=("*",),
    )
    api_key = PrincipalContext(principal_id="demo-integrator", key_class="demo")
    assert principal_permits_route("/demo/dubai", supervisor) is True
    assert principal_permits_route("/demo/riyadh", supervisor) is False
    assert principal_permits_route("/demo/riyadh", inspector) is True
    assert principal_permits_route("/demo/riyadh", wildcard_supervisor) is False
    assert principal_permits_route("/demo/riyadh", api_key) is True
    assert principal_permits_route("/sites", supervisor) is True
    assert principal_permits_route("/demo/dubai", EMPTY_PRINCIPAL) is False


def test_access_decision_dual_vs_enforce() -> None:
    classified = classify_request("/sites", "GET")
    assert access_decision(classified, EMPTY_PRINCIPAL) == "admit"
    assert (
        access_decision(
            classified, EMPTY_PRINCIPAL, mode=AuthMode.ENFORCE, path="/sites"
        )
        == "deny"
    )
    live = classify_request("/health/live", "GET")
    assert (
        access_decision(live, EMPTY_PRINCIPAL, mode=AuthMode.ENFORCE, path="/health/live")
        == "admit"
    )


def test_auth_mode_source_has_no_io_calls() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    forbidden = {"open", "Path", "urlopen"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden:
            raise AssertionError(f"I/O name {node.id!r} in auth_mode.py")
        if isinstance(node, ast.Attribute) and node.attr in {"open", "urlopen"}:
            raise AssertionError(f"I/O attribute {node.attr!r} in auth_mode.py")
    src = SOURCE.read_text(encoding="utf-8")
    assert "httpx" not in src
    assert "pathlib" not in src
    assert "socket" not in src


def test_anonymous_dual_emits_group_and_origin(
    captured_logs: list[dict], set_auth_modes: Any
) -> None:
    set_auth_modes({})
    resp = client.get(
        "/sites",
        headers={"Origin": "http://localhost:5173", "User-Agent": "wo005-test"},
    )
    assert resp.status_code == 200
    events = [e for e in captured_logs if e.get("event") == AUTH_DEPRECATED_ANONYMOUS]
    assert len(events) == 1
    event = events[0]
    assert event["route"] == "/sites"
    assert event["route_group"] == "reference"
    assert event["origin"] == "http://localhost:5173"
    assert event["user_agent"] == "wo005-test"
    assert event["request_id"]


def test_anonymous_enforce_returns_401_without_event(
    captured_logs: list[dict], set_auth_modes: Any
) -> None:
    set_auth_modes({"HEATGUARD_AUTH_MODE": "enforce"})
    resp = client.get("/sites")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == REFUSAL_CODE_UNAUTHENTICATED
    assert body["message"] == "Request refused."
    assert "request_id" in body
    assert "traceback" not in resp.text.lower()
    events = [e for e in captured_logs if e.get("event") == AUTH_DEPRECATED_ANONYMOUS]
    assert events == []


def test_probes_remain_open_when_baseline_is_enforce(
    set_auth_modes: Any,
) -> None:
    set_auth_modes({"HEATGUARD_AUTH_MODE": "enforce"})
    live = client.get("/health/live")
    metrics = client.get("/metrics")
    assert live.status_code == 200
    assert metrics.status_code in (200, 404)


def test_single_group_revert_leaves_others_enforced(
    set_auth_modes: Any,
) -> None:
    set_auth_modes(
        {
            "HEATGUARD_AUTH_MODE": "enforce",
            "HEATGUARD_AUTH_MODE_REFERENCE": "dual",
        }
    )
    assert client.get("/sites").status_code == 200
    denied = client.get("/demo/dubai")
    assert denied.status_code == 401
    assert denied.json()["code"] == REFUSAL_CODE_UNAUTHENTICATED


def test_enforce_wrong_site_returns_403(set_auth_modes: Any) -> None:
    set_auth_modes({"HEATGUARD_AUTH_MODE_ADVISORY": "enforce"})
    token = _session_token(
        sub="dashboard-supervisor",
        roles=["supervisor"],
        sites=["dubai"],
    )
    denied = client.get(
        "/demo/riyadh",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == REFUSAL_CODE_FORBIDDEN
    assert "traceback" not in denied.text.lower()
    allowed = client.get(
        "/demo/dubai",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert allowed.status_code == 200


def test_enforce_inspector_wildcard_permits_other_site(set_auth_modes: Any) -> None:
    set_auth_modes({"HEATGUARD_AUTH_MODE_ADVISORY": "enforce"})
    token = _session_token(
        sub="dashboard-inspector",
        roles=["inspector"],
        sites=["*"],
    )
    resp = client.get(
        "/demo/riyadh",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_malformed_credential_in_enforce_is_401_not_anonymous(
    captured_logs: list[dict], set_auth_modes: Any
) -> None:
    set_auth_modes({"HEATGUARD_AUTH_MODE": "enforce"})
    resp = client.get("/sites", headers={"X-API-Key": "not-a-real-key"})
    assert resp.status_code == 401
    events = [e for e in captured_logs if e.get("event") == AUTH_DEPRECATED_ANONYMOUS]
    assert events == []
