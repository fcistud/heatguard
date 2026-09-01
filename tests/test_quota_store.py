"""Shared Redis quota store, breaker, and fail-open fallback (WO-008)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from heatguard.api import app, bind_auth_modes, bind_quota
from heatguard.boundary.cors_config import ConfigurationError
from heatguard.boundary.enforcement import REFUSAL_CODE_QUOTA, REFUSAL_CODE_UNAUTHENTICATED
from heatguard.boundary.quota import StoreBreaker, load_quota_runtime
from heatguard.boundary.quota_redis import (
    ENV_COMMAND_TIMEOUT,
    ENV_CONNECT_TIMEOUT,
    InMemoryQuotaRedis,
    QuotaStoreUnavailable,
    RedisQuotaStore,
    redis_quota_key,
    resolve_redis_settings,
)
from heatguard.health import clear_readiness_cache
from heatguard.observability import degradation as deg
from heatguard.observability import metrics as obs_metrics

client = TestClient(app)
FIXTURE = Path(__file__).parent / "fixtures" / "quota_store.json"


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


@pytest.fixture
def set_quota():
    deg.clear_degradation_state()
    clear_readiness_cache()

    def _apply(
        env: dict[str, str],
        *,
        clock: FakeClock | None = None,
        shared: InMemoryQuotaRedis | RedisQuotaStore | None = None,
    ) -> None:
        store = shared
        if isinstance(shared, InMemoryQuotaRedis):
            store = RedisQuotaStore(shared)
        bind_quota(app, env, clock=clock, shared_store=store)

    yield _apply
    bind_quota(app, {})
    bind_auth_modes(app, {})
    deg.clear_degradation_state()
    clear_readiness_cache()


def _tight_env() -> dict[str, str]:
    return {
        "HEATGUARD_QUOTA_KEY_CAPACITY_ANONYMOUS": "2",
        "HEATGUARD_QUOTA_KEY_REFILL_ANONYMOUS": "1",
        "HEATGUARD_QUOTA_REDIS_BREAKER_FAILURES": "1",
        "HEATGUARD_QUOTA_REDIS_BREAKER_COOLDOWN_SEC": "10",
    }


def test_redis_settings_invalid_timeout_fails_boot() -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        resolve_redis_settings({ENV_CONNECT_TIMEOUT: "0"})
    assert ENV_CONNECT_TIMEOUT in str(excinfo.value)
    with pytest.raises(ConfigurationError) as excinfo:
        resolve_redis_settings({ENV_COMMAND_TIMEOUT: "-1"})
    assert ENV_COMMAND_TIMEOUT in str(excinfo.value)


def test_eval_command_construction_and_atomic_debit() -> None:
    fake = InMemoryQuotaRedis()
    store = RedisQuotaStore(fake)
    key = "anon:none|reference"
    first = store.consume(key, 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)
    second = store.consume(key, 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)
    third = store.consume(key, 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)
    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds >= 1
    recovered = store.consume(key, 1.0, 5.0, capacity=2.0, refill_per_sec=1.0)
    assert recovered.allowed is True
    assert fake.eval_calls == 4
    assert fake.commands[0][0] == "EVAL"
    assert fake.commands[0][3][0] == redis_quota_key(key)


def test_two_threads_cannot_double_spend() -> None:
    fake = InMemoryQuotaRedis()
    store = RedisQuotaStore(fake)
    results: list[bool] = []

    def _hit() -> None:
        results.append(
            store.consume("cell", 1.0, 0.0, capacity=1.0, refill_per_sec=1.0).allowed
        )

    threads = [threading.Thread(target=_hit) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 1
    assert results.count(False) == 7


def test_timeout_and_malformed_reply_are_unavailable() -> None:
    fake = InMemoryQuotaRedis()
    store = RedisQuotaStore(fake)
    fake.fail_with = TimeoutError("injected")
    with pytest.raises(QuotaStoreUnavailable):
        store.consume("k", 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)
    fake.fail_with = None
    fake.reply_override = "not-a-pair"
    with pytest.raises(QuotaStoreUnavailable):
        store.consume("k", 1.0, 0.0, capacity=2.0, refill_per_sec=1.0)


def test_breaker_opens_after_threshold_and_cools_down() -> None:
    clock = FakeClock()
    breaker = StoreBreaker(failure_threshold=2, cooldown_seconds=5.0)
    assert breaker.is_open(clock.t) is False
    breaker.record_failure(clock.t)
    assert breaker.is_open(clock.t) is False
    breaker.record_failure(clock.t)
    assert breaker.is_open(clock.t) is True
    clock.advance(5.0)
    assert breaker.is_open(clock.t) is False
    breaker.record_success()
    assert breaker.consecutive_failures == 0


def test_shared_store_healthy_429(
    set_quota: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HEATGUARD_METRICS_ENABLED", "1")
    obs_metrics.reset_registry()
    fake = InMemoryQuotaRedis()
    set_quota(_tight_env(), shared=fake)
    assert client.get("/sites").status_code == 200
    assert client.get("/sites").status_code == 200
    denied = client.get("/sites")
    assert denied.status_code == 429
    assert denied.json()["code"] == REFUSAL_CODE_QUOTA
    assert int(denied.headers["retry-after"]) >= 1
    assert fake.eval_calls == 3
    text = obs_metrics.render_prometheus().decode("utf-8")
    assert "heatguard_ratelimit_rejected_total{" in text


def test_outage_falls_back_latches_ready_degraded(
    set_quota: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HEATGUARD_METRICS_ENABLED", "1")
    obs_metrics.reset_registry()
    fake = InMemoryQuotaRedis()
    fake.fail_with = TimeoutError("down")
    set_quota(_tight_env(), shared=fake)
    admitted = client.get("/sites")
    assert admitted.status_code == 200
    clear_readiness_cache()
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "degraded"
    assert "ratelimit_store_unavailable" in body["degraded"]
    assert body["failed"] == []
    text = obs_metrics.render_prometheus().decode("utf-8")
    assert 'reason_code="ratelimit_store_unavailable"' in text
    second = client.get("/sites")
    assert second.status_code == 200
    asserted = [
        line
        for line in text.splitlines()
        if 'reason_code="ratelimit_store_unavailable"' in line and line.startswith("heatguard_degraded_conditions_total")
    ]
    # Counter increments on first fallback only; scrape after first request.
    assert any(line.endswith(" 1.0") for line in asserted)


def test_recovery_returns_to_shared_store(set_quota: Any) -> None:
    clock = FakeClock()
    fake = InMemoryQuotaRedis()
    fake.fail_with = TimeoutError("down")
    set_quota(_tight_env(), clock=clock, shared=fake)
    assert client.get("/sites").status_code == 200
    fake.fail_with = None
    clock.advance(11.0)
    assert client.get("/sites").status_code == 200
    assert client.get("/sites").status_code == 200
    denied = client.get("/sites")
    assert denied.status_code == 429
    assert fake.eval_calls >= 3


def test_outage_does_not_admit_unauthenticated_in_enforce(
    set_quota: Any,
) -> None:
    fake = InMemoryQuotaRedis()
    fake.fail_with = TimeoutError("down")
    set_quota(_tight_env(), shared=fake)
    bind_auth_modes(app, {"HEATGUARD_AUTH_MODE": "enforce"})
    denied = client.get("/demo/dubai")
    assert denied.status_code == 401
    assert denied.json()["code"] == REFUSAL_CODE_UNAUTHENTICATED
    clear_readiness_cache()
    ready = client.get("/health/ready").json()
    assert "ratelimit_store_unavailable" not in ready.get("degraded", [])


def test_fallback_does_not_double_count(set_quota: Any) -> None:
    fake = InMemoryQuotaRedis()
    fake.fail_with = TimeoutError("down")
    set_quota(
        {
            "HEATGUARD_QUOTA_KEY_CAPACITY_ANONYMOUS": "1",
            "HEATGUARD_QUOTA_KEY_REFILL_ANONYMOUS": "0.01",
            "HEATGUARD_QUOTA_REDIS_BREAKER_FAILURES": "1",
            "HEATGUARD_QUOTA_REDIS_BREAKER_COOLDOWN_SEC": "30",
        },
        shared=fake,
    )
    assert client.get("/sites").status_code == 200
    denied = client.get("/sites")
    assert denied.status_code == 429
    assert fake.eval_calls == 1


def test_429_counter_increments_only_after_send(
    set_quota: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HEATGUARD_METRICS_ENABLED", "1")
    obs_metrics.reset_registry()
    set_quota(
        {
            "HEATGUARD_QUOTA_KEY_CAPACITY_ANONYMOUS": "1",
            "HEATGUARD_QUOTA_KEY_REFILL_ANONYMOUS": "0.01",
        }
    )
    assert client.get("/sites").status_code == 200

    async def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("send failed")

    monkeypatch.setattr("heatguard.boundary.enforcement._send_refusal", boom)
    admitted = client.get("/sites")
    assert admitted.status_code == 200
    text = obs_metrics.render_prometheus().decode("utf-8")
    asserted = [
        line
        for line in text.splitlines()
        if line.startswith("heatguard_ratelimit_rejected_total{")
    ]
    assert asserted == []


def test_load_runtime_without_url_stays_in_process() -> None:
    runtime = load_quota_runtime({})
    assert runtime.fallback is None
    assert runtime.breaker is None


def test_fixture_matrix_is_committed() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert "outage" in payload and "recovery" in payload and "malformed" in payload
