"""Vendored solar geometry — cosine of the solar zenith angle.

Liljegren's outdoor-WBGT model needs the cosine of the solar zenith angle, and
recent ``thermofeel`` no longer ships one (it defers to the heavy
``earthkit-meteo``). This ~50-line NOAA implementation removes that dependency.
Accuracy is well within what WBGT estimation needs (sub-degree on the zenith).

Reference: NOAA Solar Calculator equations
(https://gml.noaa.gov/grad/solcalc/solareqns.PDF).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone


def _julian_day(dt_utc: datetime) -> float:
    """Julian Date (including the time-of-day fraction) for a UTC datetime."""
    y, m = dt_utc.year, dt_utc.month
    d = dt_utc.day
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = (
        math.floor(365.25 * (y + 4716))
        + math.floor(30.6001 * (m + 1))
        + d
        + b
        - 1524.5
    )
    frac = (dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600) / 24.0
    return jd + frac


def cos_solar_zenith_angle(ts: datetime, lat: float, lon: float) -> float:
    """Cosine of the solar zenith angle in [-1, 1] (negative = sun below horizon).

    ``ts`` must be timezone-aware; it is converted to UTC internally.
    """
    if ts.tzinfo is None:
        raise ValueError("cos_solar_zenith_angle requires a timezone-aware datetime")
    dt_utc = ts.astimezone(timezone.utc)

    jd = _julian_day(dt_utc)
    t = (jd - 2451545.0) / 36525.0  # Julian centuries since J2000.0

    # Geometric mean longitude & anomaly of the sun (degrees).
    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360.0
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    m_rad = math.radians(m)

    # Sun's equation of centre and true/apparent longitude.
    c = (
        math.sin(m_rad) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * m_rad) * (0.019993 - 0.000101 * t)
        + math.sin(3 * m_rad) * 0.000289
    )
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    # Obliquity of the ecliptic and solar declination.
    eps0 = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(app_long)))

    # Equation of time (minutes).
    y = math.tan(math.radians(eps / 2.0)) ** 2
    l0_rad = math.radians(l0)
    eot = 4.0 * math.degrees(
        y * math.sin(2 * l0_rad)
        - 2 * e * math.sin(m_rad)
        + 4 * e * y * math.sin(m_rad) * math.cos(2 * l0_rad)
        - 0.5 * y * y * math.sin(4 * l0_rad)
        - 1.25 * e * e * math.sin(2 * m_rad)
    )

    # True solar time (minutes) at this longitude, then the hour angle (degrees).
    utc_minutes = dt_utc.hour * 60 + dt_utc.minute + dt_utc.second / 60.0
    tst = (utc_minutes + eot + 4.0 * lon) % 1440.0
    hour_angle = tst / 4.0 - 180.0

    lat_rad = math.radians(lat)
    cossza = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(
        math.radians(hour_angle)
    )
    return max(-1.0, min(1.0, cossza))


def solar_zenith_deg(ts: datetime, lat: float, lon: float) -> float:
    """Solar zenith angle in degrees (0 = sun overhead, 90 = horizon)."""
    return math.degrees(math.acos(cos_solar_zenith_angle(ts, lat, lon)))


def solar_elevation_deg(ts: datetime, lat: float, lon: float) -> float:
    return 90.0 - solar_zenith_deg(ts, lat, lon)
