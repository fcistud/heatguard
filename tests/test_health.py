"""Unit and integration tests for liveness / readiness probes (WO-012)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from heatguard import health as health_mod  # noqa: E402
from heatguard._paths import _REPO_ROOT  # noqa: E402
from heatguard.api import app  # noqa: E402
from heatguard.health import (  # noqa: E402
    EXPECTED_SITE_COUNT,
    DependencyCheck,
    clear_readiness_cache,
    get_readiness,
    liveness,
    run_readiness,
)
from heatguard.sites import load_sites  # noqa: E402

FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "health"
VALID_DATA = FIXTURES / "valid"
BROKEN_DATA = FIXTURES / "broken"


@pytest.fixture(autouse=True)
def _clear_ready_cache() -> None:
    clear_readiness_cache()
    yield
    clear_readiness_cache()


def test_liveness_has_version_and_uptime_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live payload is process-only — no sites/manifest/httpx work."""
    calls: list[str] = []

    def boom_sites() -> dict:
        calls.append("sites")
        raise AssertionError("load_sites must not run during liveness")

    def boom_manifest() -> dict:
        calls.append("manifest")
        raise AssertionError("load_manifest must not run during liveness")

    monkeypatch.setattr("heatguard.sites.load_sites", boom_sites)
    monkeypatch.setattr("heatguard.datasets.load_manifest", boom_manifest)

    import httpx

    def boom_get(*_a, **_k):
        calls.append("httpx")
        raise AssertionError("httpx must not run during liveness")

    monkeypatch.setattr(httpx, "get", boom_get)

    body = liveness()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]
    assert isinstance(body["uptime_seconds"], (int, float))
    assert body["uptime_seconds"] >= 0
    assert calls == []


def test_ready_all_hard_ok_with_injected_checkers() -> None:
    checkers = [
        DependencyCheck("hard_ok", "hard", lambda: None),
        DependencyCheck("opt_ok", "optional", lambda: None),
    ]
    result = run_readiness(checkers)
    assert result.status == "ready"
    assert result.failed == []
    assert result.degraded == []


def test_ready_degraded_when_optional_fails() -> None:
    checkers = [
        DependencyCheck("hard_ok", "hard", lambda: None),
        DependencyCheck("risk_model", "optional", lambda: "heuristic fallback"),
    ]
    result = run_readiness(checkers)
    assert result.status == "degraded"
    assert result.failed == []
    assert any("risk_model" in d for d in result.degraded)


def test_ready_not_ready_when_hard_fails() -> None:
    checkers = [
        DependencyCheck("sites_registry", "hard", lambda: "missing locales"),
        DependencyCheck("risk_model", "optional", lambda: "heuristic fallback"),
    ]
    result = run_readiness(checkers)
    assert result.status == "not_ready"
    assert any("sites_registry" in f for f in result.failed)
    # Optional failures still reported, but hard drives status.
    assert any("risk_model" in d for d in result.degraded)


def test_readiness_never_constructs_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def boom(*_a, **_k):
        raise AssertionError("readiness must not construct outbound HTTP clients")

    monkeypatch.setattr(httpx, "Client", boom)
    monkeypatch.setattr(httpx, "AsyncClient", boom)
    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setattr(httpx, "request", boom)

    # Force evaluation against the real checkers once (uses repo data/).
    clear_readiness_cache()
    result = get_readiness(force=True)
    assert result.status in {"ready", "degraded", "not_ready"}


def test_readiness_memoisation_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def counting() -> str | None:
        calls["n"] += 1
        return None

    monkeypatch.setattr(
        health_mod,
        "default_checkers",
        lambda: [DependencyCheck("once", "hard", counting)],
    )
    monkeypatch.setenv("HEATGUARD_READINESS_TTL_SECONDS", "60")
    clear_readiness_cache()
    a = get_readiness(force=True)
    b = get_readiness(force=False)
    assert a.status == "ready" and b.status == "ready"
    assert calls["n"] == 1


def test_api_live_and_ready_headers() -> None:
    client = TestClient(app)
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.headers.get("cache-control") == "no-store"
    body = live.json()
    assert body["status"] == "ok"
    assert "version" in body and "uptime_seconds" in body

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.headers.get("cache-control") == "no-store"
    rbody = ready.json()
    assert rbody["status"] in {"ready", "degraded"}
    assert "failed" in rbody and "degraded" in rbody


def test_api_ready_503_when_data_dir_broken(monkeypatch: pytest.MonkeyPatch) -> None:
    """Boot against broken HEATGUARD_DATA_DIR: live 200, ready 503."""
    import heatguard._paths as paths

    monkeypatch.setattr(paths, "DATA_DIR", BROKEN_DATA)
    monkeypatch.setenv("HEATGUARD_DATA_DIR", str(BROKEN_DATA))
    load_sites.cache_clear()
    clear_readiness_cache()

    client = TestClient(app)
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = client.get("/health/ready")
    assert ready.status_code == 503
    body = ready.json()
    assert body["status"] == "not_ready"
    assert body["failed"]


def test_check_sites_allows_more_than_expected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extra locales must not fail readiness (forward-compatible registry growth)."""
    monkeypatch.setattr(
        "heatguard.sites.load_sites",
        lambda: {f"s{i}": object() for i in range(EXPECTED_SITE_COUNT + 2)},
    )
    assert health_mod._check_sites() is None


def test_check_sites_fails_when_below_expected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "heatguard.sites.load_sites",
        lambda: {f"s{i}": object() for i in range(EXPECTED_SITE_COUNT - 1)},
    )
    reason = health_mod._check_sites()
    assert reason is not None
    assert "at least" in reason


def test_valid_fixture_satisfies_hard_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    import heatguard._paths as paths
    from heatguard.sites import load_sites as ls

    monkeypatch.setattr(paths, "DATA_DIR", VALID_DATA)
    ls.cache_clear()
    clear_readiness_cache()

    hard_only = [
        c
        for c in health_mod.default_checkers()
        if c.kind == "hard"
    ]
    result = run_readiness(hard_only)
    assert result.status == "ready", result.failed
