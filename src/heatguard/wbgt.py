"""Outdoor WBGT estimation from ordinary weather.

``pythermalcomfort.wbgt`` needs wet-bulb + globe temperatures as inputs, so the
outdoor estimate comes from the **Liljegren et al. (2008)** model via
``thermofeel`` for daytime, with a Stull-natural-wet-bulb fallback for night or
non-convergence. Every value carries its provenance (``source``) into the
compliance log and UI so the approximation is never hidden.

thermofeel quirks pinned against v2.2.0: pressure must be in **hPa** (Pa -> NaN),
the Liljegren solve returns **Kelvin**, and it returns **NaN when the sun is
below the horizon** (cos solar zenith <= 0) — hence the explicit night branch.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import NamedTuple

from .solar import cos_solar_zenith_angle
from .types import Site, Weather

# Outdoor WBGT weighting (with solar load): WBGT = 0.7*Tnwb + 0.2*Tg + 0.1*Tdb.
# Indoor / no-sun weighting: WBGT = 0.7*Tnwb + 0.3*Tdb (globe ~ air).


class WbgtEstimate(NamedTuple):
    wbgt_c: float
    source: str       # "liljegren" | "fallback" | "measured"
    globe_c: float    # black-globe temperature used as the radiant load (tr in PHS)


def stull_wet_bulb(tdb_c: float, rh_pct: float) -> float:
    """Thermodynamic wet-bulb temperature (Stull 2011 empirical fit).

    Valid roughly for RH 5-99% and T -20..50 degC; a good proxy for the natural
    wet-bulb term of WBGT.
    """
    rh = max(1.0, min(100.0, rh_pct))
    t = tdb_c
    return (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
        - 4.686035
    )


def _globe_from_wbgt(wbgt_c: float, tdb_c: float, rh_pct: float) -> float:
    """Recover a globe temperature consistent with an outdoor WBGT value."""
    tnwb = stull_wet_bulb(tdb_c, rh_pct)
    tg = (wbgt_c - 0.7 * tnwb - 0.1 * tdb_c) / 0.2
    return max(tg, tdb_c)


def wbgt_fallback(tdb_c: float, rh_pct: float, solar_wm2: float, wind_ms: float) -> tuple[float, float]:
    """Return ``(wbgt_c, globe_c)`` without the Liljegren solver.

    Used at night and whenever the solver fails. Adds a bounded solar globe bump
    that grows with radiation and shrinks with wind.
    """
    tnwb = stull_wet_bulb(tdb_c, rh_pct)
    if solar_wm2 <= 5.0:  # effectively no sun
        return 0.7 * tnwb + 0.3 * tdb_c, tdb_c
    bump = max(0.0, solar_wm2) / 1000.0 * 12.0 / (1.0 + 0.5 * max(wind_ms, 0.0))
    tg = tdb_c + bump
    return 0.7 * tnwb + 0.2 * tg + 0.1 * tdb_c, tg


def wbgt_liljegren(w: Weather, site: Site, cossza: float) -> float:
    """WBGT (degC) from the Liljegren model via thermofeel. May return NaN."""
    import numpy as np
    import thermofeel as tf

    out = tf.calculate_wbgt_liljegren(
        np.array([w.tdb_c + 273.15]),     # t2_k
        np.array([max(1.0, min(100.0, w.rh_pct))]),
        np.array([w.pressure_hpa]),        # hPa (NOT Pa)
        np.array([max(w.wind_ms, 0.3)]),
        np.array([max(w.shortwave_wm2, 0.0)]),
        np.array([max(w.direct_wm2, 0.0)]),
        np.array([cossza]),
    )
    return float(out[0]) - 273.15


def estimate_wbgt(w: Weather, site: Site, when: datetime | None = None) -> WbgtEstimate:
    """Best-effort outdoor WBGT with provenance and a consistent globe temp."""
    ts = when or w.timestamp
    cossza = cos_solar_zenith_angle(ts, site.lat, site.lon)

    if cossza > 0.02 and w.shortwave_wm2 > 5.0:
        try:
            val = wbgt_liljegren(w, site, cossza)
            if math.isfinite(val) and (w.tdb_c - 40.0) < val < (w.tdb_c + 8.0):
                return WbgtEstimate(val, "liljegren", _globe_from_wbgt(val, w.tdb_c, w.rh_pct))
        except Exception:
            pass

    val, tg = wbgt_fallback(w.tdb_c, w.rh_pct, w.shortwave_wm2, w.wind_ms)
    return WbgtEstimate(val, "fallback", tg)


def from_measured(wbgt_c: float, tdb_c: float, rh_pct: float) -> WbgtEstimate:
    """Wrap a supervisor's on-site WBGT-meter reading (bypasses estimation)."""
    return WbgtEstimate(wbgt_c, "measured", _globe_from_wbgt(wbgt_c, tdb_c, rh_pct))
