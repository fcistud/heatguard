"""Shared application service — assembles demo/timeline/decision/impact payloads.

Reused by the CLI, the FastAPI backend, the Streamlit app, and the notebook so the
narrative is computed in exactly one place.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

from . import calendar_ban, economics, impact
from .compliance import ComplianceLog
from .scheduler import live_signal, schedule
from .sites import get_site, load_sites
from .types import MetabolicCategory, Signal, Weather, Worker
from .weather import daytime, fetch_archive, replay_worker

_PROTECTIVE = (Signal.STOP, Signal.REST_IN_SHADE)
WORK_START, WORK_END = 5, 19

# The two committed demo datasets / narratives.
DEMOS: dict[str, dict] = {
    "dubai": {
        "site": "dubai",
        "focus_day": date(2025, 5, 16),
        "season_start": date(2025, 5, 1),
        "season_end": date(2025, 9, 15),
        "intensity": MetabolicCategory.HEAVY,
        "headline": "Dubai, May 2025 — extreme heat arrived before the calendar ban started.",
    },
    "riyadh": {
        "site": "riyadh",
        "focus_day": date(2024, 7, 15),
        "season_start": date(2024, 6, 1),
        "season_end": date(2024, 9, 15),
        "intensity": MetabolicCategory.HEAVY,
        "headline": "Riyadh, summer — the ban 'protects' 12:00-15:00 but misses the humid morning.",
    },
}


def _veteran() -> Worker:
    return Worker("veteran", days_on_job=120, acclimatized=True)


def _newcomer() -> Worker:
    return Worker("newcomer-day0", days_on_job=0, acclimatized=False)


def list_sites() -> list[dict]:
    out = []
    for key, s in load_sites().items():
        out.append({
            "key": key, "name": s.name, "lat": s.lat, "lon": s.lon,
            "country": s.country, "ban": calendar_ban.describe(s.country),
            "is_demo": key in DEMOS,
        })
    return out


def load_season(site_key: str):
    cfg = DEMOS[site_key]
    site = get_site(cfg["site"])
    weathers = fetch_archive(site, cfg["season_start"], cfg["season_end"])  # cached
    return cfg, site, weathers


def available_days(site_key: str) -> list[str]:
    _, _, season = load_season(site_key)
    return sorted({str(w.timestamp.date()) for w in season})


def _row(w: Weather, site, cat, veteran, newcomer) -> dict:
    av = schedule(w, site, veteran, cat)
    an = schedule(w, site, newcomer, cat)
    banned = calendar_ban.is_banned(site.country, w.timestamp, av.wbgt_c)
    gap = (av.signal in _PROTECTIVE or an.signal in _PROTECTIVE) and not banned
    return {
        "hour": w.timestamp.hour,
        "time": w.timestamp.strftime("%H:%M"),
        "tdb_c": round(w.tdb_c, 1),
        "rh_pct": round(w.rh_pct, 0),
        "wbgt_c": round(av.wbgt_c, 1),
        "wbgt_source": av.wbgt_source,
        "veteran": av.to_dict(),
        "newcomer": an.to_dict(),
        "banned": banned,
        "gap": gap,
    }


def timeline_for_day(site_key: str, day: date) -> dict:
    cfg, site, season = load_season(site_key)
    cat = cfg["intensity"]
    veteran, newcomer = _veteran(), _newcomer()
    rows = [
        _row(w, site, cat, veteran, newcomer)
        for w in season
        if w.timestamp.date() == day and WORK_START <= w.timestamp.hour <= WORK_END
    ]
    return {
        "site": site.name,
        "country": site.country,
        "date": str(day),
        "rows": rows,
        "gap_hours": sum(r["gap"] for r in rows),
    }


def _season_hourly(site_key: str):
    """One representative-worker season replay -> (hourly[(advisory, banned)], season_days)."""
    cfg, site, season = load_season(site_key)
    # WORK_END is inclusive for the timeline/compliance views; daytime() is
    # half-open, so +1 keeps the impact window identical (hours 5..19).
    work = daytime(season, WORK_START, WORK_END + 1)
    advs = replay_worker(work, site, _veteran(), cfg["intensity"])
    hourly = impact.pair_with_ban(advs, site.country)
    season_days = len({w.timestamp.date() for w in work})
    return hourly, season_days


def season_impact_report(site_key: str, crew: int = 100):
    hourly, days = _season_hourly(site_key)
    return impact.estimate_impact(hourly, crew_size=crew, season_days=days)


def season_impact(site_key: str, crew: int = 100) -> dict:
    return season_impact_report(site_key, crew).to_dict()


def business_case(site_key: str, crew: int = 100) -> dict:
    return economics.business_case(season_impact_report(site_key, crew)).to_dict()


def impact_sensitivity(site_key: str, crew: int = 100) -> list[dict]:
    hourly, days = _season_hourly(site_key)
    return impact.sensitivity(hourly, crew, days)


def compliance_for_day(site_key: str, day: date) -> ComplianceLog:
    cfg, site, season = load_season(site_key)
    cat = cfg["intensity"]
    log = ComplianceLog(f"{site.name} demo site")
    for w in season:
        if w.timestamp.date() == day and WORK_START <= w.timestamp.hour <= WORK_END:
            log.append(schedule(w, site, _veteran(), cat), water_available=True)
    return log


def build_demo(site_key: str, crew: int = 100) -> dict:
    cfg, site, season = load_season(site_key)
    focus = cfg["focus_day"]
    tl = timeline_for_day(site_key, focus)
    log = compliance_for_day(site_key, focus)
    peak = max(season, key=lambda w: w.tdb_c)

    # one season replay feeds impact + economics + sensitivity
    hourly, days = _season_hourly(site_key)
    report = impact.estimate_impact(hourly, crew_size=crew, season_days=days)
    return {
        "site": {"key": site_key, "name": site.name, "country": site.country, "lat": site.lat, "lon": site.lon},
        "headline": cfg["headline"],
        "intensity": cfg["intensity"].value,
        "ban": {"country": site.country, "description": calendar_ban.describe(site.country)},
        "focus_day": str(focus),
        "available_days": sorted({str(w.timestamp.date()) for w in season}),
        "peak": {"tdb_c": round(peak.tdb_c, 1), "when": peak.timestamp.strftime("%Y-%m-%d %H:%M")},
        "timeline": tl,
        "compliance": {
            "summary": log.summary(),
            "records": [asdict(r) for r in log.records],
            "csv": log.export_csv(),
        },
        "impact": report.to_dict(),
        "economics": economics.business_case(report).to_dict(),
        "sensitivity": impact.sensitivity(hourly, crew, days),
    }


def decide_one(
    site_key: str,
    tdb: float,
    rh: float,
    wind: float = 2.0,
    solar: float = 800.0,
    hour: int = 12,
    intensity: str = "heavy",
    days_on_job: int = 120,
    acclimatized: bool = True,
    experienced: bool = False,
    measured_wbgt: float | None = None,
) -> dict:
    site = get_site(site_key)
    ts = datetime.now().astimezone().replace(hour=hour, minute=0, second=0, microsecond=0)
    w = Weather(ts, tdb, rh, wind, solar, solar * 0.85, tdb - 15, 1013.0)
    worker = Worker("api", days_on_job=days_on_job, acclimatized=acclimatized, experienced_elsewhere=experienced)
    av = schedule(w, site, worker, MetabolicCategory(intensity), measured_wbgt_c=measured_wbgt)
    return {
        "advisory": av.to_dict(),
        "banned": calendar_ban.is_banned(site.country, ts, av.wbgt_c),
        "ban_description": calendar_ban.describe(site.country),
        "live": [live_signal(av, m).value for m in range(60)],
    }


def backtest() -> dict:
    return impact.backtest_nicaragua()
