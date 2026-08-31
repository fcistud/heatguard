"""Token-bucket quota in the enforcement pass (WO-007).

Characterization of *today* (after WO-005): a modest flood still receives
no 429 under the generous default bucket. Tight-capacity tests bind a
fresh store so they cannot starve the rest of the suite.
"""
from __future__ import annotations

import ast
import json
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from heatguard.api import app, bind_quota
from heatguard.boundary.cors_config import ConfigurationError
from heatguard.boundary.enforcement import REFUSAL_CODE_QUOTA
from heatguard.boundary.quota import (
    InProcessQuotaStore,
    bucket_key,
    coarse_origin,
    resolve_quota_settings,
    retry_after_seconds,
)
from heatguard.observability import metrics as obs_metrics

client = TestClient(app)
FIXTURE = Path(__file__).parent / "fixtures" / "quota_buckets.json"
API_KEYS = Path(__file__).parent / "fixtures" / "api_key_digests.json"
SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "heatguard" / "boundary" / "quota.py"
)


class FakeClock:
    """Deterministic monotonic clock — no wall-clock sleeps."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


@pytest.fixture
def set_quota():
    def _apply(env: dict[str, str], *, clock: FakeClock | None = None) -> None:
        bind_quota(app, env, clock=clock)

    yield _apply
    bind_quota(app, {})


def _matrix() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_characterization_flood_does_not_return_429() -> None:
    obs_metrics.reset_registry()
    statuses = [client.get("/sites").status_code for _ in range(40)]
    assert 429 not in statuses
    assert all(code not in (401, 403) for code in statuses)
    text = obs_metrics.render_prometheus().decode("utf-8")
    assert "heatguard_ratelimit_rejected_total" in text
    asserted = [
        line.split()[-1]
        for line in text.splitlines()
        if line.startswith("heatguard_ratelimit_rejected_total{")
    ]
    assert asserted == []


@pytest.mark.parametrize("case", _matrix()["cases"], ids=lambda c: c["id"])
def test_resolve_quota_settings_matrix(case: dict) -> None:
    settings = resolve_quota_settings(case["env"])
    for combo, expected in case["expect"].items():
        key_class, group = combo.split("/")
        assert list(settings.params_for(key_class, group)) == expected


@pytest.mark.parametrize("case", _matrix()["invalid"], ids=lambda c: c["id"])
def test_resolve_quota_settings_invalid_fails_boot(case: dict) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        resolve_quota_settings(case["env"])
    assert case["variable"] in str(excinfo.value)


def test_retry_after_never_zero_or_negative() -> None:
    assert retry_after_seconds(deficit=0.1, refill_per_sec=10.0) == 1
    assert retry_after_seconds(deficit=2.1, refill_per_sec=1.0) == 3
    assert retry_after_seconds(deficit=0.0, refill_per_sec=1.0) == 1


def test_token_bucket_burst_reject_refill_clamp_isolation() -> None:
    store = InProcessQuotaStore(max_buckets=8)
    key_a = "anon:none|reference"
    key_b = "anon:none|advisory"
    first = store.consume(key_a, 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)
    second = store.consume(key_a, 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)
    third = store.consume(key_a, 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)
    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds >= 1
    other = store.consume(key_b, 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)
    assert other.allowed is True
    recovered = store.consume(key_a, 1.0, 5.0, capacity=2.0, refill_per_sec=1.0)
    assert recovered.allowed is True
    clamped = store.consume(key_a, 1.0, 1_000.0, capacity=2.0, refill_per_sec=1.0)
    assert clamped.allowed is True
    second_at_cap = store.consume(key_a, 1.0, 1_000.0, capacity=2.0, refill_per_sec=1.0)
    assert second_at_cap.allowed is True
    over = store.consume(key_a, 1.0, 1_000.0, capacity=2.0, refill_per_sec=1.0)
    assert over.allowed is False


def test_lru_eviction_counts() -> None:
    obs_metrics.reset_registry()
    store = InProcessQuotaStore(max_buckets=2)
    store.consume("a", 1.0, 0.0, capacity=5.0, refill_per_sec=1.0)
    store.consume("b", 1.0, 0.0, capacity=5.0, refill_per_sec=1.0)
    store.consume("c", 1.0, 0.0, capacity=5.0, refill_per_sec=1.0)
    assert store.evictions == 1
    text = obs_metrics.render_prometheus().decode("utf-8")
    assert "heatguard_quota_bucket_evicted_total" in text
    assert "heatguard_quota_bucket_evicted_total 1.0" in text


def test_concurrent_consumes_do_not_overspend() -> None:
    store = InProcessQuotaStore(max_buckets=4)
    allowed = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal allowed
        result = store.consume("shared", 1.0, 0.0, capacity=20.0, refill_per_sec=1.0)
        if result.allowed:
            with lock:
                allowed += 1

    threads = [threading.Thread(target=worker) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert allowed == 20


def test_bucket_key_and_origin_helpers() -> None:
    assert coarse_origin(None) == "none"
    assert coarse_origin("https://Pitch.Example:5173/x") == "pitch.example"
    assert bucket_key(
        principal_id="demo-integrator", origin="none", group="reference"
    ) == "demo-integrator|reference"
    assert bucket_key(
        principal_id=None, origin="localhost", group="reference"
    ) == "anon:localhost|reference"
    assert "origin:localhost" in bucket_key(
        principal_id="u1", origin="localhost", group="session"
    )


def test_quota_source_has_no_io_calls() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    forbidden = {"open", "Path", "urlopen"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden:
            raise AssertionError(f"I/O name {node.id!r} in quota.py")
        if isinstance(node, ast.Attribute) and node.attr in {"open", "urlopen"}:
            raise AssertionError(f"I/O attribute {node.attr!r} in quota.py")
    src = SOURCE.read_text(encoding="utf-8")
    assert "httpx" not in src
    assert "pathlib" not in src
    assert "socket" not in src
    tree_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "redis" not in tree_names


def test_anonymous_over_limit_returns_429_then_recovers(
    set_quota: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HEATGUARD_METRICS_ENABLED", "1")
    obs_metrics.reset_registry()
    clock = FakeClock()
    set_quota(
        {
            "HEATGUARD_QUOTA_KEY_CAPACITY_ANONYMOUS": "2",
            "HEATGUARD_QUOTA_KEY_REFILL_ANONYMOUS": "1",
        },
        clock=clock,
    )
    assert client.get("/sites").status_code == 200
    assert client.get("/sites").status_code == 200
    denied = client.get("/sites")
    assert denied.status_code == 429
    assert denied.json()["code"] == REFUSAL_CODE_QUOTA
    assert denied.json()["message"] == "Request refused."
    assert "request_id" in denied.json()
    retry = int(denied.headers["retry-after"])
    assert retry >= 1
    assert "traceback" not in denied.text.lower()
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert (
        'heatguard_ratelimit_rejected_total{key_class="anonymous",route="/sites"} 1.0'
        in body
    )
    clock.advance(5.0)
    assert client.get("/sites").status_code == 200


def test_demo_key_is_exempt_from_quota(set_quota: Any) -> None:
    payload = json.loads(API_KEYS.read_text(encoding="utf-8"))
    set_quota({"HEATGUARD_QUOTA_CAPACITY": "1", "HEATGUARD_QUOTA_REFILL_PER_SEC": "0.01"})
    obs_metrics.reset_registry()
    headers = {"X-API-Key": payload["secrets"]["demo-integrator"]}
    statuses = [client.get("/sites", headers=headers).status_code for _ in range(8)]
    assert statuses == [200] * 8
    text = obs_metrics.render_prometheus().decode("utf-8")
    asserted = [
        line
        for line in text.splitlines()
        if line.startswith("heatguard_ratelimit_rejected_total{")
    ]
    assert asserted == []


def test_observe_only_counts_without_429(set_quota: Any) -> None:
    obs_metrics.reset_registry()
    set_quota(
        {
            "HEATGUARD_QUOTA_KEY_CAPACITY_ANONYMOUS": "1",
            "HEATGUARD_QUOTA_KEY_REFILL_ANONYMOUS": "0.01",
            "HEATGUARD_QUOTA_OBSERVE_ONLY": "true",
        }
    )
    statuses = [client.get("/sites").status_code for _ in range(4)]
    assert 429 not in statuses
    text = obs_metrics.render_prometheus().decode("utf-8")
    assert "heatguard_ratelimit_would_reject_total{" in text
    rejected = [
        line
        for line in text.splitlines()
        if line.startswith("heatguard_ratelimit_rejected_total{")
    ]
    assert rejected == []


def test_probes_exempt_from_quota_under_flood(set_quota: Any) -> None:
    set_quota({"HEATGUARD_QUOTA_CAPACITY": "1", "HEATGUARD_QUOTA_REFILL_PER_SEC": "0.01"})
    obs_metrics.reset_registry()
    live = [client.get("/health/live").status_code for _ in range(30)]
    ready = [client.get("/health/ready").status_code for _ in range(30)]
    assert live == [200] * 30
    assert all(code == 200 for code in ready)
    text = obs_metrics.render_prometheus().decode("utf-8")
    asserted = [
        line
        for line in text.splitlines()
        if line.startswith("heatguard_ratelimit_rejected_total{")
    ]
    assert asserted == []


def test_group_buckets_are_isolated(set_quota: Any) -> None:
    set_quota(
        {
            "HEATGUARD_QUOTA_CELL_CAPACITY_ANONYMOUS_REFERENCE": "1",
            "HEATGUARD_QUOTA_CELL_REFILL_ANONYMOUS_REFERENCE": "0.01",
        }
    )
    assert client.get("/sites").status_code == 200
    assert client.get("/sites").status_code == 429
    landing = client.get("/")
    assert landing.status_code not in (401, 403, 429)


def test_limiter_failure_admits_rather_than_withholding(
    set_quota: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_quota({"HEATGUARD_QUOTA_KEY_CAPACITY_ANONYMOUS": "1"})
    runtime = app.state.quota

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("quota store exploded")

    monkeypatch.setattr(runtime.store, "consume", boom)
    resp = client.get("/sites")
    assert resp.status_code == 200
