"""Business case / ROI — the pitch's killer argument made explicit.

The intervention is *productivity-positive* and a *compliance shield*. This module
monetises the impact (from ``impact.ImpactReport``) into a defensible ROI, with
all assumptions loaded from ``data/economics.json`` and fully tunable.

To stay credible the **headline** ROI uses only the conservative benefit subset —
productivity gain, AKI cases averted, fines avoided, and recovered safe work the
blunt ban would have stopped. The (sensitive) death-averted and turnover terms are
computed and reported *separately*, never folded into the headline.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ._paths import data_file
from .impact import ImpactReport


def _load() -> dict:
    return json.loads(data_file("economics.json").read_text())


@dataclass(frozen=True, slots=True)
class EconomicAssumptions:
    daily_value_per_worker_usd: float = 30.0
    work_hours_per_day: float = 8.0
    aki_case_cost_usd: float = 1200.0
    heat_death_cost_usd: float = 150000.0
    heat_death_per_aki_case: float = 0.005
    fine_per_worker_usd: float = 1361.0
    fine_probability_per_season: float = 0.03
    turnover_cost_per_worker_usd: float = 150.0
    turnover_reduction: float = 0.10

    @classmethod
    def from_file(cls) -> "EconomicAssumptions":
        d = _load()
        return cls(
            daily_value_per_worker_usd=d["daily_value_per_worker_usd"],
            work_hours_per_day=d["work_hours_per_day"],
            aki_case_cost_usd=d["aki_case_cost_usd"],
            heat_death_cost_usd=d["heat_death_cost_usd"],
            heat_death_per_aki_case=d["heat_death_per_aki_case"],
            fine_per_worker_usd=d["fine_per_worker_usd"],
            fine_probability_per_season=d["fine_probability_per_season"],
            turnover_cost_per_worker_usd=d["turnover_cost_per_worker_usd"],
            turnover_reduction=d["turnover_reduction"],
        )

    @property
    def hourly_value_usd(self) -> float:
        return self.daily_value_per_worker_usd / self.work_hours_per_day


@dataclass(frozen=True, slots=True)
class BusinessCase:
    crew_size: int
    season_days: int
    # benefit items (USD, crew + season)
    productivity_value_lo: float
    productivity_value_hi: float
    recovered_safe_work_value: float
    aki_value: float
    fines_avoided_value: float
    death_averted_value: float
    turnover_value: float
    # roll-ups
    headline_benefit_lo: float          # conservative subset
    headline_benefit_hi: float
    total_benefit_lo: float             # incl. death + turnover
    total_benefit_hi: float
    program_cost_usd: float
    net_benefit_lo: float               # headline benefit - cost
    net_benefit_hi: float
    roi_multiple_lo: float              # headline benefit / cost
    roi_multiple_hi: float
    payback_days: float                 # days for headline benefit to cover cost
    assumptions: dict

    def to_dict(self) -> dict:
        return asdict(self)


def business_case(report: ImpactReport, assumptions: EconomicAssumptions | None = None) -> BusinessCase:
    a = assumptions or EconomicAssumptions.from_file()
    crew = report.crew_size

    # Productivity gain (already crew-level worker-hours in the report).
    prod_lo = report.productivity_worker_hours_lo * a.hourly_value_usd
    prod_hi = report.productivity_worker_hours_hi * a.hourly_value_usd

    # Safe work the blunt ban would have stopped, recovered. Fraction-weighted
    # (the actual productive hours, accounting for breaks) and scaled to the crew.
    recovered = report.ban_only_safe_work_hours * crew * a.hourly_value_usd

    # Health: AKI cases averted vs the ban (crew-level in the report).
    aki_value = report.aki_cases_averted_vs_ban * a.aki_case_cost_usd
    deaths_averted = report.aki_cases_averted_vs_ban * a.heat_death_per_aki_case
    death_value = deaths_averted * a.heat_death_cost_usd

    # Compliance shield: expected fines avoided.
    fines = a.fine_per_worker_usd * crew * a.fine_probability_per_season

    # Turnover reduction.
    turnover = a.turnover_cost_per_worker_usd * crew * a.turnover_reduction

    cost = report.capital_cost_usd + report.recurring_cost_usd

    headline_lo = prod_lo + recovered + aki_value + fines
    headline_hi = prod_hi + recovered + aki_value + fines
    total_lo = headline_lo + death_value + turnover
    total_hi = headline_hi + death_value + turnover

    roi_lo = headline_lo / cost if cost else float("inf")
    roi_hi = headline_hi / cost if cost else float("inf")
    # payback: how many season-days until the headline (low) benefit covers the cost
    daily_headline = headline_lo / report.season_days if report.season_days else 0.0
    payback = (cost / daily_headline) if daily_headline > 0 else float("inf")

    return BusinessCase(
        crew_size=crew,
        season_days=report.season_days,
        productivity_value_lo=round(prod_lo, 0),
        productivity_value_hi=round(prod_hi, 0),
        recovered_safe_work_value=round(recovered, 0),
        aki_value=round(aki_value, 0),
        fines_avoided_value=round(fines, 0),
        death_averted_value=round(death_value, 0),
        turnover_value=round(turnover, 0),
        headline_benefit_lo=round(headline_lo, 0),
        headline_benefit_hi=round(headline_hi, 0),
        total_benefit_lo=round(total_lo, 0),
        total_benefit_hi=round(total_hi, 0),
        program_cost_usd=round(cost, 0),
        net_benefit_lo=round(headline_lo - cost, 0),
        net_benefit_hi=round(headline_hi - cost, 0),
        roi_multiple_lo=round(roi_lo, 1),
        roi_multiple_hi=round(roi_hi, 1),
        payback_days=round(payback, 1),
        assumptions={
            "daily_value_per_worker_usd": a.daily_value_per_worker_usd,
            "aki_case_cost_usd": a.aki_case_cost_usd,
            "fine_per_worker_usd": a.fine_per_worker_usd,
            "fine_probability_per_season": a.fine_probability_per_season,
            "deaths_averted_estimate": round(deaths_averted, 3),
            "headline_excludes": ["death_averted_value", "turnover_value"],
            "note": "Illustrative, conservative, tunable (data/economics.json). Headline ROI excludes the death and turnover terms.",
        },
    )
