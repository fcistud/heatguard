"""Shared application service — assembles demo/timeline/decision/impact payloads.

Reused by the CLI, the FastAPI backend, the Streamlit app, and the notebook so the
narrative is computed in exactly one place.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

from . import calendar_ban, economics, impact, scale
from .compliance import ComplianceLog
from .scheduler import live_signal, schedule
from .sites import get_site, load_sites
from .types import MetabolicCategory, Signal, Weather, Worker
from .wbgt import estimate_wbgt
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


def _newcomer(days_on_job: int = 0) -> Worker:
    return Worker(f"newcomer-day{days_on_job}", days_on_job=days_on_job, acclimatized=False)


def _intensity(intensity: str | None, cfg: dict) -> MetabolicCategory:
    """Resolve a work-intensity string to a category, defaulting to the demo's."""
    if not intensity:
        return cfg["intensity"]
    return MetabolicCategory(intensity)


def _worker_for(kind: str, newcomer_days: int = 0) -> Worker:
    return _newcomer(newcomer_days) if kind == "newcomer" else _veteran()


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


def timeline_for_day(
    site_key: str, day: date, intensity: str | None = None, newcomer_days: int = 0
) -> dict:
    cfg, site, season = load_season(site_key)
    cat = _intensity(intensity, cfg)
    veteran, newcomer = _veteran(), _newcomer(newcomer_days)
    rows = [
        _row(w, site, cat, veteran, newcomer)
        for w in season
        if w.timestamp.date() == day and WORK_START <= w.timestamp.hour <= WORK_END
    ]
    return {
        "site": site.name,
        "country": site.country,
        "date": str(day),
        "intensity": cat.value,
        "newcomer_days": newcomer_days,
        "rows": rows,
        "gap_hours": sum(r["gap"] for r in rows),
    }


def hour_advisory(
    site_key: str,
    day: date,
    hour: int,
    worker_kind: str = "veteran",
    newcomer_days: int = 0,
    intensity: str | None = None,
    measured_wbgt: float | None = None,
) -> dict:
    """Recompute one hour's advisory for a specific worker/intensity, optionally
    overriding the estimated WBGT with an on-site meter reading. Returns the
    advisory plus the model ESTIMATE for a sensor-vs-estimate comparison."""
    cfg, site, season = load_season(site_key)
    cat = _intensity(intensity, cfg)
    w = next(
        (x for x in season if x.timestamp.date() == day and x.timestamp.hour == hour),
        None,
    )
    if w is None:
        raise KeyError(f"No weather for {site_key} {day} {hour:02d}:00")
    worker = _worker_for(worker_kind, newcomer_days)
    est = estimate_wbgt(w, site)  # always compute the estimate, for comparison
    adv = schedule(w, site, worker, cat, measured_wbgt_c=measured_wbgt)
    return {
        "advisory": adv.to_dict(),
        "estimated_wbgt_c": round(est.wbgt_c, 1),
        "estimated_source": est.source,
        "measured": measured_wbgt is not None,
        "banned": calendar_ban.is_banned(site.country, w.timestamp, adv.wbgt_c),
        "live": [live_signal(adv, m).value for m in range(60)],
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


def scale_projection(site_key: str, workforce: int = 5000, crew: int = 100) -> dict:
    """Project the per-crew season impact up to a workforce (the scale / lives-saved story)."""
    report = season_impact_report(site_key, crew)
    return scale.project(report, workforce).to_dict()


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
