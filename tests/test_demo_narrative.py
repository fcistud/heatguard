"""Golden-file style tests for the demo narrative (committed weather cache)."""
from __future__ import annotations

from heatguard.service import DEMOS, build_demo, timeline_for_day


def test_dubai_may_focus_day_has_calendar_gap():
    """May 2025: HeatGuard protects hours the UAE calendar ban does not cover."""
    cfg = DEMOS["dubai"]
    tl = timeline_for_day("dubai", cfg["focus_day"])
    assert tl["date"] == str(cfg["focus_day"])
    assert tl["country"] == "AE"
    # README/demo: 12 gap hours on focus day; allow small drift if cache updates
    assert tl["gap_hours"] >= 10
    assert any(r["gap"] for r in tl["rows"])


def test_dubai_focus_day_ban_not_active_in_may():
    """UAE ban season starts 15 June — May focus day should have zero banned hours."""
    cfg = DEMOS["dubai"]
    tl = timeline_for_day("dubai", cfg["focus_day"])
    assert sum(1 for r in tl["rows"] if r["banned"]) == 0


def test_riyadh_focus_day_has_morning_gap():
    """Riyadh summer: humid morning danger outside the noon ban window."""
    cfg = DEMOS["riyadh"]
    tl = timeline_for_day("riyadh", cfg["focus_day"])
    assert tl["gap_hours"] >= 5
    banned_hours = {r["hour"] for r in tl["rows"] if r["banned"]}
    gap_hours = {r["hour"] for r in tl["rows"] if r["gap"]}
    assert gap_hours - banned_hours, "some gap hours fall outside the ban window"


def test_dubai_season_impact_caught_vs_ban():
    demo = build_demo("dubai", crew=100)
    imp = demo["impact"]
    assert imp["danger_hours_caught_vs_ban"] > 100
    assert imp["ban_coverage_pct"] < 100.0


def test_riyadh_season_has_ban_overrestriction():
    demo = build_demo("riyadh", crew=100)
    assert demo["impact"]["ban_only_safe_hours"] > 0


def test_abu_dhabi_focus_day_has_calendar_gap():
    """May 2025 shoulder season — adaptive signals before UAE ban season."""
    cfg = DEMOS["abu_dhabi"]
    tl = timeline_for_day("abu_dhabi", cfg["focus_day"])
    assert tl["country"] == "AE"
    assert tl["gap_hours"] >= 10
    assert sum(1 for r in tl["rows"] if r["banned"]) == 0


def test_doha_focus_day_has_morning_gap():
    """Qatar WBGT ban covers mid-day but not humid morning danger."""
    cfg = DEMOS["doha"]
    tl = timeline_for_day("doha", cfg["focus_day"])
    assert tl["country"] == "QA"
    assert tl["gap_hours"] >= 5
    banned_hours = {r["hour"] for r in tl["rows"] if r["banned"]}
    gap_hours = {r["hour"] for r in tl["rows"] if r["gap"]}
    assert gap_hours - banned_hours


def test_abu_dhabi_and_doha_season_impact():
    for key in ("abu_dhabi", "doha"):
        demo = build_demo(key, crew=100)
        assert demo["impact"]["danger_hours_caught_vs_ban"] > 0
