"""Canonical JSON serialization for golden-master byte comparison.

Policy (documented for regeneration sign-off):
- Objects: keys sorted lexicographically
- Separators: compact ``(',', ':')`` — no whitespace
- Unicode: ``ensure_ascii=False``
- Floats: non-finite → ``null``; otherwise shortest round-trip via
  ``format(x, '.17g')`` then re-parsed so the JSON number is stable
- Timestamps: timezone-aware datetimes → UTC ISO-8601 ending in ``Z``;
  naive datetimes are treated as UTC
- Enums / Path-like: ``str(value)``
- numpy scalars: coerced via ``.item()`` before formatting
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def _to_utc_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + (
        f".{dt.microsecond:06d}Z" if dt.microsecond else "Z"
    )


def _float_canonical(x: float) -> float | None:
    if not math.isfinite(x):
        return None
    # Shortest round-trip decimal that round-trips under IEEE-754 binary64.
    return float(format(x, ".17g"))


def normalize(obj: Any) -> Any:
    """Deep-normalize *obj* into JSON-friendly primitives for canonical dumps."""
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, Enum):
        return obj.value if isinstance(obj.value, (str, int, float, bool)) else str(obj.value)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return _to_utc_z(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if hasattr(obj, "item") and not isinstance(obj, (bytes, bytearray)):
        # numpy scalar
        try:
            return normalize(obj.item())
        except Exception:
            pass
    if isinstance(obj, float):
        return _float_canonical(obj)
    if isinstance(obj, dict):
        return {str(k): normalize(obj[k]) for k in sorted(obj, key=lambda x: str(x))}
    if isinstance(obj, (list, tuple)):
        return [normalize(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((normalize(v) for v in obj), key=lambda x: json.dumps(x, sort_keys=True))
    raise TypeError(f"Cannot canonicalize object of type {type(obj).__name__}")


def dumps(obj: Any) -> str:
    """Serialize *obj* to a canonical JSON string (no trailing newline)."""
    return json.dumps(
        normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def dumps_bytes(obj: Any) -> bytes:
    return dumps(obj).encode("utf-8")


def dump(obj: Any, path: Path | str) -> bytes:
    """Write canonical JSON to *path* (UTF-8, trailing newline) and return bytes written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = dumps(obj) + "\n"
    data = body.encode("utf-8")
    p.write_bytes(data)
    return data


def load(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
