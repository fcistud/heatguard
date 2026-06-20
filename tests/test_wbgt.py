from __future__ import annotations

import math

from heatguard import wbgt as W
from heatguard.wbgt import estimate_wbgt, from_measured, stull_wet_bulb

from conftest import weather


def test_wet_bulb_below_dry_bulb():
    assert stull_wet_bulb(45.0, 20.0) < 45.0
    assert stull_wet_bulb(30.0, 90.0) < 30.0


def test_wet_bulb_rises_with_humidity():
    assert stull_wet_bulb(40.0, 60.0) > stull_wet_bulb(40.0, 20.0)


def test_daytime_uses_liljegren(riyadh):
    w = weather(12, 45, 18, wind=2.0, sw=940, direct=820)
    est = estimate_wbgt(w, riyadh)
    assert est.source == "liljegren"
    assert math.isfinite(est.wbgt_c)
    # dry desert: WBGT well below air temperature
    assert est.wbgt_c < w.tdb_c
    # globe hotter than air under sun
    assert est.globe_c >= w.tdb_c


def test_night_uses_fallback(riyadh):
    w = weather(2, 33, 40, wind=1.5, sw=0, direct=0)
    est = estimate_wbgt(w, riyadh)
    assert est.source == "fallback"
    assert est.wbgt_c < w.tdb_c


def test_humidity_raises_wbgt(riyadh):
    dry = estimate_wbgt(weather(12, 42, 15, sw=900, direct=780), riyadh).wbgt_c
    humid = estimate_wbgt(weather(12, 42, 55, sw=900, direct=780), riyadh).wbgt_c
    assert humid > dry


def test_measured_passthrough():
    est = from_measured(31.5, tdb_c=44.0, rh_pct=20.0)
    assert est.source == "measured"
    assert est.wbgt_c == 31.5
