from __future__ import annotations

import pytest

from heatguard import worktables as wt
from heatguard.types import MetabolicCategory as MC

ACC = True
UNACC = False


def frac(wbgt, cat, acc=ACC):
    return wt.work_fraction(wbgt, cat, acc)[0]


def test_published_tlv_values():
    assert wt.WBGT_TLV[MC.LIGHT] == {"100": 31.0, "75": 31.0, "50": 32.0, "25": 32.5}
    assert wt.WBGT_TLV[MC.MODERATE] == {"100": 28.0, "75": 29.0, "50": 30.0, "25": 31.5}
    assert wt.WBGT_TLV[MC.HEAVY]["100"] is None and wt.WBGT_TLV[MC.HEAVY]["75"] == 27.5
    assert wt.WBGT_TLV[MC.VERY_HEAVY]["100"] is None and wt.WBGT_TLV[MC.VERY_HEAVY]["50"] == 28.0


def test_step_mapping_boundaries_moderate():
    # moderate acclimatized: 100->28, 75->29, 50->30, 25->31.5
    assert frac(20.0, MC.MODERATE) == 1.00      # below screening
    assert frac(28.0, MC.MODERATE) == 1.00      # exactly the 100% ceiling
    assert frac(28.1, MC.MODERATE) == 0.75
    assert frac(29.0, MC.MODERATE) == 0.75
    assert frac(30.0, MC.MODERATE) == 0.50
    assert frac(31.5, MC.MODERATE) == 0.25
    assert frac(31.6, MC.MODERATE) == 0.00      # above 25% ceiling -> STOP


def test_dashed_cells_allow_full_work_below_threshold():
    # very-heavy has "--" at 100% and 75%; min listed threshold is 28.0 (50/50)
    assert frac(20.0, MC.VERY_HEAVY) == 1.00
    assert frac(28.0, MC.VERY_HEAVY) == 0.50
    assert frac(30.0, MC.VERY_HEAVY) == 0.25
    assert frac(30.1, MC.VERY_HEAVY) == 0.00


def test_action_limit_is_stricter_than_tlv_everywhere():
    for cat in (MC.LIGHT, MC.MODERATE, MC.HEAVY, MC.VERY_HEAVY):
        for key in ("100", "75", "50", "25"):
            tlv = wt.WBGT_TLV[cat][key]
            al = wt.WBGT_AL[cat][key]
            if tlv is not None and al is not None:
                assert al < tlv, f"AL not stricter for {cat} {key}: AL={al} TLV={tlv}"


def test_unacclimatized_more_conservative_at_same_wbgt():
    # at WBGT 27, moderate: acclimatized allows full, unacclimatized restricts
    assert frac(27.0, MC.MODERATE, ACC) == 1.00
    assert frac(27.0, MC.MODERATE, UNACC) <= 0.50


def test_work_rest_cycle_minutes():
    cyc = wt.work_rest_cycle(30.0, MC.MODERATE, ACC)  # 50% work
    assert cyc.work_fraction == 0.50
    assert cyc.work_min_per_hour == 30 and cyc.rest_min_per_hour == 30
    assert cyc.table == "TLV"
    stop = wt.work_rest_cycle(40.0, MC.MODERATE, ACC)
    assert stop.work_fraction == 0.0 and stop.work_min_per_hour == 0


def test_risk_score_monotonic_and_bounded():
    lo = wt.risk_score(20.0, MC.MODERATE, ACC)
    mid = wt.risk_score(29.5, MC.MODERATE, ACC)
    hi = wt.risk_score(40.0, MC.MODERATE, ACC)
    assert lo == 0.0 and hi == 1.0
    assert 0.0 < mid < 1.0
    assert lo <= mid <= hi


def test_met_units_in_phs_valid_window_for_work_categories():
    # moderate/heavy/very-heavy must be inside PHS validity [1.72, 7.74]
    for cat in (MC.MODERATE, MC.HEAVY, MC.VERY_HEAVY):
        assert 1.72 <= wt.met_for_category(cat) <= 7.74
