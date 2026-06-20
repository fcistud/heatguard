"""HeatGuard — adaptive WBGT-driven work-rest-hydration scheduler for outdoor
labour crews in the Gulf.

Replaces the blunt calendar-based midday work ban with a condition-responsive
schedule, a tamper-evident compliance log, and a health/productivity impact
estimator grounded in the La Isla / Adelante (Nicaragua) effect sizes.
"""
from __future__ import annotations

from .scheduler import build_conditions, decide, live_signal, schedule
from .types import (
    Advisory,
    Conditions,
    HydrationTarget,
    MetabolicCategory,
    Posture,
    Signal,
    Site,
    Weather,
    Worker,
    WorkRestCycle,
)
from .wbgt import estimate_wbgt, from_measured

__version__ = "0.1.0"

__all__ = [
    "Advisory",
    "Conditions",
    "HydrationTarget",
    "MetabolicCategory",
    "Posture",
    "Signal",
    "Site",
    "Weather",
    "Worker",
    "WorkRestCycle",
    "build_conditions",
    "decide",
    "estimate_wbgt",
    "from_measured",
    "live_signal",
    "schedule",
    "__version__",
]
