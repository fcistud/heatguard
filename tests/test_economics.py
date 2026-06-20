from __future__ import annotations

from datetime import datetime, timedelta, timezone

from heatguard import economics, impact
from heatguard.economics import EconomicAssumptions, business_case
from heatguard.impact import EffectSizes, estimate_impact
from heatguard.types import Advisory, HydrationTarget, Signal, WorkRestCycle

TZ3 = timezone(timedelta(hours=3))


def _adv(hour, signal, work_fraction):
    cyc = WorkRestCycle(work_fraction, int(work_fraction * 60), 60 - int(work_fraction * 60), 30.0, "TLV")
    hyd = HydrationTarget(700, 700, 2.8, 45.0, 37.6, True)
    return Advisory(datetime(2024, 7, 15, hour, 0, tzinfo=TZ3), "S", "w", 33.0, "liljegren",
                    signal, cyc, hyd, 1.0, "", 0.5)


def _report(crew=100):
    hourly = [(_adv(h, Signal.STOP, 0.0), False) for h in range(8)]
    hourly += [(_adv(9, Signal.WORK, 1.0), True)]  # ban-only safe hour
    return estimate_impact(hourly, crew_size=crew, season_days=10)


def test_assumptions_load_from_file():
    a = EconomicAssumptions.from_file()
    assert a.daily_value_per_worker_usd > 0
    assert a.hourly_value_usd == a.daily_value_per_worker_usd / a.work_hours_per_day


def test_business_case_positive_roi():
    bc = business_case(_report())
    assert bc.program_cost_usd > 0
    assert bc.headline_benefit_lo > 0
    assert bc.roi_multiple_lo >= 1.0          # productivity-positive intervention
    assert bc.roi_multiple_hi >= bc.roi_multiple_lo
    assert bc.payback_days > 0


def test_headline_excludes_death_and_turnover():
    bc = business_case(_report())
    assert bc.total_benefit_lo >= bc.headline_benefit_lo
    # headline = total minus the two excluded terms
    assert abs((bc.headline_benefit_lo + bc.death_averted_value + bc.turnover_value) - bc.total_benefit_lo) < 1.0
    assert "death_averted_value" in bc.assumptions["headline_excludes"]


def test_benefit_scales_with_crew():
    small = business_case(_report(crew=10))
    big = business_case(_report(crew=100))
    assert big.headline_benefit_lo > small.headline_benefit_lo


def test_sensitivity_monotonic_in_incidence():
    hourly = [(_adv(h, Signal.STOP, 0.0), False) for h in range(10)]
    rows = impact.sensitivity(hourly, crew_size=100, season_days=10)
    averted = [r["aki_cases_averted_vs_ban"] for r in rows]
    assert averted == sorted(averted)  # higher baseline incidence -> more averted
    assert len(rows) == 5
