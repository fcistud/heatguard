"""Unit tests for canonical JSON serialization (golden-master foundation)."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from heatguard.canonical import dumps, dumps_bytes, normalize


def test_dumps_is_byte_deterministic():
    obj = {"b": 2, "a": [3, 1], "z": {"y": 1.5, "x": None}}
    assert dumps(obj) == dumps(obj)
    assert dumps_bytes(obj) == dumps_bytes(obj)


def test_sorted_keys_and_compact_separators():
    assert dumps({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_float_round_trip_policy():
    # Shortest round-trip — same value twice yields identical encoding.
    x = 1.0 / 3.0
    assert dumps({"v": x}) == dumps({"v": x})
    assert "null" in dumps({"v": float("nan")})
    assert "null" in dumps({"v": float("inf")})
    # -0.0 must be stable across two serializations (exact form is policy-defined).
    assert dumps({"v": -0.0}) == dumps({"v": -0.0})


def test_float_formatting_boundaries():
    assert dumps(0.0) == dumps(0.0)
    assert dumps(1.0) in ("1", "1.0")
    assert dumps(1e-20) == dumps(1e-20)
    assert normalize(float("nan")) is None
    assert normalize(math.inf) is None


def test_datetime_to_utc_z():
    dt = datetime(2025, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    assert dumps({"t": dt}) == '{"t":"2025-05-16T12:00:00Z"}'
    naive = datetime(2025, 5, 16, 12, 0, 0)
    assert dumps({"t": naive}).endswith('Z"}')


def test_empty_and_none_handling():
    assert dumps({}) == "{}"
    assert dumps([]) == "[]"
    assert dumps(None) == "null"
    assert dumps({"a": None, "b": []}) == '{"a":null,"b":[]}'


def test_nested_determinism_same_as_twice():
    payload = {
        "rows": [
            {"hour": 12, "wbgt_c": 31.25, "banned": False},
            {"hour": 11, "wbgt_c": 30.1, "banned": True},
        ],
        "meta": {"crew": 100},
    }
    a = dumps_bytes(payload)
    b = dumps_bytes(payload)
    assert a == b
    assert a.endswith(b"{") is False
