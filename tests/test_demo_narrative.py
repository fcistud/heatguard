"""Byte-identical golden parity for the four demo narratives.

Characterization baseline (pre WO-003):
- Collected suite size: 128 tests (post WO-003 pins: 152 collected)
- Tolerance bands in this module were:
  - dubai focus: gap_hours >= 10 (README claimed 12)
  - riyadh focus: gap_hours >= 5
  - abu_dhabi focus: gap_hours >= 10
  - doha focus: gap_hours >= 5
  - dubai season: danger_hours_caught_vs_ban > 100; ban_coverage_pct < 100
  - riyadh season: ban_only_safe_hours > 0
  - abu_dhabi/doha season: danger_hours_caught_vs_ban > 0
Those bands are replaced by byte equality against tests/golden/.
"""
from __future__ import annotations

import pytest

from heatguard import golden
from heatguard.service import DEMOS, build_demo, forecast_timeline, timeline_for_day
from conftest import assert_golden, golden_tree_fingerprint


@pytest.mark.parametrize("site_key", ["dubai", "riyadh", "abu_dhabi", "doha"])
def test_focus_day_hourly_matches_golden(site_key):
    cfg = DEMOS[site_key]
    tl = timeline_for_day(site_key, cfg["focus_day"])
    payload = {
        "site_key": site_key,
        "date": str(cfg["focus_day"]),
        "rows": golden._hourly_from_timeline(tl),
    }
    assert_golden(payload, site_key, "hourly.json")


@pytest.mark.parametrize("site_key", ["dubai", "riyadh", "abu_dhabi", "doha"])
def test_focus_day_timeline_matches_golden(site_key):
    cfg = DEMOS[site_key]
    tl = timeline_for_day(site_key, cfg["focus_day"])
    demo = build_demo(site_key, crew=100)
    payload = {
        "site_key": site_key,
        "timeline": tl,
        "demo_headline": demo["headline"],
        "demo_focus_day": demo["focus_day"],
        "demo_intensity": demo["intensity"],
    }
    assert_golden(payload, site_key, "focus_day.json")


@pytest.mark.parametrize("site_key", ["dubai", "riyadh", "abu_dhabi", "doha"])
def test_forecast_matches_golden(site_key):
    forecast = forecast_timeline(site_key)
    assert_golden({"site_key": site_key, "forecast": forecast}, site_key, "forecast.json")


@pytest.mark.parametrize("site_key", ["dubai", "riyadh", "abu_dhabi", "doha"])
def test_impact_economics_sensitivity_matches_golden(site_key):
    demo = build_demo(site_key, crew=100)
    payload = {
        "site_key": site_key,
        "crew": 100,
        "impact": demo["impact"],
        "economics": demo["economics"],
        "sensitivity": demo["sensitivity"],
    }
    assert_golden(payload, site_key, "impact_economics_sensitivity.json")


@pytest.mark.parametrize("site_key", ["dubai", "riyadh", "abu_dhabi", "doha"])
def test_compliance_chain_matches_golden(site_key):
    demo = build_demo(site_key, crew=100)
    # Rebuild the same way capture does for a stable surface
    from dataclasses import asdict
    from heatguard.service import compliance_for_day

    log = compliance_for_day(site_key, DEMOS[site_key]["focus_day"])
    assert log.verify_chain()
    payload = {
        "site_key": site_key,
        "site_name": log.site_name,
        "genesis": "0" * 64,
        "verified": True,
        "head_hash": log.head_hash,
        "summary": log.summary(),
        "records": [asdict(r) for r in log.records],
    }
    assert_golden(payload, site_key, "compliance_chain.json")
    # Narrative still surfaces the demo export for the UI path
    assert demo["compliance"]["summary"]["verified"] is True


def test_full_tree_regenerate_byte_identical():
    diffs = golden.check_against_committed()
    assert diffs == [], "\n".join(diffs)


def test_normal_suite_helper_does_not_write_goldens():
    """assert_golden / check paths are read-only — fingerprint must be stable."""
    before = golden_tree_fingerprint()
    # Exercise read-only helpers
    _ = golden.check_against_committed(sites=["dubai"])
    after = golden_tree_fingerprint()
    assert before == after
