"""Shared Memorystore/Redis quota store (WO-008).

``consume`` is a single EVAL of the token-bucket script so two Cloud Run
instances cannot double-spend. Timeouts and malformed replies raise
``QuotaStoreUnavailable``; the runtime falls back to in-process buckets.
"""
from __future__ import annotations

import math
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from heatguard.boundary.cors_config import ConfigurationError
from heatguard.boundary.quota import ConsumeResult, retry_after_seconds

ENV_REDIS_URL = "HEATGUARD_QUOTA_REDIS_URL"
ENV_CONNECT_TIMEOUT = "HEATGUARD_QUOTA_REDIS_CONNECT_TIMEOUT"
ENV_COMMAND_TIMEOUT = "HEATGUARD_QUOTA_REDIS_COMMAND_TIMEOUT"
ENV_BREAKER_FAILURES = "HEATGUARD_QUOTA_REDIS_BREAKER_FAILURES"
ENV_BREAKER_COOLDOWN = "HEATGUARD_QUOTA_REDIS_BREAKER_COOLDOWN_SEC"

DEFAULT_CONNECT_TIMEOUT = 0.05
DEFAULT_COMMAND_TIMEOUT = 0.05
DEFAULT_BREAKER_FAILURES = 3
DEFAULT_BREAKER_COOLDOWN = 5.0

# Quota keyspace only. Login/lockout/last-login must never use this prefix.
KEY_PREFIX = "hg:quota:"

# Single round-trip: refill, debit or compute Retry-After, write, expire.
# Idempotency: EVAL is atomic on one key; a retried EVAL is a second consume.
TOKEN_BUCKET_LUA = """\
local key = KEYS[1]
local now = tonumber(ARGV[1])
local cost = tonumber(ARGV[2])
local capacity = tonumber(ARGV[3])
local refill = tonumber(ARGV[4])
if now == nil or cost == nil or capacity == nil or refill == nil then
  return redis.error_reply('malformed argv')
end
if refill <= 0 or capacity <= 0 then
  return redis.error_reply('invalid params')
end
local data = redis.call('HMGET', key, 'tokens', 'stamp')
local tokens = tonumber(data[1])
local stamp = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  stamp = now
end
local elapsed = now - stamp
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill)
local allowed = 0
local retry = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  local deficit = cost - tokens
  retry = math.ceil(deficit / refill)
  if retry < 1 then retry = 1 end
end
redis.call('HSET', key, 'tokens', tokens, 'stamp', now)
local ttl = math.ceil(capacity / refill) + 1
if ttl < 1 then ttl = 1 end
redis.call('EXPIRE', key, ttl)
return {allowed, retry}
"""


class QuotaStoreUnavailable(Exception):
    """Shared store timed out, disconnected, or returned a malformed reply."""


class RedisCommands(Protocol):
    """EVAL surface used by ``RedisQuotaStore`` — real client or test fake."""

    def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...


@dataclass(frozen=True, slots=True)
class RedisQuotaSettings:
    """Boot-time Redis timeouts and breaker. Empty url means in-process only."""

    url: str
    connect_timeout: float
    command_timeout: float
    breaker_failures: int
    breaker_cooldown: float


def _parse_positive_float(raw: str, *, variable: str) -> float:
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise ConfigurationError(
            f"{variable}={raw!r} is not a number; use a positive float."
        ) from exc
    if value <= 0:
        raise ConfigurationError(f"{variable}={raw!r} must be > 0.")
    return value


def _parse_positive_int(raw: str, *, variable: str) -> int:
    try:
        value = int(raw.strip(), 10)
    except ValueError as exc:
        raise ConfigurationError(
            f"{variable}={raw!r} is not an integer; use a positive int."
        ) from exc
    if value <= 0:
        raise ConfigurationError(f"{variable}={raw!r} must be >= 1.")
    return value


def resolve_redis_settings(env: Mapping[str, str] | None = None) -> RedisQuotaSettings:
    """Parse Redis URL and timeouts. Invalid values fail boot."""
    source: Mapping[str, str] = env if env is not None else os.environ
    url = (source.get(ENV_REDIS_URL) or "").strip()
    raw_connect = source.get(ENV_CONNECT_TIMEOUT)
    connect = (
        DEFAULT_CONNECT_TIMEOUT
        if raw_connect is None or not raw_connect.strip()
        else _parse_positive_float(raw_connect, variable=ENV_CONNECT_TIMEOUT)
    )
    raw_command = source.get(ENV_COMMAND_TIMEOUT)
    command = (
        DEFAULT_COMMAND_TIMEOUT
        if raw_command is None or not raw_command.strip()
        else _parse_positive_float(raw_command, variable=ENV_COMMAND_TIMEOUT)
    )
    raw_fail = source.get(ENV_BREAKER_FAILURES)
    failures = (
        DEFAULT_BREAKER_FAILURES
        if raw_fail is None or not raw_fail.strip()
        else _parse_positive_int(raw_fail, variable=ENV_BREAKER_FAILURES)
    )
    raw_cool = source.get(ENV_BREAKER_COOLDOWN)
    cooldown = (
        DEFAULT_BREAKER_COOLDOWN
        if raw_cool is None or not raw_cool.strip()
        else _parse_positive_float(raw_cool, variable=ENV_BREAKER_COOLDOWN)
    )
    return RedisQuotaSettings(
        url=url,
        connect_timeout=connect,
        command_timeout=command,
        breaker_failures=failures,
        breaker_cooldown=cooldown,
    )


