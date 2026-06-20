"""NIOSH acclimatization ramp for new arrivals — the deadliest, cheapest-to-protect
group. Pure scheduling, zero cost.

Two effects, both applied in ``scheduler.decide``:

1. **Threshold** — until the ramp completes an unacclimatized worker is screened
   against the stricter Action-Limit table (``use_unacclimatized_thresholds``).
2. **Exposure cap** — ``allowed_fraction`` is an upper bound on the called work
   fraction (NIOSH: brand-new workers 20% day-0 rising 20%/day over 5 days;
   heat-experienced-but-new-to-this-job 50% then 100%).
"""
from __future__ import annotations

from .types import Worker

_NEW_RAMP = [0.20, 0.40, 0.60, 0.80, 1.00]   # days 0..4 for a brand-new worker
_EXPERIENCED_RAMP = [0.50, 1.00]              # days 0..1 for a heat-experienced worker


def _ramp(worker: Worker) -> list[float]:
    return _EXPERIENCED_RAMP if worker.experienced_elsewhere else _NEW_RAMP


def is_ramping(worker: Worker) -> bool:
    """True while the worker is still completing the acclimatization ramp.

    The ramp length tracks the worker's ramp (5 days new, 2 days experienced) so
    the exposure cap and the table-selection agree on when ramping ends.
    """
    if worker.acclimatized:
        return False
    return worker.days_on_job < len(_ramp(worker))


def allowed_fraction(worker: Worker) -> float:
    """Upper bound on the work fraction from the acclimatization ramp (0-1)."""
    if worker.acclimatized:
        return 1.0
    ramp = _ramp(worker)
    if worker.days_on_job >= len(ramp):
        return 1.0
    return ramp[max(0, worker.days_on_job)]


def use_unacclimatized_thresholds(worker: Worker) -> bool:
    """Whether to screen against the stricter Action-Limit table."""
    return is_ramping(worker)
