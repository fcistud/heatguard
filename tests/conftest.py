from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from heatguard.types import Site, Weather, Worker

TZ3 = timezone(timedelta(hours=3))
TZ4 = timezone(timedelta(hours=4))


@pytest.fixture
def riyadh() -> Site:
    return Site("Riyadh", 24.7136, 46.6753, 612, "Asia/Riyadh", "SA")


@pytest.fixture
def dubai() -> Site:
    return Site("Dubai", 25.2048, 55.2708, 5, "Asia/Dubai", "AE")


def weather(hour, tdb, rh, wind=2.0, sw=0.0, direct=0.0, *, day=15, month=7, year=2024, tz=TZ3):
    return Weather(
        timestamp=datetime(year, month, day, hour, 0, tzinfo=tz),
        tdb_c=tdb, rh_pct=rh, wind_ms=wind,
        shortwave_wm2=sw, direct_wm2=direct, dew_point_c=tdb - 15, pressure_hpa=1004.0,
    )


@pytest.fixture
def veteran() -> Worker:
    return Worker("vet-1", days_on_job=120, acclimatized=True)


@pytest.fixture
def newcomer() -> Worker:
    return Worker("new-1", days_on_job=0, acclimatized=False)
