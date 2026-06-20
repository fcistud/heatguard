"""The orchestrator: ``Conditions`` + ``Worker`` -> ``Advisory``.

The called work fraction is the **most conservative** of three constraints:

1. the ACGIH/ISO 7243 screening table (regulatory),
2. the NIOSH acclimatization ramp (new-worker cap), and
3. the ISO 7933 PHS physiological limit (max safe continuous minutes / 60).

STOP fires only when no safe work block remains (under ~5 min) or WBGT is above
the table's most-permissive ceiling. Otherwise a work-rest cycle is prescribed.
"""
from __future__ import annotations

from dataclasses import replace

from . import acclimatization, hydration, worktables
from .types import (
    Advisory,
    Conditions,
    MetabolicCategory,
    Posture,
    Signal,
    Site,
    Weather,
    Worker,
    WorkRestCycle,
)
from .wbgt import estimate_wbgt, from_measured


def build_conditions(
    weather: Weather,
    site: Site,
    met_category: MetabolicCategory,
    posture: Posture = Posture.STANDING,
    measured_wbgt_c: float | None = None,
) -> Conditions:
    """Resolve weather into a decision input (estimated WBGT, or a meter reading)."""
    if measured_wbgt_c is not None:
        est = from_measured(measured_wbgt_c, weather.tdb_c, weather.rh_pct)
    else:
        est = estimate_wbgt(weather, site)
    return Conditions(
        site=site,
        weather=weather,
        wbgt_c=est.wbgt_c,
        wbgt_source=est.source,
        globe_c=est.globe_c,
        met_category=met_category,
        posture=posture,
    )


def decide(c: Conditions, worker: Worker) -> Advisory:
    cat = c.met_category
    table_acclimatized = not acclimatization.use_unacclimatized_thresholds(worker)

    base = worktables.work_rest_cycle(c.wbgt_c, cat, table_acclimatized)
    allowed = acclimatization.allowed_fraction(worker)
    eff_worker = replace(worker, acclimatized=table_acclimatized)

    mins, mins_valid = hydration.max_safe_minutes(c, eff_worker)
    mins = float(mins)
    phs_fraction = max(0.0, min(1.0, mins / 60.0)) if mins_valid else 1.0

    # The acclimatization cap limits exposure to *heat stress* — it only binds
    # when the conditions are actually hot (the table or PHS already restricts
    # work). In cool conditions a new worker can work normally.
    heat_stress = base.work_fraction < 1.0 or phs_fraction < 1.0
    acc_cap = allowed if heat_stress else 1.0

    eff_fraction = float(min(base.work_fraction, acc_cap, phs_fraction))
    work_min = int(round(eff_fraction * 60 / 5) * 5)

    stopped = work_min < 5
    if stopped:
        eff_fraction, work_min = 0.0, 0

    acc_binding = bool(heat_stress and acc_cap <= base.work_fraction and acc_cap <= phs_fraction and acc_cap < 1.0)
    phs_binding = bool(mins_valid and phs_fraction < base.work_fraction and phs_fraction < acc_cap)

    cycle = WorkRestCycle(
        work_fraction=eff_fraction,
        work_min_per_hour=work_min,
        rest_min_per_hour=60 - work_min,
        threshold_wbgt_c=base.threshold_wbgt_c,
        table=base.table,
        capped_by_acclimatization=acc_binding and not stopped,
    )

    hyd = hydration.hydration_target(c, eff_worker, eff_fraction, mins)

    # Signal + rationale.
    if stopped:
        signal = Signal.STOP
        if base.work_fraction <= 0.0:
            rationale = "WBGT is above the safe ceiling for this work intensity — stop outdoor work and move to shade."
        else:
            rationale = (
                f"Heat strain limits safe continuous work to under {mins:.0f} min — "
                "stop outdoor work and move to shade."
            )
    elif eff_fraction <= 0.25:
        signal = Signal.REST_IN_SHADE
        rationale = (
            f"Heat requires {cycle.rest_min_per_hour} min/hour of shaded rest — work only "
            f"{cycle.work_min_per_hour} min; drink {hyd.cups_250ml_per_h:.1f} cups/hour."
        )
    else:
        signal = Signal.WORK
        rationale = (
            f"Work {cycle.work_min_per_hour} min then rest {cycle.rest_min_per_hour} min in shade; "
            f"drink {hyd.cups_250ml_per_h:.1f} cups/hour."
        )

    drivers = []
    if not stopped and phs_binding:
        drivers.append(f"physiological limit ~{mins:.0f} min continuous")
    if acc_binding:
        drivers.append(
            f"new worker day {worker.days_on_job + 1}: {int(allowed * 100)}% cap + Action-Limit table"
        )
    if drivers:
        rationale += " (" + "; ".join(drivers) + ")"
    if c.wbgt_source != "measured":
        rationale += f" [WBGT {c.wbgt_source}-estimated]"

    return Advisory(
        timestamp=c.weather.timestamp,
        site_name=c.site.name,
        worker_id=worker.worker_id,
        wbgt_c=c.wbgt_c,
        wbgt_source=c.wbgt_source,
        signal=signal,
        cycle=cycle,
        hydration=hyd,
        acclim_fraction=allowed,
        rationale=rationale,
        risk_score=worktables.risk_score(c.wbgt_c, cat, table_acclimatized),
    )


def schedule(
    weather: Weather,
    site: Site,
    worker: Worker,
    cat: MetabolicCategory,
    posture: Posture = Posture.STANDING,
    measured_wbgt_c: float | None = None,
) -> Advisory:
    """Convenience: weather -> Advisory in one call."""
    return decide(build_conditions(weather, site, cat, posture, measured_wbgt_c), worker)


def live_signal(advisory: Advisory, minute_into_hour: int) -> Signal:
    """Instantaneous broadcast signal for a wall-clock minute of the hour.

    Models one work block then one shaded-rest block; a DRINK_NOW pulse opens
    each rest break and recurs at the hydration cadence during work.
    """
    if advisory.signal is Signal.STOP:
        return Signal.STOP
    work_min = advisory.cycle.work_min_per_hour
    m = minute_into_hour % 60
    cups = max(1.0, advisory.hydration.cups_250ml_per_h)
    drink_every = max(10, int(round(60 / cups)))
    if m >= work_min:
        return Signal.DRINK_NOW if (m - work_min) < 2 else Signal.REST_IN_SHADE
    return Signal.DRINK_NOW if (m > 0 and m % drink_every == 0) else Signal.WORK
