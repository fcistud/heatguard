"""Route-table coverage gate for EnforcementMiddleware (WO-006).

The gate enumerates the assembled FastAPI ``app.routes`` table (including
``include_in_schema=False`` routers and static mounts), classifies every
method-path pair with the production ``classify_request`` helper, and diffs
the result against ``tests/fixtures/route_inventory.json``.

Deliberate-break drill (executed 2026-08-29 on ``fix/route-coverage``):
1. Temporarily registered ``GET /__wo006_unclassified__`` on ``heatguard.api.app``
   with no ``_ROUTE_SPEC`` entry. The gate failed with an ``added`` row and an
   ``unclassified (no group assignment)`` row for that path.
2. Reverted the route. The gate passed.
3. Temporarily marked ``GET /sites`` exempt in ``_ROUTE_SPEC``. The gate failed
   with a distinct ``reclassified`` row plus ``exempt set`` extra ``/sites``
   (and ``non-probe business routes marked exempt``).
4. Reverted the spec. The gate passed.

Do not auto-heal the fixture. Classify new routes in
``src/heatguard/boundary/enforcement.py`` (``_ROUTE_SPEC``) and update the
inventory in the same change; do not bump ``non_probe_count`` blindly.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from heatguard.api import app  # noqa: E402
from heatguard.boundary.enforcement import HEADER_ROUTE_GROUP, classify_request  # noqa: E402
from route_coverage_gate import (  # noqa: E402
    EXEMPT_PATHS,
    KIND_MOUNT,
    KIND_ROUTE,
    NON_PROBE_ROUTE_COUNT,
    collect_live_route_entries,
    coverage_report,
    format_coverage_failure,
    report_is_clean,
)

FIXTURE = Path(__file__).parent / "fixtures" / "route_inventory.json"
ROUTE_GROUP_HEADER = HEADER_ROUTE_GROUP.decode("ascii")
GATE_SOURCE = Path(__file__).parent / "route_coverage_gate.py"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def assert_live_route_coverage() -> None:
    """Fail with a structured added/removed/reclassified report (WO-006)."""
    fixture = _fixture()
    live = collect_live_route_entries(app)
    report = coverage_report(live, fixture)
    if not report_is_clean(report):
        raise AssertionError(format_coverage_failure(report))


def test_live_route_coverage_gate() -> None:
    started = time.perf_counter()
    assert_live_route_coverage()
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0, elapsed


def test_gate_imports_production_classifier() -> None:
    src = GATE_SOURCE.read_text(encoding="utf-8")
    assert "from heatguard.boundary.enforcement import classify_request" in src
    assert "def classify_request" not in src
    live = collect_live_route_entries(app)
    sites = next(row for row in live if row["path"] == "/sites" and row["method"] == "GET")
    production = classify_request("/sites", "GET")
    assert sites["group"] == production.group
    assert sites["exempt"] is production.exempt


def test_exempt_set_is_exactly_probes_plus_metrics() -> None:
    fixture = _fixture()
    assert tuple(fixture["exempt_paths"]) == EXEMPT_PATHS
    live = collect_live_route_entries(app)
    live_exempt = sorted(
        {row["path"] for row in live if row["kind"] == KIND_ROUTE and row["exempt"]}
    )
    assert live_exempt == list(EXEMPT_PATHS)
    for path in EXEMPT_PATHS:
        result = classify_request(path, "GET")
        assert result.exempt is True
        assert result.group in {"probes", "metrics"}


def test_non_probe_count_is_pinned() -> None:
    fixture = _fixture()
    assert fixture["non_probe_count"] == NON_PROBE_ROUTE_COUNT
    assert "do not bump" in fixture["non_probe_count_note"].lower()
    live = collect_live_route_entries(app)
    required_keys = {
        (row["kind"], row["path"], row.get("method") or "")
        for row in fixture["entries"]
    }
    required_live = [
        row
        for row in live
        if (row["kind"], row["path"], row.get("method") or "") in required_keys
    ]
    non_probe = [row for row in required_live if row["group"] != "probes"]
    assert len(non_probe) == NON_PROBE_ROUTE_COUNT


def test_health_alias_and_trailing_slash_both_inventoried() -> None:
    paths = {(row["path"], row["method"]) for row in _fixture()["entries"]}
    assert ("/health", "GET") in paths
    assert ("/health/", "GET") in paths
    live = {(row["path"], row["method"]) for row in collect_live_route_entries(app)}
    assert ("/health", "GET") in live
    assert ("/health/", "GET") in live


def test_private_metrics_enumerated_despite_schema_exclusion() -> None:
    schema_paths = set(app.openapi()["paths"])
    assert "/metrics" not in schema_paths
    live = collect_live_route_entries(app)
    metrics = [row for row in live if row["path"] == "/metrics"]
    assert len(metrics) == 1
    assert metrics[0]["method"] == "GET"
    assert classify_request("/metrics", "GET").group == "metrics"


def test_mount_private_routes_does_not_duplicate_metrics() -> None:
    from heatguard import api as heatguard_api

    heatguard_api.mount_private_routes(heatguard_api.app)
    heatguard_api.mount_private_routes(heatguard_api.app)
    live = collect_live_route_entries(heatguard_api.app)
    metrics = [row for row in live if row["path"] == "/metrics"]
    assert len(metrics) == 1


def test_inventory_uses_fastapi_path_format_strings() -> None:
    for row in _fixture()["entries"]:
        assert "dubai" not in row["path"]
        assert "2025-05-16" not in row["path"]
    paths = {row["path"] for row in _fixture()["entries"]}
    assert "/timeline/{site_key}/{day}" in paths
    assert "/hour/{site_key}/{day}/{hour}" in paths
    assert "/demo/{site_key}" in paths
    assert "/compliance/{site_key}/export" in paths


def test_static_mounts_are_listed_explicitly() -> None:
    fixture = _fixture()
    mounts = [row for row in fixture["entries"] if row["kind"] == KIND_MOUNT]
    assert mounts == [
        {
            "kind": KIND_MOUNT,
            "path": "/",
            "method": "",
            "name": "landing",
            "group": "static",
            "exempt": False,
        }
    ]
    optional = fixture["optional_entries"]
    optional_paths = {row["path"] for row in optional}
    assert optional_paths == {"/dashboard"}
    live_mounts = [
        row for row in collect_live_route_entries(app) if row["kind"] == KIND_MOUNT
    ]
    live_mount_paths = {row["path"] for row in live_mounts}
    assert "/" in live_mount_paths
    for row in live_mounts:
        assert row["path"] in {"/", "/dashboard"}
        assert classify_request(row["path"], "GET").group == "static"


def test_method_path_pairs_are_separate_rows() -> None:
    rows = [
        (row["path"], row["method"])
        for row in _fixture()["entries"]
        if row["path"] == "/openapi.json"
    ]
    assert ("/openapi.json", "GET") in rows
    assert ("/openapi.json", "HEAD") in rows
    policy = [
        (row["path"], row["method"])
        for row in _fixture()["entries"]
        if row["path"] == "/policy/query"
    ]
    assert policy == [("/policy/query", "POST")]


@pytest.mark.parametrize(
    "path,method,group",
    [
        ("/health/live", "GET", "probes"),
        ("/metrics", "GET", "metrics"),
        ("/auth/session", "GET", "session"),
        ("/demo/dubai", "GET", "advisory"),
        ("/sites", "GET", "reference"),
        ("/", "GET", "static"),
    ],
)
def test_enforcement_pass_traversed_per_group(
    path: str, method: str, group: str
) -> None:
    client = TestClient(app)
    if method == "GET":
        resp = client.get(path, follow_redirects=False)
    else:
        resp = client.request(method, path, follow_redirects=False)
    assert resp.headers.get(ROUTE_GROUP_HEADER) == group
    assert resp.status_code != 403


def test_gate_fails_on_added_unclassified_route() -> None:
    fixture = _fixture()
    live = collect_live_route_entries(app)
    extra = {
        "kind": KIND_ROUTE,
        "path": "/__wo006_unclassified__",
        "method": "GET",
        "name": "wo006_drill",
        "group": "unknown",
        "exempt": False,
    }
    report = coverage_report([*live, extra], fixture)
    assert report_is_clean(report) is False
    message = format_coverage_failure(report)
    assert "added:" in message
    assert "unclassified (no group assignment):" in message
    assert "/__wo006_unclassified__" in message
    assert "_ROUTE_SPEC" in message


def test_gate_fails_distinctly_when_business_route_marked_exempt() -> None:
    fixture = _fixture()
    live = collect_live_route_entries(app)
    mutated_live = []
    for row in live:
        if row["path"] == "/sites" and row["method"] == "GET":
            mutated_live.append({**row, "exempt": True})
        else:
            mutated_live.append(row)
    report = coverage_report(mutated_live, fixture)
    assert report_is_clean(report) is False
    message = format_coverage_failure(report)
    assert "reclassified:" in message
    assert "extra: /sites" in message
    assert "non-probe business routes marked exempt:" in message
    assert "added:" not in message
    assert "unclassified (no group assignment):" not in message


def test_gate_reports_removed_routes_separately() -> None:
    fixture = _fixture()
    live = [
        row
        for row in collect_live_route_entries(app)
        if not (row["path"] == "/backtest" and row["method"] == "GET")
    ]
    report = coverage_report(live, fixture)
    message = format_coverage_failure(report)
    assert "removed:" in message
    assert "/backtest" in message
    assert "added:" not in message
