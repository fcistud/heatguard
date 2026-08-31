"""In-process token-bucket quota (WO-007).

``QuotaStore.consume`` is the interface WO-008 will back with Memorystore.
This module performs no network I/O; bucket math uses a monotonic clock.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from heatguard.boundary.auth_mode import ROUTE_GROUPS
from heatguard.boundary.cors_config import ConfigurationError
from heatguard.observability.metrics import observe_quota_bucket_evicted

ENV_CAPACITY = "HEATGUARD_QUOTA_CAPACITY"
ENV_REFILL = "HEATGUARD_QUOTA_REFILL_PER_SEC"
ENV_KEY_CAPACITY_PREFIX = "HEATGUARD_QUOTA_KEY_CAPACITY_"
ENV_KEY_REFILL_PREFIX = "HEATGUARD_QUOTA_KEY_REFILL_"
ENV_GROUP_CAPACITY_PREFIX = "HEATGUARD_QUOTA_GROUP_CAPACITY_"
ENV_GROUP_REFILL_PREFIX = "HEATGUARD_QUOTA_GROUP_REFILL_"
ENV_CELL_CAPACITY_PREFIX = "HEATGUARD_QUOTA_CELL_CAPACITY_"
ENV_CELL_REFILL_PREFIX = "HEATGUARD_QUOTA_CELL_REFILL_"
ENV_OBSERVE_ONLY = "HEATGUARD_QUOTA_OBSERVE_ONLY"
ENV_MAX_BUCKETS = "HEATGUARD_QUOTA_MAX_BUCKETS"

# Generous defaults so a false 429 on an advisory is not the boot posture.
DEFAULT_CAPACITY = 10_000.0
DEFAULT_REFILL_PER_SEC = 1_000.0
DEFAULT_MAX_BUCKETS = 4_096
DEMO_KEY_CLASS = "demo"
ANONYMOUS_KEY_CLASS = "anonymous"
KNOWN_KEY_CLASSES: frozenset[str] = frozenset(
    {"demo", "partner", "internal", "dashboard", "anonymous"}
)
CONFIGURABLE_GROUPS: frozenset[str] = ROUTE_GROUPS | frozenset({"unknown"})


@dataclass(frozen=True, slots=True)
class ConsumeResult:
    """Outcome of one token-bucket consume."""

    allowed: bool
    retry_after_seconds: int


class QuotaStore(Protocol):
    """Shared consume contract — in-process now, Memorystore in WO-008."""

    def consume(
        self,
        bucket_key: str,
        cost: float,
        now: float,
        *,
        capacity: float,
        refill_per_sec: float,
    ) -> ConsumeResult: ...


@dataclass(frozen=True, slots=True)
class QuotaSettings:
    """Immutable bucket sizing resolved once at boot."""

    default_capacity: float
    default_refill_per_sec: float
    key_capacity: tuple[tuple[str, float], ...]
    key_refill: tuple[tuple[str, float], ...]
    group_capacity: tuple[tuple[str, float], ...]
    group_refill: tuple[tuple[str, float], ...]
    cell_capacity: tuple[tuple[str, str, float], ...]
    cell_refill: tuple[tuple[str, str, float], ...]
    observe_only: bool
    max_buckets: int

    def params_for(self, key_class: str, group: str) -> tuple[float, float]:
        """Most-specific override wins: cell, then key, then group, then default."""
        capacity = self.default_capacity
        refill = self.default_refill_per_sec
        for name, value in self.group_capacity:
            if name == group:
                capacity = value
                break
        for name, value in self.group_refill:
            if name == group:
                refill = value
                break
        for name, value in self.key_capacity:
            if name == key_class:
                capacity = value
                break
        for name, value in self.key_refill:
            if name == key_class:
                refill = value
                break
        for klass, grp, value in self.cell_capacity:
            if klass == key_class and grp == group:
                capacity = value
                break
        for klass, grp, value in self.cell_refill:
            if klass == key_class and grp == group:
                refill = value
                break
        return capacity, refill


class QuotaRef:
    """Mutable slot filled once at bind — request path only reads ``runtime``."""

    __slots__ = ("runtime",)

    def __init__(self) -> None:
        self.runtime: QuotaRuntime | None = None


@dataclass(slots=True)
class QuotaRuntime:
    """Settings plus the in-process store consulted on every request."""

    settings: QuotaSettings
    store: InProcessQuotaStore


def retry_after_seconds(*, deficit: float, refill_per_sec: float) -> int:
    """Whole seconds until ``deficit`` tokens accrue. Never zero or negative."""
    if deficit <= 0:
        return 1
    wait = math.ceil(deficit / refill_per_sec)
    return max(1, int(wait))


class InProcessQuotaStore:
    """Monotonic-clock token buckets with bounded LRU eviction."""

    def __init__(
        self,
        *,
        max_buckets: int = DEFAULT_MAX_BUCKETS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._max_buckets = max_buckets
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self.evictions = 0

    def consume(
        self,
        bucket_key: str,
        cost: float,
        now: float,
        *,
        capacity: float,
        refill_per_sec: float,
    ) -> ConsumeResult:
        with self._lock:
            tokens, last = self._buckets.get(bucket_key, (capacity, now))
            elapsed = max(0.0, now - last)
            tokens = min(capacity, tokens + elapsed * refill_per_sec)
            if tokens >= cost:
                tokens -= cost
                self._touch(bucket_key, tokens, now)
                return ConsumeResult(allowed=True, retry_after_seconds=0)
            self._touch(bucket_key, tokens, now)
            return ConsumeResult(
                allowed=False,
                retry_after_seconds=retry_after_seconds(
                    deficit=cost - tokens, refill_per_sec=refill_per_sec
                ),
            )

    def _touch(self, bucket_key: str, tokens: float, stamp: float) -> None:
        if bucket_key in self._buckets:
            del self._buckets[bucket_key]
        elif len(self._buckets) >= self._max_buckets:
            self._buckets.popitem(last=False)
            self.evictions += 1
            observe_quota_bucket_evicted()
        self._buckets[bucket_key] = (tokens, stamp)


DEFAULT_SETTINGS = QuotaSettings(
    default_capacity=DEFAULT_CAPACITY,
    default_refill_per_sec=DEFAULT_REFILL_PER_SEC,
    key_capacity=(),
    key_refill=(),
    group_capacity=(),
    group_refill=(),
    cell_capacity=(),
    cell_refill=(),
    observe_only=False,
    max_buckets=DEFAULT_MAX_BUCKETS,
)
DEFAULT_RUNTIME = QuotaRuntime(
    settings=DEFAULT_SETTINGS,
    store=InProcessQuotaStore(max_buckets=DEFAULT_MAX_BUCKETS),
)


def _parse_positive_float(raw: str, *, variable: str) -> float:
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise ConfigurationError(
            f"{variable}={raw!r} is not a number; use a positive float."
        ) from exc
    if value <= 0:
        raise ConfigurationError(
            f"{variable}={raw!r} must be > 0; a zero capacity would reject every request."
        )
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


def _parse_bool(raw: str, *, variable: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes"}:
        return True
    if value in {"0", "false", "no", ""}:
        return False
    raise ConfigurationError(
        f"{variable}={raw!r} is not a boolean; use true/false."
    )


def _split_cell_suffix(suffix: str, *, variable: str) -> tuple[str, str]:
    parts = suffix.strip().lower().split("_", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ConfigurationError(
            f"{variable} suffix {suffix!r} must be KEYCLASS_GROUP "
            f"(for example ANONYMOUS_ADVISORY)."
        )
    key_class, group = parts
    if key_class not in KNOWN_KEY_CLASSES:
        raise ConfigurationError(
            f"{variable} names key_class {key_class!r} which is not in "
            f"({', '.join(sorted(KNOWN_KEY_CLASSES))})."
        )
    if group not in CONFIGURABLE_GROUPS:
        raise ConfigurationError(
            f"{variable} names group {group!r} which is not in "
            f"({', '.join(sorted(CONFIGURABLE_GROUPS))})."
        )
    return key_class, group


def resolve_quota_settings(env: Mapping[str, str] | None = None) -> QuotaSettings:
    """Parse capacity/refill overrides. Invalid values fail boot."""
    source: Mapping[str, str] = env if env is not None else os.environ
    raw_capacity = source.get(ENV_CAPACITY)
    default_capacity = (
        DEFAULT_CAPACITY
        if raw_capacity is None or not raw_capacity.strip()
        else _parse_positive_float(raw_capacity, variable=ENV_CAPACITY)
    )
    raw_refill = source.get(ENV_REFILL)
    default_refill = (
        DEFAULT_REFILL_PER_SEC
        if raw_refill is None or not raw_refill.strip()
        else _parse_positive_float(raw_refill, variable=ENV_REFILL)
    )
    raw_max = source.get(ENV_MAX_BUCKETS)
    max_buckets = (
        DEFAULT_MAX_BUCKETS
        if raw_max is None or not raw_max.strip()
        else _parse_positive_int(raw_max, variable=ENV_MAX_BUCKETS)
    )
    raw_observe = source.get(ENV_OBSERVE_ONLY)
    observe_only = (
        False
        if raw_observe is None
        else _parse_bool(raw_observe, variable=ENV_OBSERVE_ONLY)
    )

    key_capacity: list[tuple[str, float]] = []
    key_refill: list[tuple[str, float]] = []
    group_capacity: list[tuple[str, float]] = []
    group_refill: list[tuple[str, float]] = []
    cell_capacity: list[tuple[str, str, float]] = []
    cell_refill: list[tuple[str, str, float]] = []

    for key, raw in source.items():
        if key.startswith(ENV_CELL_CAPACITY_PREFIX):
            klass, group = _split_cell_suffix(
                key[len(ENV_CELL_CAPACITY_PREFIX) :], variable=key
            )
            cell_capacity.append(
                (klass, group, _parse_positive_float(raw, variable=key))
            )
        elif key.startswith(ENV_CELL_REFILL_PREFIX):
            klass, group = _split_cell_suffix(
                key[len(ENV_CELL_REFILL_PREFIX) :], variable=key
            )
            cell_refill.append(
                (klass, group, _parse_positive_float(raw, variable=key))
            )
        elif key.startswith(ENV_KEY_CAPACITY_PREFIX):
            name = key[len(ENV_KEY_CAPACITY_PREFIX) :].strip().lower()
            if name not in KNOWN_KEY_CLASSES:
                raise ConfigurationError(
                    f"{key} names key_class {name!r} which is not in "
                    f"({', '.join(sorted(KNOWN_KEY_CLASSES))})."
                )
            key_capacity.append((name, _parse_positive_float(raw, variable=key)))
        elif key.startswith(ENV_KEY_REFILL_PREFIX):
            name = key[len(ENV_KEY_REFILL_PREFIX) :].strip().lower()
            if name not in KNOWN_KEY_CLASSES:
                raise ConfigurationError(
                    f"{key} names key_class {name!r} which is not in "
                    f"({', '.join(sorted(KNOWN_KEY_CLASSES))})."
                )
            key_refill.append((name, _parse_positive_float(raw, variable=key)))
        elif key.startswith(ENV_GROUP_CAPACITY_PREFIX):
            name = key[len(ENV_GROUP_CAPACITY_PREFIX) :].strip().lower()
            if name not in CONFIGURABLE_GROUPS:
                raise ConfigurationError(
                    f"{key} names group {name!r} which is not in "
                    f"({', '.join(sorted(CONFIGURABLE_GROUPS))})."
                )
            group_capacity.append((name, _parse_positive_float(raw, variable=key)))
        elif key.startswith(ENV_GROUP_REFILL_PREFIX):
            name = key[len(ENV_GROUP_REFILL_PREFIX) :].strip().lower()
            if name not in CONFIGURABLE_GROUPS:
                raise ConfigurationError(
                    f"{key} names group {name!r} which is not in "
                    f"({', '.join(sorted(CONFIGURABLE_GROUPS))})."
                )
            group_refill.append((name, _parse_positive_float(raw, variable=key)))

    return QuotaSettings(
        default_capacity=default_capacity,
        default_refill_per_sec=default_refill,
        key_capacity=tuple(sorted(key_capacity)),
        key_refill=tuple(sorted(key_refill)),
        group_capacity=tuple(sorted(group_capacity)),
        group_refill=tuple(sorted(group_refill)),
        cell_capacity=tuple(sorted(cell_capacity)),
        cell_refill=tuple(sorted(cell_refill)),
        observe_only=observe_only,
        max_buckets=max_buckets,
    )


def load_quota_runtime(
    env: Mapping[str, str] | None = None,
    *,
    clock: Callable[[], float] | None = None,
) -> QuotaRuntime:
    """Bind-time wrapper: freeze settings and allocate a fresh in-process store."""
    settings = resolve_quota_settings(env)
    return QuotaRuntime(
        settings=settings,
        store=InProcessQuotaStore(max_buckets=settings.max_buckets, clock=clock),
    )


def coarse_origin(origin_header: str | None) -> str:
    """Host of the Origin header, or ``none`` when absent/unparseable."""
    if not origin_header or not origin_header.strip():
        return "none"
    parsed = urlparse(origin_header.strip())
    host = (parsed.netloc or parsed.path).split("@")[-1].split(":")[0].lower()
    return host or "none"


def bucket_key(
    *,
    principal_id: str | None,
    origin: str,
    group: str,
) -> str:
    """Principal (or anonymous+origin) plus group. Session is origin-strict."""
    identity = principal_id or f"anon:{origin}"
    if group == "session":
        return f"{identity}|origin:{origin}|{group}"
    return f"{identity}|{group}"
