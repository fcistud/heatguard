from __future__ import annotations

from datetime import datetime, timedelta, timezone

from heatguard import impact
from heatguard.impact import EffectSizes, estimate_impact
from heatguard.types import (
    Advisory,
    HydrationTarget,
    Signal,
    WorkRestCycle,
)

TZ3 = timezone(timedelta(hours=3))


def _adv(hour, signal, work_fraction):
    cyc = WorkRestCycle(work_fraction, int(work_fraction * 60), 60 - int(work_fraction * 60), 30.0, "TLV")
    hyd = HydrationTarget(700, 700, 2.8, 45.0, 37.6, True)
    return Advisory(
        timestamp=datetime(2024, 7, 15, hour, 0, tzinfo=TZ3),
        site_name="S", worker_id="w", wbgt_c=33.0, wbgt_source="liljegren",
        signal=signal, cycle=cyc, hydration=hyd, acclim_fraction=1.0,
        rationale="", risk_score=0.5,
    )


def test_backtest_reproduces_nicaragua():
    bt = impact.backtest_nicaragua()
    assert bt["passed"] is True
    assert abs(bt["reproduced_aki_reduction"] - 0.94) < 1e-9
    assert bt["productivity_band"] == [0.10, 0.20]


def test_coverage_zero_gives_full_incremental():
    # all danger hours OUTSIDE any ban -> full 94% credited vs ban
    hourly = [(_adv(h, Signal.STOP, 0.0), False) for h in range(10)]
    rep = estimate_impact(hourly, crew_size=100, season_days=1, effects=EffectSizes())
    assert rep.ban_coverage_pct == 0.0
    assert abs(rep.aki_cases_averted_vs_ban - rep.aki_cases_averted_heatguard) < 1e-6


def test_full_coverage_gives_zero_incremental():
    # every danger hour already inside the ban -> no incremental benefit vs ban
    hourly = [(_adv(h, Signal.STOP, 0.0), True) for h in range(10)]
    rep = estimate_impact(hourly, crew_size=100, season_days=1, effects=EffectSizes())
    assert rep.ban_coverage_pct == 100.0
    assert abs(rep.aki_cases_averted_vs_ban) < 1e-6


def test_no_danger_hours_averts_nothing():
    # a season with zero danger hours must not credit any AKI averted
    hourly = [(_adv(h, Signal.WORK, 1.0), False) for h in range(10)]
    rep = estimate_impact(hourly, crew_size=100, season_days=1, effects=EffectSizes())
    assert rep.total_danger_hours == 0
    assert rep.aki_cases_averted_heatguard == 0.0
    assert rep.aki_cases_averted_vs_ban == 0.0


def test_danger_caught_vs_ban_counts_gap():
    hourly = [
        (_adv(8, Signal.STOP, 0.0), False),       # danger, missed by ban
        (_adv(9, Signal.REST_IN_SHADE, 0.25), False),  # danger, missed by ban
        (_adv(13, Signal.STOP, 0.0), True),       # danger, covered by ban
        (_adv(7, Signal.WORK, 1.0), False),       # safe
    ]
    rep = estimate_impact(hourly, crew_size=50, season_days=1)
    assert rep.total_danger_hours == 3
    assert rep.danger_hours_in_ban == 1
    assert rep.danger_hours_caught_vs_ban == 2


def test_ban_only_safe_hours_counts_overrestriction():
    hourly = [
        (_adv(13, Signal.WORK, 1.0), True),   # ban stops work HeatGuard finds safe
        (_adv(8, Signal.WORK, 1.0), False),
    ]
    rep = estimate_impact(hourly, crew_size=10, season_days=1)
    assert rep.ban_only_safe_hours == 1


def test_impact_scales_with_crew():
    hourly = [(_adv(h, Signal.STOP, 0.0), False) for h in range(5)]
    r1 = estimate_impact(hourly, crew_size=10, season_days=1)
    r2 = estimate_impact(hourly, crew_size=100, season_days=1)
    assert r2.aki_cases_baseline == 10 * r1.aki_cases_baseline
