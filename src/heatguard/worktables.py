"""ACGIH TLV / Action-Limit screening tables (ISO 7243 family) and the
WBGT -> work-rest mapping.

The tables give the highest WBGT (degC) at which each work allocation is still
permitted, by metabolic category, for **acclimatized** workers (TLV) and
**unacclimatized** workers (Action Limit, ~3 degC stricter). A ``None`` cell
("--" in the published table) means that allocation has no screening WBGT for
that intensity — below the lowest listed threshold work is unrestricted by heat;
the physiological PHS layer (``hydration.py``) catches metabolic danger there.

Mapping is a **step lookup**, not interpolation — that is the standard's intent
and what an inspector expects. A separate continuous ``risk_score`` (interpolated)
is exposed for the UI gauge only.
"""
from __future__ import annotations

from .types import MetabolicCategory, WorkRestCycle

# Allocations ordered most-work -> most-rest. Keys used in the tables below.
_ALLOCATIONS: list[tuple[float, str]] = [
    (1.00, "100"),
    (0.75, "75"),
    (0.50, "50"),
    (0.25, "25"),
]

# WBGT (degC) ceilings. TLV = acclimatized.  (ACGIH 2017 7th-ed. screening criteria.)
WBGT_TLV: dict[MetabolicCategory, dict[str, float | None]] = {
    MetabolicCategory.LIGHT:      {"100": 31.0, "75": 31.0, "50": 32.0, "25": 32.5},
    MetabolicCategory.MODERATE:   {"100": 28.0, "75": 29.0, "50": 30.0, "25": 31.5},
    MetabolicCategory.HEAVY:      {"100": None, "75": 27.5, "50": 29.0, "25": 30.5},
    MetabolicCategory.VERY_HEAVY: {"100": None, "75": None, "50": 28.0, "25": 30.0},
}

# Action Limit = unacclimatized.
WBGT_AL: dict[MetabolicCategory, dict[str, float | None]] = {
    MetabolicCategory.LIGHT:      {"100": 28.0, "75": 28.5, "50": 29.5, "25": 30.0},
    MetabolicCategory.MODERATE:   {"100": 25.0, "75": 26.0, "50": 27.0, "25": 29.0},
    MetabolicCategory.HEAVY:      {"100": None, "75": 24.0, "50": 25.5, "25": 28.0},
    MetabolicCategory.VERY_HEAVY: {"100": None, "75": None, "50": 24.5, "25": 27.0},
}


def _table(acclimatized: bool) -> dict[MetabolicCategory, dict[str, float | None]]:
    return WBGT_TLV if acclimatized else WBGT_AL


def _listed(cat: MetabolicCategory, acclimatized: bool) -> list[tuple[float, float]]:
    """(fraction, threshold) pairs with a non-null threshold, most-work first."""
    row = _table(acclimatized)[cat]
    return [(frac, row[key]) for frac, key in _ALLOCATIONS if row[key] is not None]


def work_fraction(wbgt_c: float, cat: MetabolicCategory, acclimatized: bool) -> tuple[float, float | None]:
    """Return ``(work_fraction, governing_threshold)`` for the conditions.

    Below the lowest listed threshold work is unrestricted (1.00). Above the
    25%-rest (most permissive) threshold -> 0.0 (STOP).
    """
    listed = _listed(cat, acclimatized)
    if cat is MetabolicCategory.REST:
        return 1.0, None
    min_thr = min(thr for _, thr in listed)
    if wbgt_c < min_thr:
        return 1.0, min_thr
    for frac, thr in listed:
        if wbgt_c <= thr:
            return frac, thr
    return 0.0, listed[-1][1]  # hotter than the 25% ceiling -> STOP


def work_rest_cycle(wbgt_c: float, cat: MetabolicCategory, acclimatized: bool) -> WorkRestCycle:
    frac, thr = work_fraction(wbgt_c, cat, acclimatized)
    work_min = round(frac * 60 / 5) * 5
    return WorkRestCycle(
        work_fraction=frac,
        work_min_per_hour=work_min,
        rest_min_per_hour=60 - work_min,
        threshold_wbgt_c=thr,
        table="TLV" if acclimatized else "AL",
    )


def risk_score(wbgt_c: float, cat: MetabolicCategory, acclimatized: bool) -> float:
    """Continuous 0-1 heat-stress score for the UI gauge (NOT the legal output).

    0 at/below the most-restrictive (lowest) screening threshold, 1 at/above the
    STOP threshold (the most permissive / highest listed WBGT).
    """
    if cat is MetabolicCategory.REST:
        cat = MetabolicCategory.LIGHT
    listed = _listed(cat, acclimatized)
    lo = min(thr for _, thr in listed)
    hi = max(thr for _, thr in listed)
    if hi <= lo:
        return 1.0 if wbgt_c >= hi else 0.0
    return max(0.0, min(1.0, (wbgt_c - lo) / (hi - lo)))


def met_for_category(cat: MetabolicCategory) -> float:
    """Metabolic rate in *met units* for the PHS model (1 met = 58.15 W/m^2)."""
    return cat.met
