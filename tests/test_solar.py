from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from heatguard.solar import cos_solar_zenith_angle, solar_elevation_deg

TZ3 = timezone(timedelta(hours=3))


def test_requires_tzaware():
    with pytest.raises(ValueError):
        cos_solar_zenith_angle(datetime(2024, 7, 15, 12, 0), 24.7, 46.7)


def test_high_at_summer_solar_noon_riyadh():
    # ~solar noon (local ~12:00) mid-summer in Riyadh -> sun nearly overhead
    elev = solar_elevation_deg(datetime(2024, 6, 21, 12, 0, tzinfo=TZ3), 24.7136, 46.6753)
    assert elev > 80.0


def test_negative_at_local_midnight():
    cz = cos_solar_zenith_angle(datetime(2024, 7, 15, 0, 0, tzinfo=TZ3), 24.7136, 46.6753)
    assert cz < 0.0


def test_sunrise_low_elevation():
    elev = solar_elevation_deg(datetime(2024, 7, 15, 6, 0, tzinfo=TZ3), 24.7136, 46.6753)
    assert -5.0 < elev < 25.0


def test_cossza_bounded():
    for h in range(24):
        cz = cos_solar_zenith_angle(datetime(2024, 7, 15, h, 0, tzinfo=TZ3), 24.7136, 46.6753)
        assert -1.0 <= cz <= 1.0