def redis_quota_key(bucket_key: str) -> str:
    """Namespace a limiter bucket. Login-state keys must never be produced here."""
    return f"{KEY_PREFIX}{bucket_key}"


class RedisQuotaStore:
    """QuotaStore backed by Redis EVAL. No login-state keys are written."""

    def __init__(self, client: RedisCommands, *, key_prefix: str = KEY_PREFIX) -> None:
        if key_prefix != KEY_PREFIX:
            raise ConfigurationError(
                f"Redis quota key prefix must be {KEY_PREFIX!r}; got {key_prefix!r}."
            )
        self._client = client
        self._key_prefix = key_prefix

    @classmethod
    def from_url(cls, settings: RedisQuotaSettings) -> RedisQuotaStore:
        try:
            import redis as redis_mod
        except ImportError as exc:
            raise ConfigurationError(
                f"{ENV_REDIS_URL} is set but the redis package is not installed; "
                "add it through scripts/export_requirements.py."
            ) from exc
        client = redis_mod.Redis.from_url(
            settings.url,
            socket_connect_timeout=settings.connect_timeout,
            socket_timeout=settings.command_timeout,
            decode_responses=True,
        )
        return cls(client)

    def consume(
        self,
        bucket_key: str,
        cost: float,
        now: float,
        *,
        capacity: float,
        refill_per_sec: float,
    ) -> ConsumeResult:
        key = redis_quota_key(bucket_key)
        try:
            raw = self._client.eval(
                TOKEN_BUCKET_LUA,
                1,
                key,
                now,
                cost,
                capacity,
                refill_per_sec,
            )
        except QuotaStoreUnavailable:
            raise
        except Exception as exc:
            raise QuotaStoreUnavailable("shared quota store unavailable") from exc
        return _parse_eval_reply(raw, cost=cost, refill_per_sec=refill_per_sec)


def _parse_eval_reply(
    raw: object, *, cost: float, refill_per_sec: float
) -> ConsumeResult:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise QuotaStoreUnavailable("malformed quota EVAL reply")
    try:
        allowed_flag = int(raw[0])
        retry = int(raw[1])
    except (TypeError, ValueError) as exc:
        raise QuotaStoreUnavailable("malformed quota EVAL reply") from exc
    if allowed_flag == 1:
        return ConsumeResult(allowed=True, retry_after_seconds=0)
    if retry < 1:
        retry = retry_after_seconds(deficit=max(cost, 0.0), refill_per_sec=refill_per_sec)
    return ConsumeResult(allowed=False, retry_after_seconds=max(1, retry))


class InMemoryQuotaRedis:
    """Redis-compatible EVAL fake. Offline tests; no network I/O."""

    def __init__(self) -> None:
        self.commands: list[tuple[object, ...]] = []
        self.eval_calls = 0
        self.fail_with: BaseException | None = None
        self.reply_override: object | None = None
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        self.commands.append(("EVAL", script, numkeys, keys_and_args))
        self.eval_calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        if self.reply_override is not None:
            return self.reply_override
        if script != TOKEN_BUCKET_LUA:
            raise QuotaStoreUnavailable("unexpected EVAL script")
        if numkeys != 1 or len(keys_and_args) < 5:
            raise QuotaStoreUnavailable("unexpected EVAL arity")
        key = str(keys_and_args[0])
        now = float(keys_and_args[1])
        cost = float(keys_and_args[2])
        capacity = float(keys_and_args[3])
        refill = float(keys_and_args[4])
        with self._lock:
            tokens, stamp = self._buckets.get(key, (capacity, now))
            elapsed = max(0.0, now - stamp)
            tokens = min(capacity, tokens + elapsed * refill)
            if tokens >= cost:
                tokens -= cost
                self._buckets[key] = (tokens, now)
                return [1, 0]
            self._buckets[key] = (tokens, now)
            retry = max(1, int(math.ceil((cost - tokens) / refill)))
            return [0, retry]
