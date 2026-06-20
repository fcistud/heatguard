from __future__ import annotations

import math

from heatguard import hydration
from heatguard.scheduler import build_conditions
from heatguard.types import MetabolicCategory as MC

from conftest import weather


def _cond(site, hour, tdb, rh, sw, cat=MC.HEAVY):
    return build_conditions(weather(hour, tdb, rh, sw=sw, direct=sw * 0.85), site, cat)


def test_met_validity_window():
    assert math.isclose(hydration.PHS_MET_MIN, 100 / 58.15, rel_tol=1e-6)
    assert math.isclose(hydration.PHS_MET_MAX, 450 / 58.15, rel_tol=1e-6)
    assert hydration._clamp_met(1.0) == hydration.PHS_MET_MIN
    assert hydration._clamp_met(9.0) == hydration.PHS_MET_MAX


def test_max_safe_minutes_shorter_when_hotter(riyadh, veteran):
    cool, _ = hydration.max_safe_minutes(_cond(riyadh, 9, 35, 30, 600), veteran)
    hot, _ = hydration.max_safe_minutes(_cond(riyadh, 12, 47, 18, 950), veteran)
    assert hot <= cool


def test_hydration_positive_and_finite(riyadh, veteran):
    c = _cond(riyadh, 12, 44, 20, 920)
    mins, _ = hydration.max_safe_minutes(c, veteran)
    hyd = hydration.hydration_target(c, veteran, work_fraction=0.5, max_exposure_min=mins)
    assert hyd.water_ml_per_h > 0
    assert hyd.cups_250ml_per_h > 0
    assert 0.0 <= hyd.max_exposure_min <= 480.0


def test_light_work_does_not_crash_below_phs_floor(riyadh, veteran):
    # light weighted by high rest -> met below PHS floor; clamp keeps it defined
    c = _cond(riyadh, 9, 33, 25, 400, cat=MC.LIGHT)
    mins, _ = hydration.max_safe_minutes(c, veteran)
    hyd = hydration.hydration_target(c, veteran, work_fraction=0.25, max_exposure_min=mins)
    assert math.isfinite(hyd.water_ml_per_h)
    assert hyd.water_ml_per_h > 0


def test_sweat_rises_with_intensity(riyadh, veteran):
    c_mod = _cond(riyadh, 11, 40, 25, 800, cat=MC.MODERATE)
    c_heavy = _cond(riyadh, 11, 40, 25, 800, cat=MC.HEAVY)
    s_mod = hydration.hydration_target(c_mod, veteran, 1.0, 60).sweat_loss_g_per_h
    s_heavy = hydration.hydration_target(c_heavy, veteran, 1.0, 60).sweat_loss_g_per_h
    assert s_heavy > s_mod
