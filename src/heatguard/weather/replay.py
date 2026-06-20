"""Replay a sequence of ``Weather`` samples through the scheduler."""
from __future__ import annotations

import json
from pathlib import Path

from ..scheduler import build_conditions, decide
from ..types import Advisory, MetabolicCategory, Posture, Site, Weather, Worker
from .openmeteo import load_cached_payload


def load_cached(path: str | Path, site: Site) -> list[Weather]:
    return load_cached_payload(Path(path), site)


def daytime(weathers: list[Weather], start_hour: int = 5, end_hour: int = 19) -> list[Weather]:
    """Restrict to the working window [start_hour, end_hour)."""
    return [w for w in weathers if start_hour <= w.timestamp.hour < end_hour]


def replay_worker(
    weathers: list[Weather],
    site: Site,
    worker: Worker,
    cat: MetabolicCategory,
    posture: Posture = Posture.STANDING,
) -> list[Advisory]:
    return [decide(build_conditions(w, site, cat, posture), worker) for w in weathers]


def replay_crew(
    weathers: list[Weather],
    site: Site,
    crew: list[Worker],
    cat: MetabolicCategory,
    posture: Posture = Posture.STANDING,
) -> dict[str, list[Advisory]]:
    return {wk.worker_id: replay_worker(weathers, site, wk, cat, posture) for wk in crew}
