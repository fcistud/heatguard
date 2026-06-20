"""Shared data structures for the HeatGuard engine.

The decision flow for a single (worker, hour) is::

    Weather --estimate_wbgt--> Conditions --scheduler.decide--> Advisory --compliance.append-->

Input/output records are frozen dataclasses so the engine stays pure and the
audit trail is immutable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MetabolicCategory(str, Enum):
    """ACGIH / ISO 8996 work-intensity categories.

    ``met`` values are in *met units* (1 met = 58.15 W/m^2). pythermalcomfort's
    ``phs`` multiplies ``met`` by 58.15 to get the metabolic rate M in W/m^2, and
    the ISO 7933 model is only valid for M in [100, 450] W/m^2 — see
    ``hydration.PHS_MET_MIN/MAX``.
    """

    REST = "rest"            # ~65 W/m^2  (1.1 met) — baseline, below PHS validity floor
    LIGHT = "light"          # ~105 W/m^2 (1.8 met)
    MODERATE = "moderate"    # ~169 W/m^2 (2.9 met)
    HEAVY = "heavy"          # ~233 W/m^2 (4.0 met)
    VERY_HEAVY = "very_heavy"  # ~291 W/m^2 (5.0 met)

    @property
    def met(self) -> float:
        return _MET_UNITS[self]

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


_MET_UNITS: dict["MetabolicCategory", float] = {
    MetabolicCategory.REST: 1.1,
    MetabolicCategory.LIGHT: 1.8,
    MetabolicCategory.MODERATE: 2.9,
    MetabolicCategory.HEAVY: 4.0,
    MetabolicCategory.VERY_HEAVY: 5.0,
}


class Posture(str, Enum):
    STANDING = "standing"
    SITTING = "sitting"
    CROUCHING = "crouching"


class Signal(str, Enum):
    """The single instruction broadcast to the crew via horn/light/phone."""

    WORK = "WORK"
    REST_IN_SHADE = "REST_IN_SHADE"
    DRINK_NOW = "DRINK_NOW"
    STOP = "STOP"

    @property
    def color(self) -> str:
        return {
            "WORK": "#16a34a",          # green
            "REST_IN_SHADE": "#f59e0b",  # amber
            "DRINK_NOW": "#0ea5e9",      # blue
            "STOP": "#dc2626",           # red
        }[self.value]


@dataclass(frozen=True, slots=True)
class Site:
    name: str
    lat: float
    lon: float
    elevation_m: float
    tz: str
    country: str  # ISO-2, selects the calendar-ban rule (e.g. "SA", "AE", "QA")


@dataclass(frozen=True, slots=True)
class Weather:
    """One hourly weather sample in SI units (wind in m/s, pressure in hPa)."""

    timestamp: datetime          # timezone-aware (site-local)
    tdb_c: float                 # 2 m air (dry-bulb) temperature [degC]
    rh_pct: float                # relative humidity [%]
    wind_ms: float               # 10 m wind speed [m/s]
    shortwave_wm2: float         # global horizontal solar radiation (ssrd) [W/m^2]
    direct_wm2: float            # direct beam on horizontal (fdir) [W/m^2]
    dew_point_c: float
    pressure_hpa: float          # surface pressure [hPa]


@dataclass(frozen=True, slots=True)
class Conditions:
    """A fully resolved decision input: weather + derived WBGT + work context."""

    site: Site
    weather: Weather
    wbgt_c: float
    wbgt_source: str             # "liljegren" | "fallback" | "measured"
    globe_c: float               # estimated black-globe temperature [degC] (radiant load)
    met_category: MetabolicCategory
    posture: Posture = Posture.STANDING


@dataclass(frozen=True, slots=True)
class Worker:
    worker_id: str
    days_on_job: int = 30        # 0 = first day on site
    acclimatized: bool = True    # baseline acclimatization status
    experienced_elsewhere: bool = False  # new to THIS job but heat-experienced -> faster ramp
    weight_kg: float = 75.0
    height_m: float = 1.75


@dataclass(frozen=True, slots=True)
class WorkRestCycle:
    work_fraction: float         # 0.0-1.0 of the hour spent working
    work_min_per_hour: int
    rest_min_per_hour: int
    threshold_wbgt_c: float | None  # the TLV/AL threshold that produced this fraction
    table: str                   # "TLV" (acclimatized) | "AL" (action limit, unacclimatized)
    capped_by_acclimatization: bool = False


@dataclass(frozen=True, slots=True)
class HydrationTarget:
    sweat_loss_g_per_h: float
    water_ml_per_h: float
    cups_250ml_per_h: float
    max_exposure_min: float      # min(d_lim_t_re, d_lim_loss_95), continuous work at full intensity
    core_temp_c: float           # projected end-of-hour core temperature (t_cr)
    phs_valid: bool              # False if conditions/met fell outside the ISO 7933 envelope


@dataclass(frozen=True, slots=True)
class Advisory:
    """The decision output for one (worker, hour, conditions)."""

    timestamp: datetime
    site_name: str
    worker_id: str
    wbgt_c: float
    wbgt_source: str
    signal: Signal
    cycle: WorkRestCycle
    hydration: HydrationTarget
    acclim_fraction: float       # 0-1 exposure cap from the ramp
    rationale: str
    risk_score: float            # 0-1 continuous WBGT-vs-thresholds score (UI gauge only)

    def to_dict(self) -> dict:
        """JSON-serialisable view (used by the compliance log and the API)."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "site_name": self.site_name,
            "worker_id": self.worker_id,
            "wbgt_c": round(self.wbgt_c, 2),
            "wbgt_source": self.wbgt_source,
            "signal": self.signal.value,
            "cycle": {
                "work_fraction": self.cycle.work_fraction,
                "work_min_per_hour": self.cycle.work_min_per_hour,
                "rest_min_per_hour": self.cycle.rest_min_per_hour,
                "threshold_wbgt_c": self.cycle.threshold_wbgt_c,
                "table": self.cycle.table,
                "capped_by_acclimatization": self.cycle.capped_by_acclimatization,
            },
            "hydration": {
                "sweat_loss_g_per_h": round(self.hydration.sweat_loss_g_per_h, 1),
                "water_ml_per_h": round(self.hydration.water_ml_per_h, 1),
                "cups_250ml_per_h": round(self.hydration.cups_250ml_per_h, 2),
                "max_exposure_min": round(self.hydration.max_exposure_min, 1),
                "core_temp_c": round(self.hydration.core_temp_c, 2),
                "phs_valid": self.hydration.phs_valid,
            },
            "acclim_fraction": self.acclim_fraction,
            "rationale": self.rationale,
            "risk_score": round(self.risk_score, 3),
        }
