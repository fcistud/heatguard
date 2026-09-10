"""Schema-level frozen legal contract (WO-012).

Field inventory lives in ``heatguard.contracts.legal_contract`` and mirrors
**docs/SCOPE_GUARDRAIL.md section 8** (API contract). That document is the
authoritative field list; these tests pin it into OpenAPI ``required`` arrays
and live response validation without changing emitted bytes.
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from heatguard._paths import _REPO_ROOT
from heatguard.api import app
from heatguard.contracts import (
    LEGAL_CONTRACT_INVENTORY,
    HourAdvisoryPayload,
    LegalEnvelope,
    TimelineResponse,
    TimelineRow,
)

client = TestClient(app)
FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "legal_contract"
SRC_ROOT = _REPO_ROOT / "src" / "heatguard"
INV = LEGAL_CONTRACT_INVENTORY

# Known demo hours: Riyadh 15 Jul is in the SA midday ban; Dubai 16 May is not.
BANNED_HOUR = "/hour/riyadh/2024-07-15/12"
PERMITTED_HOUR = "/hour/dubai/2025-05-16/12"
BANNED_TIMELINE = "/timeline/riyadh/2024-07-15"
PERMITTED_TIMELINE = "/timeline/dubai/2025-05-16"

_ADVISORY_PATHS = (
    ("/hour/{site_key}/{day}/{hour}", "get"),
    ("/decide", "post"),
    ("/timeline/{site_key}/{day}", "get"),
)


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _resolve_schema(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Resolve ``$ref`` recursively, merging sibling keywords (OpenAPI 3.0)."""

    def rec(node: Any, seen: frozenset[str]) -> Any:
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        extras = {k: v for k, v in node.items() if k != "$ref"}
        resolved: dict[str, Any] = {}
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name not in seen:
                target = components["schemas"][name]
                resolved = rec(target, seen | {name})
        merged = {**resolved, **{k: rec(v, seen) for k, v in extras.items()}}
        if "properties" in resolved or "properties" in extras:
            merged["properties"] = {
                **rec(resolved.get("properties") or {}, seen),
                **rec(extras.get("properties") or {}, seen),
            }
        required: list[str] = []
        for src in (resolved, extras):
            for item in src.get("required") or []:
                if item not in required:
                    required.append(item)
        if required:
            merged["required"] = required
        for key in ("allOf", "anyOf", "oneOf"):
            if key in merged:
                merged[key] = [rec(part, seen) for part in merged[key]]
        if "items" in merged:
            merged["items"] = rec(merged["items"], seen)
        return merged

    return rec(schema, frozenset())


