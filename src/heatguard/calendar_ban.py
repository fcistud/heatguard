"""GCC calendar-based midday work bans — the foil HeatGuard improves on.

Every Gulf state bans midday outdoor work on a fixed calendar window. The window
ignores actual conditions, work intensity, and acclimatization, and only Qatar
adds a (too-high) WBGT trigger. Comparing "what the calendar bans" with "what
HeatGuard calls" is the heart of the demo.

Specs (from the brief):
  SA  12:00-15:00, 15 Jun - 15 Sep
  AE  12:30-15:00, 15 Jun - 15 Sep   (fine: AED 5,000/worker, up to AED 50,000)
  KW  11:00-16:00, 01 Jun - 31 Aug   (widest window)
  OM  12:30-15:30, 01 Jun - 31 Aug
  BH  12:00-16:00, 15 Jun - 31 Aug
  QA  10:00-15:30, 01 Jun - 15 Sep   + WBGT > 32.1 degC cutoff (only WBGT rule)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True, slots=True)
class BanRule:
    country: str
    name: str
    season_start: tuple[int, int]   # (month, day)
    season_end: tuple[int, int]
    daily_start: time
    daily_end: time
    wbgt_cutoff_c: float | None = None
    fine_note: str | None = None


GCC_BANS: dict[str, BanRule] = {
    "SA": BanRule("SA", "Saudi Arabia", (6, 15), (9, 15), time(12, 0), time(15, 0)),
    "AE": BanRule("AE", "UAE", (6, 15), (9, 15), time(12, 30), time(15, 0),
                  fine_note="AED 5,000 per worker, up to AED 50,000"),
    "KW": BanRule("KW", "Kuwait", (6, 1), (8, 31), time(11, 0), time(16, 0)),
    "OM": BanRule("OM", "Oman", (6, 1), (8, 31), time(12, 30), time(15, 30)),
    "BH": BanRule("BH", "Bahrain", (6, 15), (8, 31), time(12, 0), time(16, 0)),
    "QA": BanRule("QA", "Qatar", (6, 1), (9, 15), time(10, 0), time(15, 30), wbgt_cutoff_c=32.1),
}


def _in_season(rule: BanRule, d: date) -> bool:
    md = (d.month, d.day)
    return rule.season_start <= md <= rule.season_end


def ban_window_today(country: str, d: date) -> tuple[time, time] | None:
    """Return today's banned (start, end) window, or None if out of season."""
    rule = GCC_BANS.get(country)
    if rule is None or not _in_season(rule, d):
        return None
    return rule.daily_start, rule.daily_end


def is_banned(country: str, ts: datetime, wbgt_c: float | None = None) -> bool:
    """Whether the calendar ban prohibits outdoor work at this instant.

    Qatar's WBGT cutoff (>32.1 degC) applies as a condition-based override.
    """
    rule = GCC_BANS.get(country)
    if rule is None:
        return False
    if rule.wbgt_cutoff_c is not None and wbgt_c is not None and wbgt_c > rule.wbgt_cutoff_c:
        return True
    if not _in_season(rule, ts.date()):
        return False
    return rule.daily_start <= ts.time() <= rule.daily_end


def describe(country: str) -> str:
    rule = GCC_BANS.get(country)
    if rule is None:
        return f"No calendar ban on record for {country}."
    s, e = rule.season_start, rule.season_end
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    win = f"{rule.daily_start:%H:%M}-{rule.daily_end:%H:%M}"
    season = f"{s[1]} {months[s[0]]} - {e[1]} {months[e[0]]}"
    extra = f"; WBGT cutoff {rule.wbgt_cutoff_c} degC" if rule.wbgt_cutoff_c else ""
    return f"{rule.name}: {win}, {season}{extra}"
