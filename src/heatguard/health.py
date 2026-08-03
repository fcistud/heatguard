"""Liveness and dependency readiness probes (WO-012).

``/health/live`` must never touch the filesystem, caches, or the network.
``/health/ready`` evaluates hard vs optional dependencies and is memoised so
probe storms do not re-read the data directory on every scrape.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Callable, Literal

from ._paths import data_file

Kind = Literal["hard", "optional"]
ReadyStatus = Literal["ready", "degraded", "not_ready"]

_PROCESS_STARTED = time.monotonic()
_READY_LOCK = threading.Lock()
_READY_CACHE: tuple[float, "ReadinessResult"] | None = None

EXPECTED_SITE_COUNT = 7
HARD_JSON_FILES = (
    "economics.json",
    "epidemiology/gulf_heat.json",
    "nicaragua_baseline.json",
)


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    name: str
    kind: Kind
    checker: Callable[[], str | None]
    """Return None on success, or a short reason string on failure."""


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    name: str
    kind: Kind
    ok: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    status: ReadyStatus
    checks: list[CheckOutcome] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "failed": list(self.failed),
            "degraded": list(self.degraded),
            "checks": [
                {
                    "name": c.name,
                    "kind": c.kind,
                    "ok": c.ok,
                    "reason": c.reason,
                }
                for c in self.checks
            ],
        }


def service_version() -> str:
    try:
        return version("heatguard")
    except PackageNotFoundError:
        return "0.1.0"


def uptime_seconds() -> float:
    return round(time.monotonic() - _PROCESS_STARTED, 3)


def liveness() -> dict:
    """Process-only liveness payload — no I/O, no network."""
    return {
        "status": "ok",
        "version": service_version(),
        "uptime_seconds": uptime_seconds(),
    }


def _check_sites() -> str | None:
    from .sites import load_sites

    sites = load_sites()
    if len(sites) < EXPECTED_SITE_COUNT:
        return (
            f"expected at least {EXPECTED_SITE_COUNT} sites in locales.json, "
            f"found {len(sites)}"
        )
    return None


def _check_manifest() -> str | None:
    from .datasets import load_manifest

    manifest = load_manifest()
    if not isinstance(manifest, dict) or "version" not in manifest:
        return "datasets.json missing required 'version' field"
    return None


def _check_json_file(rel: str) -> Callable[[], str | None]:
    def _inner() -> str | None:
        path = data_file(rel)
        if not path.is_file():
            return f"missing {rel}"
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"unreadable or invalid JSON at {rel}: {exc}"
        return None

    return _inner


def _check_risk_model() -> str | None:
    from .risk_model import _load_model

    if _load_model() is None:
        return "risk_model_heuristic"
    return None


def _check_policy_rag() -> str | None:
    from . import policy_rag

    available, _reason = policy_rag.policy_index_status()
    if not available:
        return "policy_index_unavailable"
    return None


def _check_archive_caches() -> str | None:
    from .datasets import archive_specs

    specs = archive_specs()
    missing = [s.site_key for s in specs if s.required and not s.cached]
    if missing:
        return "missing required archive cache for: " + ", ".join(sorted(set(missing)))
    optional_missing = [s.site_key for s in specs if (not s.required) and not s.cached]
    if optional_missing:
        return "missing optional archive cache for: " + ", ".join(sorted(set(optional_missing)))
    return None


def default_checkers() -> list[DependencyCheck]:
    hard = [
        DependencyCheck("sites_registry", "hard", _check_sites),
        DependencyCheck("datasets_manifest", "hard", _check_manifest),
    ]
    for rel in HARD_JSON_FILES:
        hard.append(DependencyCheck(f"data:{rel}", "hard", _check_json_file(rel)))
    optional = [
        DependencyCheck("risk_model", "optional", _check_risk_model),
        DependencyCheck("policy_rag", "optional", _check_policy_rag),
        DependencyCheck("archive_caches", "optional", _check_archive_caches),
    ]
    return hard + optional


def run_readiness(checkers: list[DependencyCheck] | None = None) -> ReadinessResult:
    """Evaluate readiness. Never raises — every checker failure becomes a reason."""
    from .observability.degradation import REASON_CODES, active_reason_codes

    outcomes: list[CheckOutcome] = []
    failed: list[str] = []
    degraded: list[str] = []

    for dep in checkers if checkers is not None else default_checkers():
        try:
            reason = dep.checker()
        except Exception as exc:  # noqa: BLE001 — probe must never raise
            reason = f"{type(exc).__name__}: {exc}"
        ok = reason is None
        outcomes.append(CheckOutcome(dep.name, dep.kind, ok, reason))
        if ok:
            continue
        label = reason if reason in REASON_CODES else f"{dep.name}: {reason}"
        if dep.kind == "hard":
            failed.append(label)
        else:
            degraded.append(label)

    # Merge process-level degradation snapshot (WO-016) without escalating to 503.
    try:
        for code in active_reason_codes():
            if code not in degraded:
                degraded.append(code)
    except Exception:  # noqa: BLE001
        pass

    if failed:
        status: ReadyStatus = "not_ready"
    elif degraded:
        status = "degraded"
    else:
        status = "ready"
    return ReadinessResult(status=status, checks=outcomes, failed=failed, degraded=degraded)


def readiness_ttl_seconds() -> float:
    raw = os.environ.get("HEATGUARD_READINESS_TTL_SECONDS", "5")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 5.0


def get_readiness(*, force: bool = False) -> ReadinessResult:
    """Memoised readiness evaluation (default TTL 5s)."""
    global _READY_CACHE
    ttl = readiness_ttl_seconds()
    now = time.monotonic()
    with _READY_LOCK:
        if (
            not force
            and _READY_CACHE is not None
            and ttl > 0
            and (now - _READY_CACHE[0]) < ttl
        ):
            return _READY_CACHE[1]
        result = run_readiness()
        _READY_CACHE = (now, result)
        return result


def clear_readiness_cache() -> None:
    global _READY_CACHE
    with _READY_LOCK:
        _READY_CACHE = None
