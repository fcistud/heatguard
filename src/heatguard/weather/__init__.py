"""Weather ingestion: Open-Meteo client (live + cached archive) and replay."""
from __future__ import annotations

from .openmeteo import (
    HOURLY_VARS,
    cache_name_for,
    fetch_archive,
    fetch_forecast,
    forecast_cache_name_for,
)
from .replay import daytime, load_cached, replay_crew, replay_worker

__all__ = [
    "HOURLY_VARS",
    "cache_name_for",
    "fetch_archive",
    "fetch_forecast",
    "forecast_cache_name_for",
    "daytime",
    "load_cached",
    "replay_crew",
    "replay_worker",
]
