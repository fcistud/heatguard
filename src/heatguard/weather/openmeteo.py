"""Open-Meteo client — free, no API key.

Archive (reanalysis) for replaying real days/seasons, and the forecast endpoint
for a near-live signal. Responses are cached to ``data/cache/`` so the stage demo
never touches the network. Wind is requested in m/s and pressure comes in hPa,
matching the engine's ``Weather`` units.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .._paths import CACHE_DIR, cache_file
from ..types import Site, Weather

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "shortwave_radiation",
    "direct_radiation",
    "dew_point_2m",
    "surface_pressure",
]


def _slug(site: Site) -> str:
    return site.name.lower().replace(" ", "_")


def cache_name_for(site: Site, start: date, end: date) -> str:
    return f"{_slug(site)}_{start}_{end}.json"


def _base_params(site: Site) -> dict:
    return {
        "latitude": site.lat,
        "longitude": site.lon,
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": site.tz,
    }


def _parse(payload: dict, site: Site) -> list[Weather]:
    h = payload["hourly"]
    offset = int(payload.get("utc_offset_seconds", 0))
    tz = timezone(timedelta(seconds=offset))
    times = h["time"]

    def col(key: str) -> list:
        return h.get(key) or [None] * len(times)

    cols = {k: col(k) for k in HOURLY_VARS}
    out: list[Weather] = []
    for i, t in enumerate(times):
        ts = datetime.fromisoformat(t).replace(tzinfo=tz)

        def g(key: str, default: float = 0.0) -> float:
            v = cols[key][i]
            return float(v) if v is not None else default

        out.append(
            Weather(
                timestamp=ts,
                tdb_c=g("temperature_2m"),
                rh_pct=g("relative_humidity_2m", 30.0),
                wind_ms=g("wind_speed_10m"),
                shortwave_wm2=g("shortwave_radiation"),
                direct_wm2=g("direct_radiation"),
                dew_point_c=g("dew_point_2m"),
                pressure_hpa=g("surface_pressure", 1013.0),
            )
        )
    return out


def fetch_archive(
    site: Site,
    start: date,
    end: date,
    use_cache: bool = True,
    refresh: bool = False,
) -> list[Weather]:
    """Hourly reanalysis for [start, end]. Cached under ``data/cache/``."""
    path = cache_file(cache_name_for(site, start, end))
    if use_cache and not refresh and path.exists():
        payload = json.loads(path.read_text())
    else:
        import httpx

        params = _base_params(site) | {"start_date": str(start), "end_date": str(end)}
        resp = httpx.get(ARCHIVE_URL, params=params, timeout=90)
        resp.raise_for_status()
        payload = resp.json()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    return _parse(payload, site)


def fetch_forecast(site: Site, forecast_days: int = 2, past_days: int = 1) -> list[Weather]:
    """Near-live hourly forecast (for the live demo signal)."""
    import httpx

    params = _base_params(site) | {"forecast_days": forecast_days, "past_days": past_days}
    resp = httpx.get(FORECAST_URL, params=params, timeout=60)
    resp.raise_for_status()
    return _parse(resp.json(), site)


def load_cached_payload(path: Path, site: Site) -> list[Weather]:
    return _parse(json.loads(Path(path).read_text()), site)