def _response_schema(spec: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    op = spec["paths"][path][method]
    raw = op["responses"]["200"]["content"]["application/json"]["schema"]
    return _resolve_schema(raw, spec.get("components") or {})


def _assert_required(schema: dict[str, Any], fields: tuple[str, ...]) -> None:
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    missing_props = [f for f in fields if f not in props]
    missing_req = [f for f in fields if f not in required]
    assert not missing_props, f"missing properties {missing_props} in {sorted(props)}"
    assert not missing_req, f"not in required {missing_req}; required={sorted(required)}"
    for field in fields:
        prop = props[field]
        assert prop.get("nullable") is not True, field
        if "anyOf" in prop:
            assert not any(
                isinstance(p, dict) and p.get("type") == "null" for p in prop["anyOf"]
            ), field


def _assert_not_response_model(path: str, method: str) -> None:
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        methods = getattr(route, "methods", None) or set()
        if method.upper() not in methods:
            continue
        model = getattr(route, "response_model", None)
        assert not (
            isinstance(model, type) and issubclass(model, BaseModel)
        ), f"{path} {method} has response_model={model}"
        return
    raise AssertionError(f"route not found: {method} {path}")


# ---- model-level required-ness ----------------------------------------------


def test_compliant_fixture_validates_hour_and_timeline_row() -> None:
    payload = _load_fixture("compliant.json")
    HourAdvisoryPayload.model_validate(payload)
    TimelineRow.model_validate(payload)
    TimelineResponse.model_validate({"rows": [payload], "site": "fixture"})
    LegalEnvelope.model_validate(payload["legal"])


@pytest.mark.parametrize("field", INV.hour_fields)
def test_hour_payload_rejects_omitted_field(field: str) -> None:
    payload = _load_fixture("compliant.json")
    del payload[field]
    with pytest.raises(ValidationError):
        HourAdvisoryPayload.model_validate(payload)


@pytest.mark.parametrize("field", INV.legal_fields)
def test_legal_envelope_rejects_omitted_field(field: str) -> None:
    payload = _load_fixture("compliant.json")
    del payload["legal"][field]
    with pytest.raises(ValidationError):
        LegalEnvelope.model_validate(payload["legal"])
    with pytest.raises(ValidationError):
        HourAdvisoryPayload.model_validate(payload)


@pytest.mark.parametrize("field", INV.timeline_lanes)
def test_timeline_row_rejects_omitted_lane(field: str) -> None:
    payload = _load_fixture("compliant.json")
    del payload[field]
    with pytest.raises(ValidationError):
        TimelineRow.model_validate(payload)


def test_missing_effective_advisory_fixture_fails() -> None:
    payload = _load_fixture("missing_effective_advisory.json")
    assert "effective_advisory" not in payload
    with pytest.raises(ValidationError):
        HourAdvisoryPayload.model_validate(payload)


def test_missing_newcomer_effective_fixture_fails() -> None:
    payload = _load_fixture("missing_newcomer_effective.json")
    assert "newcomer_effective" not in payload
    with pytest.raises(ValidationError):
        TimelineRow.model_validate(payload)


def test_extra_keys_do_not_fail_contract() -> None:
    payload = _load_fixture("compliant.json")
    assert "extra_additive_key" in payload
    HourAdvisoryPayload.model_validate(payload)
    TimelineRow.model_validate(payload)


# ---- OpenAPI required-array membership --------------------------------------


def test_openapi_hour_and_decide_require_legal_fields() -> None:
    spec = app.openapi()
    for path, method in (
        ("/hour/{site_key}/{day}/{hour}", "get"),
        ("/decide", "post"),
    ):
        schema = _response_schema(spec, path, method)
        _assert_required(schema, INV.hour_fields)
        legal = schema["properties"]["legal"]
        _assert_required(legal, INV.legal_fields)
        _assert_not_response_model(path, method)


def test_openapi_timeline_row_requires_four_lanes() -> None:
    spec = app.openapi()
    wrapper = _response_schema(spec, "/timeline/{site_key}/{day}", "get")
    _assert_required(wrapper, ("rows",))
    row = wrapper["properties"]["rows"]["items"]
    _assert_required(row, INV.timeline_lanes)
    _assert_required(row, ("legal",))
    _assert_required(row["properties"]["legal"], INV.legal_fields)
    _assert_not_response_model("/timeline/{site_key}/{day}", "get")


def test_advisory_routes_publish_contract_components() -> None:
    spec = app.openapi()
    names = set((spec.get("components") or {}).get("schemas") or {})
    assert "HourAdvisoryPayload" in names
    assert "TimelineResponse" in names
    assert "TimelineRow" in names
    assert "LegalEnvelope" in names
    for path, method in _ADVISORY_PATHS:
        assert path in spec["paths"], path
        assert method in spec["paths"][path], method


# ---- runtime conformance ----------------------------------------------------


def _validate_hour(body: dict[str, Any]) -> HourAdvisoryPayload:
    return HourAdvisoryPayload.model_validate(body)


def _validate_timeline(body: dict[str, Any]) -> TimelineResponse:
    return TimelineResponse.model_validate(body)


def test_runtime_hour_banned_and_permitted() -> None:
    banned = client.get(BANNED_HOUR)
    permitted = client.get(PERMITTED_HOUR)
    assert banned.status_code == 200
    assert permitted.status_code == 200
    banned_body = banned.json()
    permitted_body = permitted.json()
    _validate_hour(banned_body)
    _validate_hour(permitted_body)
    assert banned_body["legal"]["banned"] is True
    assert permitted_body["legal"]["banned"] is False
    assert "WORK" not in banned_body["live"]


def test_runtime_timeline_banned_and_permitted() -> None:
    banned = client.get(BANNED_TIMELINE)
    permitted = client.get(PERMITTED_TIMELINE)
    assert banned.status_code == 200
    assert permitted.status_code == 200
    banned_body = banned.json()
    permitted_body = permitted.json()
    _validate_timeline(banned_body)
    _validate_timeline(permitted_body)
    banned_rows = [r for r in banned_body["rows"] if r["legal"]["banned"]]
    permitted_rows = [r for r in permitted_body["rows"] if not r["legal"]["banned"]]
    assert banned_rows, "expected at least one banned timeline row"
    assert permitted_rows, "expected at least one permitted timeline row"
    for row in banned_rows + permitted_rows:
        TimelineRow.model_validate(row)


def test_runtime_timeline_protective_signal_still_validates_when_banned() -> None:
    body = client.get(BANNED_TIMELINE).json()
    protective = next(
        (
            row
            for row in body["rows"]
            if row["legal"]["banned"]
            and row["veteran"]["signal"] in {"REST_IN_SHADE", "DRINK_NOW", "STOP"}
        ),
        None,
    )
    if protective is None:
        pytest.skip("no banned protective-signal row on the riyadh focus day")
    TimelineRow.model_validate(protective)
    assert protective["veteran_effective"]["cycle"]["work_min_per_hour"] == 0 or (
        protective["veteran"]["cycle"]["work_min_per_hour"] == 0
    )


def test_runtime_decide_banned_and_permitted(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = datetime(2024, 7, 15, 8, 0, tzinfo=timezone(timedelta(hours=3)))

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            return frozen if tz is None else frozen.astimezone(tz)

    monkeypatch.setattr("heatguard.service.datetime", _FrozenDateTime)
    banned = client.post(
        "/decide",
        json={"site_key": "riyadh", "tdb": 26, "rh": 40, "hour": 12, "intensity": "heavy"},
    )
    permitted = client.post(
        "/decide",
        json={"site_key": "riyadh", "tdb": 26, "rh": 40, "hour": 8, "intensity": "heavy"},
    )
    assert banned.status_code == 200, banned.text
    assert permitted.status_code == 200, permitted.text
    banned_body = banned.json()
    permitted_body = permitted.json()
    _validate_hour(banned_body)
    _validate_hour(permitted_body)
    assert banned_body["legal"]["banned"] is True
    assert permitted_body["legal"]["banned"] is False


# ---- single-emitter scan ----------------------------------------------------


_EFFECTIVE_KEY = "effective_advisory"


def _construction_lines(tree: ast.AST) -> list[int]:
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value == _EFFECTIVE_KEY:
                    hits.append(getattr(node, "lineno", 0))
        elif isinstance(node, ast.Subscript):
            sl = node.slice
            if isinstance(sl, ast.Constant) and sl.value == _EFFECTIVE_KEY:
                ctx = getattr(node, "ctx", None)
                if isinstance(ctx, ast.Store):
                    hits.append(getattr(node, "lineno", 0))
        elif isinstance(node, ast.keyword) and node.arg == _EFFECTIVE_KEY:
            hits.append(getattr(node, "lineno", 0))
    return hits


def test_single_emitter_operational_payload() -> None:
    """Only ``legal_precedence.operational_payload`` constructs the key literally."""
    allowed = {SRC_ROOT / "legal_precedence.py"}
    offenders: list[str] = []
    emitter_hits = 0
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "contracts" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hits = _construction_lines(tree)
        if path in allowed:
            emitter_hits += len(hits)
            continue
        if hits:
            rel = path.relative_to(_REPO_ROOT)
            offenders.append(f"{rel}:{hits}")
    assert not offenders, "effective_advisory constructed outside legal_precedence: " + "; ".join(
        offenders
    )
    assert emitter_hits >= 1, "legal_precedence.py must construct effective_advisory"
