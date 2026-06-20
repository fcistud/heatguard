"""Hydration target & max-safe-exposure from the ISO 7933 PHS model.

Wraps ``pythermalcomfort.models.phs`` (Predicted Heat Strain, ISO 7933:2023).

* ``max_safe_minutes`` runs PHS at the *full working* metabolic rate over a long
  horizon (480 min) to read the true minutes-to-limit ``d_lim_t_re`` /
  ``d_lim_loss_95`` (they cap at ``duration``, so a long horizon is required).
  This is "how long can they work continuously before a mandatory break" — the
  scheduler turns it into a work-fraction cap, not a hard STOP.
* ``hydration_target`` runs PHS at the *weighted* metabolic rate of the called
  cycle over 60 min -> per-hour sweat loss (the drink target) and end-of-hour
  core temperature.

PHS is only valid for M in [100, 450] W/m^2 (met in [1.72, 7.74]); ``met`` is
clamped into that window and provenance reported via ``HydrationTarget.phs_valid``.
"""
from __future__ import annotations

import math
import warnings

from pythermalcomfort.models import phs

from .types import Conditions, HydrationTarget, MetabolicCategory, Worker

PHS_MET_MIN = 100.0 / 58.15  # 1.7197 met
PHS_MET_MAX = 450.0 / 58.15  # 7.7386 met
_REST_MET = MetabolicCategory.REST.met
_CLO_GULF_CONSTRUCTION = 0.6  # long-sleeve cotton coveralls + hard hat


def _clamp_met(met: float) -> float:
    return max(PHS_MET_MIN, min(PHS_MET_MAX, met))


def _run_phs(c: Conditions, worker: Worker, met: float, duration_min: int):
    # Clamp inputs to the ISO 7933 Annex A applicability envelope so the model
    # stays solvable in Gulf extremes (tr<=60 desert globe, tdb<=50, v<=3). The
    # clamped values still represent a severe load; p_a (humidity) is left as-is
    # and a NaN result is reported honestly via phs_valid.
    tdb = max(15.0, min(50.0, c.weather.tdb_c))
    tr = max(0.0, min(60.0, c.globe_c))
    v = max(0.3, min(3.0, c.weather.wind_ms))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # PHS warns on out-of-envelope inputs; we report via phs_valid
        return phs(
            tdb=tdb,
            tr=tr,                        # radiant load from the globe temperature (never just tdb under sun)
            v=v,
            rh=c.weather.rh_pct,
            met=_clamp_met(met),
            clo=_CLO_GULF_CONSTRUCTION,
            posture=c.posture.value,
            duration=duration_min,
            acclimatized=100 if worker.acclimatized else 0,
            weight=worker.weight_kg,
            height=worker.height_m,
            drink=1,                      # free drinking — the whole point of the intervention
            round_output=False,
        )


def max_safe_minutes(c: Conditions, worker: Worker) -> tuple[float, bool]:
    """Max minutes of *continuous* full-intensity work before a mandatory break.

    Returns ``(minutes, phs_valid)``; ``minutes`` is clamped to [0, 480].
    """
    r = _run_phs(c, worker, c.met_category.met, 480)
    candidates = [
        x for x in (r.d_lim_t_re, r.d_lim_loss_95)
        if x is not None and math.isfinite(x)
    ]
    if not candidates:
        return 480.0, False
    return float(max(0.0, min(float(min(candidates)), 480.0))), True


def _fallback_sweat_ml(wbgt_c: float, met: float) -> float:
    """Rough sweat estimate when PHS is undefined (kept conservative)."""
    base = 200.0 + max(0.0, wbgt_c - 20.0) * 45.0
    return max(200.0, min(1600.0, base * (met / MetabolicCategory.MODERATE.met)))


def hydration_target(
    c: Conditions,
    worker: Worker,
    work_fraction: float,
    max_exposure_min: float,
    duration_min: int = 60,
) -> HydrationTarget:
    cat = c.met_category
    met_eff = work_fraction * cat.met + (1.0 - work_fraction) * _REST_MET
    r = _run_phs(c, worker, met_eff, duration_min)

    sweat = r.sweat_loss_g
    core = r.t_cr
    phs_valid = sweat is not None and math.isfinite(sweat)
    if not phs_valid:
        sweat = _fallback_sweat_ml(c.wbgt_c, met_eff)
        core = float("nan")

    water = float(sweat)  # 1 g sweat ~ 1 mL water to replace
    return HydrationTarget(
        sweat_loss_g_per_h=float(sweat),
        water_ml_per_h=water,
        cups_250ml_per_h=water / 250.0,
        max_exposure_min=float(max_exposure_min),
        core_temp_c=float(core),
        phs_valid=phs_valid,
    )
