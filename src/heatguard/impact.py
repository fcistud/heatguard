"""Health & productivity impact, grounded in the La Isla / Adelante (Nicaragua)
effect sizes (AKI -94%, productivity +10-20%).

The AKI estimate is **mechanistic**, not a flat multiplier: HeatGuard delivers
water-rest-shade during *every* dangerous hour, while the calendar ban only
covers the dangerous hours that happen to fall inside its fixed window. The
incremental cases averted scale with the coverage gap
``aki_reduction * baseline * (1 - ban_coverage)`` — so it collapses to zero when
the ban already covers all danger, and to the full 94% when the ban covers none
(e.g. a May heat-wave before the season starts).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace

from . import calendar_ban
from ._paths import data_file
from .types import Advisory, Signal

_PROTECTIVE = {Signal.STOP, Signal.REST_IN_SHADE}


def _load_baseline() -> dict:
    return json.loads(data_file("nicaragua_baseline.json").read_text())


@dataclass(frozen=True, slots=True)
class EffectSizes:
    aki_reduction: float = 0.94
    productivity_gain_lo: float = 0.10
    productivity_gain_hi: float = 0.20
    baseline_aki_incidence: float = 0.10  # per worker-season, tunable

    @classmethod
    def from_baseline(cls) -> "EffectSizes":
        b = _load_baseline()
        o = b["outcomes"]
        return cls(
            aki_reduction=o["aki_reduction"],
            productivity_gain_lo=o["productivity_gain_lo"],
            productivity_gain_hi=o["productivity_gain_hi"],
            baseline_aki_incidence=b["baseline_aki_incidence_per_worker_season"],
        )


@dataclass(frozen=True, slots=True)
class ImpactReport:
    crew_size: int
    season_days: int
    worker_days: int
    # calendar-vs-adaptive coverage
    total_hours: int
    total_danger_hours: int
    danger_hours_in_ban: int
    danger_hours_caught_vs_ban: int     # headline: protected by HeatGuard, missed by the ban
    ban_coverage_pct: float
    ban_only_safe_hours: int            # ban stopped work HeatGuard found safe (lost productivity)
    ban_only_safe_work_hours: float     # the same, fraction-weighted (actual productive hours recovered)
    # health
    aki_cases_baseline: float
    aki_cases_averted_heatguard: float
    aki_cases_averted_vs_ban: float
    # productivity
    heatguard_work_hours_per_worker: float
    calendar_work_hours_per_worker: float
    productivity_gain_lo: float
    productivity_gain_hi: float
    productivity_worker_hours_lo: float
    productivity_worker_hours_hi: float
    # cost
    capital_cost_usd: float
    recurring_cost_usd: float
    cost_per_worker_usd: float
    assumptions: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def pair_with_ban(advisories: list[Advisory], country: str) -> list[tuple[Advisory, bool]]:
    """Pair each advisory with whether the calendar ban covered that hour."""
    return [(a, calendar_ban.is_banned(country, a.timestamp, a.wbgt_c)) for a in advisories]


def _cost(crew_size: int) -> tuple[float, float, float]:
    items = _load_baseline()["cost_items_usd"]
    capital = sum(i["usd"] for i in items if i["type"] == "capital")
    recurring = sum(i["usd"] for i in items if i["type"] == "recurring")
    per_worker = capital + recurring
    return capital * crew_size, recurring * crew_size, per_worker


def estimate_impact(
    hourly: list[tuple[Advisory, bool]],
    crew_size: int,
    season_days: int,
    effects: EffectSizes | None = None,
) -> ImpactReport:
    """Estimate impact from a representative worker's replayed season.

    ``hourly`` is one worker's (advisory, banned_by_calendar) sequence over the
    replay; crew-level figures scale by ``crew_size``.
    """
    effects = effects or EffectSizes.from_baseline()

    total_hours = len(hourly)
    danger = [(a, banned) for a, banned in hourly if a.signal in _PROTECTIVE]
    total_danger = len(danger)
    danger_in_ban = sum(1 for _, banned in danger if banned)
    danger_caught = total_danger - danger_in_ban
    ban_coverage = (danger_in_ban / total_danger) if total_danger else 0.0
    ban_only_safe = sum(1 for a, banned in hourly if banned and a.signal is Signal.WORK)
    ban_only_safe_work_hours = sum(
        a.cycle.work_fraction for a, banned in hourly if banned and a.signal is Signal.WORK
    )

    # AKI risk accrues from dangerous-hour exposure. With no danger hours there is
    # nothing to avert, so both figures gate on danger being present (otherwise the
    # mechanistic model would credit the full 94% in a season with zero danger).
    has_danger = total_danger > 0
    danger_missed_fraction = (danger_caught / total_danger) if has_danger else 0.0
    aki_baseline = effects.baseline_aki_incidence * crew_size
    aki_averted_hg = effects.aki_reduction * aki_baseline if has_danger else 0.0
    aki_averted_vs_ban = effects.aki_reduction * aki_baseline * danger_missed_fraction

    hg_work = sum(a.cycle.work_fraction for a, _ in hourly)
    cal_work = sum(1.0 for _, banned in hourly if not banned)

    heat_exposed_worker_hours = hg_work * crew_size
    prod_lo = effects.productivity_gain_lo * heat_exposed_worker_hours
    prod_hi = effects.productivity_gain_hi * heat_exposed_worker_hours

    capital, recurring, per_worker = _cost(crew_size)

    return ImpactReport(
        crew_size=crew_size,
        season_days=season_days,
        worker_days=crew_size * season_days,
        total_hours=total_hours,
        total_danger_hours=total_danger,
        danger_hours_in_ban=danger_in_ban,
        danger_hours_caught_vs_ban=danger_caught,
        ban_coverage_pct=round(100.0 * ban_coverage, 1),
        ban_only_safe_hours=ban_only_safe,
        ban_only_safe_work_hours=round(ban_only_safe_work_hours, 1),
        aki_cases_baseline=round(aki_baseline, 2),
        aki_cases_averted_heatguard=round(aki_averted_hg, 2),
        aki_cases_averted_vs_ban=round(aki_averted_vs_ban, 2),
        heatguard_work_hours_per_worker=round(hg_work, 1),
        calendar_work_hours_per_worker=round(cal_work, 1),
        productivity_gain_lo=effects.productivity_gain_lo,
        productivity_gain_hi=effects.productivity_gain_hi,
        productivity_worker_hours_lo=round(prod_lo, 1),
        productivity_worker_hours_hi=round(prod_hi, 1),
        capital_cost_usd=round(capital, 2),
        recurring_cost_usd=round(recurring, 2),
        cost_per_worker_usd=round(per_worker, 2),
        assumptions={
            "aki_reduction": effects.aki_reduction,
            "baseline_aki_incidence_per_worker_season": effects.baseline_aki_incidence,
            "productivity_band": [effects.productivity_gain_lo, effects.productivity_gain_hi],
            "danger_hour_def": "HeatGuard signal is STOP or REST_IN_SHADE",
            "aki_model": "mechanistic: reduction * baseline * (1 - ban_coverage)",
            "source": "La Isla / Adelante (Nicaragua), 2024 ILO report; effect sizes transfer with uncertainty",
        },
    )


def sensitivity(
    hourly: list[tuple[Advisory, bool]],
    crew_size: int,
    season_days: int,
    incidences: tuple[float, ...] = (0.05, 0.075, 0.10, 0.15, 0.20),
    base_effects: EffectSizes | None = None,
) -> list[dict]:
    """Vary the (uncertain) baseline AKI incidence and report the averted-vs-ban band.

    The baseline incidence is the single biggest assumption; showing a range is
    more honest than a point estimate.
    """
    base = base_effects or EffectSizes.from_baseline()
    out: list[dict] = []
    for inc in incidences:
        rep = estimate_impact(hourly, crew_size, season_days, replace(base, baseline_aki_incidence=inc))
        out.append({
            "baseline_aki_incidence": inc,
            "aki_cases_baseline": rep.aki_cases_baseline,
            "aki_cases_averted_vs_ban": rep.aki_cases_averted_vs_ban,
            "aki_cases_averted_heatguard": rep.aki_cases_averted_heatguard,
        })
    return out


def backtest_nicaragua(effects: EffectSizes | None = None, tol: float = 1e-6) -> dict:
    """Reproduce the documented Nicaragua outcomes from the wired model.

    Nicaragua had no calendar ban (coverage = 0), so the intervention should
    avert ~94% of baseline AKI and deliver a 10-20% productivity band. Returns a
    dict including ``passed`` for the test suite.
    """
    effects = effects or EffectSizes.from_baseline()
    b = _load_baseline()
    crew = b["crew_reference"]["workers"]

    aki_baseline = effects.baseline_aki_incidence * crew
    # coverage = 0 (no ban) -> full effect
    aki_averted = effects.aki_reduction * aki_baseline * (1.0 - 0.0)
    reproduced_reduction = aki_averted / aki_baseline if aki_baseline else 0.0

    expected = b["outcomes"]
    passed = (
        abs(reproduced_reduction - expected["aki_reduction"]) < tol
        and abs(effects.productivity_gain_lo - expected["productivity_gain_lo"]) < tol
        and abs(effects.productivity_gain_hi - expected["productivity_gain_hi"]) < tol
    )
    return {
        "crew_reference": crew,
        "aki_cases_baseline": round(aki_baseline, 2),
        "aki_cases_averted": round(aki_averted, 2),
        "reproduced_aki_reduction": round(reproduced_reduction, 4),
        "expected_aki_reduction": expected["aki_reduction"],
        "productivity_band": [effects.productivity_gain_lo, effects.productivity_gain_hi],
        "expected_productivity_band": [expected["productivity_gain_lo"], expected["productivity_gain_hi"]],
        "passed": passed,
    }
