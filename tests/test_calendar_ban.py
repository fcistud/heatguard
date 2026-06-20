from __future__ import annotations

from datetime import datetime, timedelta, timezone

from heatguard import calendar_ban as cb

TZ3 = timezone(timedelta(hours=3))
TZ4 = timezone(timedelta(hours=4))


def test_saudi_window():
    assert cb.is_banned("SA", datetime(2024, 7, 15, 13, 0, tzinfo=TZ3)) is True
    assert cb.is_banned("SA", datetime(2024, 7, 15, 9, 0, tzinfo=TZ3)) is False
    assert cb.is_banned("SA", datetime(2024, 7, 15, 11, 59, tzinfo=TZ3)) is False
    assert cb.is_banned("SA", datetime(2024, 7, 15, 12, 0, tzinfo=TZ3)) is True


def test_out_of_season_not_banned():
    # Dubai 51.6C event was in May, before the 15 Jun ban
    assert cb.is_banned("AE", datetime(2025, 5, 15, 13, 0, tzinfo=TZ4)) is False
    assert cb.is_banned("AE", datetime(2025, 6, 20, 13, 0, tzinfo=TZ4)) is True


def test_kuwait_widest_window():
    assert cb.is_banned("KW", datetime(2024, 6, 5, 11, 30, tzinfo=TZ3)) is True
    assert cb.is_banned("KW", datetime(2024, 6, 5, 16, 30, tzinfo=TZ3)) is False


def test_qatar_wbgt_cutoff():
    ts = datetime(2024, 7, 15, 9, 0, tzinfo=TZ3)  # 9am, outside the 10:00 window
    assert cb.is_banned("QA", ts, wbgt_c=33.0) is True   # WBGT cutoff overrides
    assert cb.is_banned("QA", ts, wbgt_c=30.0) is False


def test_unknown_country():
    assert cb.is_banned("US", datetime(2024, 7, 15, 13, 0, tzinfo=TZ3)) is False


def test_ban_window_today():
    assert cb.ban_window_today("SA", datetime(2024, 7, 15).date()) is not None
    assert cb.ban_window_today("SA", datetime(2024, 5, 15).date()) is None


def test_describe():
    assert "Saudi Arabia" in cb.describe("SA")
    assert "WBGT" in cb.describe("QA")
