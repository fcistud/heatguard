"""Legal precedence over scientific WRS signals (normative: docs/SCOPE_GUARDRAIL.md).

Calendar and condition-based GCC rules govern **permission to work**. The scheduler
output remains the scientific assessment; this module derives the operational
``effective`` advisory that must never authorize outdoor work during active bans.
"""
from __future__ import annotations

from dataclasses import replace

from . import calendar_ban
from .scheduler import live_signal
from .types import Advisory, Signal, WorkRestCycle


_LEGAL_STOP_RATIONALE = (
    "Legal prohibition in effect — do not work outdoors. "
    "Scientific assessment is shown for comparison only."
)


def legal_status(
    country: str,
    timestamp,
    wbgt_c: float,
    scientific: Advisory,
) -> dict:
    """Legal metadata for API/UI consumers."""
    banned = calendar_ban.is_banned(country, timestamp, wbgt_c)
    conflict = precedence_applies(banned, scientific)
    return {
        "banned": banned,
        "description": calendar_ban.describe(country),
        "precedence_applied": conflict,
        "scientific_vs_legal_conflict": conflict,
    }


def precedence_applies(banned: bool, scientific: Advisory) -> bool:
    """True when legal rules override a work-authorizing scientific outcome."""
    if not banned:
        return False
    return scientific.signal is Signal.WORK or scientific.cycle.work_min_per_hour > 0


def effective_signal(scientific: Signal, banned: bool, *, work_min_per_hour: int = 0) -> Signal:
    """Operational broadcast signal after legal gating."""
    if not banned:
        return scientific
    if scientific is Signal.WORK or work_min_per_hour > 0:
        return Signal.STOP
    return scientific


def effective_advisory(scientific: Advisory, banned: bool, ban_description: str) -> Advisory:
    """Operational advisory — never work-authorizing during active legal bans."""
    if not precedence_applies(banned, scientific):
        return scientific

    rationale = _LEGAL_STOP_RATIONALE
    if ban_description:
        rationale = f"{rationale} ({ban_description})"

    return replace(
        scientific,
        signal=Signal.STOP,
        cycle=WorkRestCycle(
            work_fraction=0.0,
            work_min_per_hour=0,
            rest_min_per_hour=60,
            threshold_wbgt_c=scientific.cycle.threshold_wbgt_c,
            table=scientific.cycle.table,
            capped_by_acclimatization=False,
        ),
        rationale=rationale,
    )


def effective_live(scientific: Advisory, banned: bool, ban_description: str) -> list[str]:
    """Minute-by-minute operational signals for the selected hour."""
    eff = effective_advisory(scientific, banned, ban_description)
    return [live_signal(eff, m).value for m in range(60)]


def operational_payload(
    scientific: Advisory,
    *,
    country: str,
    ban_description: str | None = None,
) -> dict:
    """Scientific + effective advisories and legal metadata for API responses."""
    desc = ban_description if ban_description is not None else calendar_ban.describe(country)
    banned = calendar_ban.is_banned(country, scientific.timestamp, scientific.wbgt_c)
    effective = effective_advisory(scientific, banned, desc)
    legal = legal_status(country, scientific.timestamp, scientific.wbgt_c, scientific)
    return {
        "scientific_advisory": scientific.to_dict(),
        "effective_advisory": effective.to_dict(),
        "advisory": effective.to_dict(),
        "legal": legal,
        "live": effective_live(scientific, banned, desc),
        "scientific_live": [live_signal(scientific, m).value for m in range(60)],
    }
