"""Project the per-crew impact to a workforce — the 'danger & scale / lives saved' story.

Turns HeatGuard's per-crew season impact into workforce-scale figures (danger-hours
protected, AKI cases averted, lives saved, productivity, value) for a landing page,
a pitch deck, or a dashboard panel. The scale *context* numbers are grounded (sources
in datasets.md); the projection multipliers come from the same effect sizes the impact
model uses, so the big numbers trace back to the per-crew result.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import economics
from .economics import EconomicAssumptions
from .impact import EffectSizes, ImpactReport

# Grounded magnitude of the problem (see datasets.md §4, §7).
SCALE_CONTEXT = {
    "arab_states_migrant_workers": 24_000_000,
    "migrant_share_pct": 41.4,           # highest migrant-worker share of any world region (ILO 2019)
    "gulf_summer_peak_c": 50,            # station records exceed 50 C; reanalysis ~46-47 C
    "migrant_deaths_per_year": 10_000,   # all-cause migrant deaths/yr (FairSquare); heat a major hidden contributor
    "deaths_caveat": ">50% certified without an underlying cause, so heat-attributable mortality is hidden",
    "ban_blind_spots": "the calendar ban misses May/September heat, humid mornings, and unacclimatized newcomers",
    "gulf_studies_note": "only 1 of 19 migrant-worker heat studies worldwide came from the Gulf — a near-total evidence void",
}

# Illustrative workforce sizes for the scale story.
WORKFORCE_PRESETS = {
    "contractor": 5_000,        # one large labour-supply contractor
    "megaproject": 100_000,     # a Gulf megaproject workforce
    "gulf_outdoor": 5_000_000,  # an illustrative slice of the regional outdoor workforce
}


@dataclass(frozen=True, slots=True)
class ScaleProjection:
    workforce: int
    season_days: int
    danger_hours_protected: float       # worker-hours of danger the ban missed, that HeatGuard catches
    aki_cases_averted: float
    lives_saved: float                  # deaths averted = AKI averted x severity ratio
    productivity_worker_hours_lo: float
    productivity_worker_hours_hi: float
    value_usd_lo: float                 # conservative headline benefit at scale
    value_usd_hi: float
    program_cost_usd: float
    cost_per_worker_usd: float
    assumptions: dict

    def to_dict(self) -> dict:
        return asdict(self)


def project(
    report: ImpactReport,
    workforce: int,
    effects: EffectSizes | None = None,
    econ: EconomicAssumptions | None = None,
) -> ScaleProjection:
    """Scale a per-crew ``ImpactReport`` up to ``workforce`` workers for one season."""
    effects = effects or EffectSizes.from_baseline()
    econ = econ or EconomicAssumptions.from_file()
    crew = max(1, report.crew_size)
    bc = economics.business_case(report, econ)

    # Reduce to per-worker, then scale to the workforce.
    danger_per_worker = report.danger_hours_caught_vs_ban            # per representative worker
    aki_per_worker = report.aki_cases_averted_vs_ban / crew         # crew-level field / crew
    deaths_per_worker = aki_per_worker * econ.heat_death_per_aki_case
    prod_lo_pw = report.productivity_worker_hours_lo / crew
    prod_hi_pw = report.productivity_worker_hours_hi / crew
    val_lo_pw = bc.headline_benefit_lo / crew
    val_hi_pw = bc.headline_benefit_hi / crew
    cost_pw = bc.program_cost_usd / crew

    n = workforce
    return ScaleProjection(
        workforce=n,
        season_days=report.season_days,
        danger_hours_protected=round(danger_per_worker * n),
        aki_cases_averted=round(aki_per_worker * n),
        lives_saved=round(deaths_per_worker * n, 1),
        productivity_worker_hours_lo=round(prod_lo_pw * n),
        productivity_worker_hours_hi=round(prod_hi_pw * n),
        value_usd_lo=round(val_lo_pw * n),
        value_usd_hi=round(val_hi_pw * n),
        program_cost_usd=round(cost_pw * n),
        cost_per_worker_usd=round(cost_pw, 2),
        assumptions={
            "basis": f"per-crew season impact ({crew} workers) scaled to {n:,} workers",
            "lives_saved_model": "AKI cases averted x heat-death-per-AKI severity ratio "
                                 f"({econ.heat_death_per_aki_case})",
            "value": "conservative headline benefit (productivity + recovered safe work + AKI + fines)",
            "note": "Illustrative; the effect sizes transfer from Nicaragua sugarcane to Gulf "
                    "construction with uncertainty (see datasets.md).",
        },
    )
