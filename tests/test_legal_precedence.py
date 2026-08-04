"""Tests for legal precedence over scientific WRS signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from heatguard import calendar_ban
from heatguard.legal_precedence import (
    effective_advisory,
    effective_live,
    effective_signal,
    legal_status,
    operational_payload,
    precedence_applies,
)
from heatguard.scheduler import schedule
from heatguard.sites import get_site
from heatguard.types import MetabolicCategory, Signal, Weather, Worker

TZ4 = timezone(timedelta(hours=4))


def _scientific_work_advisory():
    """Cool banned-window hour — engine permits work; legal ban must override."""
    site = get_site("dubai")
    worker = Worker("v", days_on_job=120, acclimatized=True)
    weather = Weather(
        timestamp=datetime(2024, 7, 15, 13, 0, tzinfo=TZ4),
        tdb_c=26.0,
        rh_pct=40.0,
        wind_ms=2.0,
        shortwave_wm2=200.0,
        direct_wm2=150.0,
        dew_point_c=12.0,
        pressure_hpa=1000.0,
    )
    return schedule(weather, site, worker, MetabolicCategory.HEAVY)


def test_precedence_applies_when_banned_and_work_signal():
    adv = _scientific_work_advisory()
    assert adv.signal.value == "WORK"
    assert precedence_applies(True, adv) is True
    assert precedence_applies(False, adv) is False


def test_effective_signal_becomes_stop_during_ban():
    adv = _scientific_work_advisory()
    assert effective_signal(adv.signal, True, work_min_per_hour=adv.cycle.work_min_per_hour) is Signal.STOP


def test_effective_advisory_zeroes_work_cycle_during_ban():
    adv = _scientific_work_advisory()
    eff = effective_advisory(adv, True, calendar_ban.describe("AE"))
    assert eff.signal.value == "STOP"
    assert eff.cycle.work_min_per_hour == 0
    assert "Legal prohibition" in eff.rationale


def test_protective_scientific_stop_unchanged_when_banned():
    site = get_site("dubai")
    worker = Worker("v", days_on_job=120, acclimatized=True)
    weather = Weather(
        timestamp=datetime(2024, 7, 15, 13, 0, tzinfo=TZ4),
        tdb_c=48.0,
        rh_pct=30.0,
        wind_ms=1.0,
        shortwave_wm2=900.0,
        direct_wm2=700.0,
        dew_point_c=20.0,
        pressure_hpa=1000.0,
    )
    adv = schedule(weather, site, worker, MetabolicCategory.HEAVY)
    assert adv.signal.value == "STOP"
    eff = effective_advisory(adv, True, calendar_ban.describe("AE"))
    assert eff.signal.value == "STOP"
    assert precedence_applies(True, adv) is False


def test_effective_live_never_emits_work_during_ban():
    adv = _scientific_work_advisory()
    live = effective_live(adv, True, calendar_ban.describe("AE"))
    assert len(live) == 60
    assert "WORK" not in live


def test_operational_payload_exposes_both_advisories():
    adv = _scientific_work_advisory()
    payload = operational_payload(adv, country="AE")
    assert payload["scientific_advisory"]["signal"] == "WORK"
    assert payload["effective_advisory"]["signal"] == "STOP"
    assert payload["advisory"]["signal"] == "STOP"
    assert payload["legal"]["precedence_applied"] is True
    assert "WORK" not in payload["live"]


def test_legal_status_conflict_flag():
    adv = _scientific_work_advisory()
    status = legal_status("AE", adv.timestamp, adv.wbgt_c, adv)
    assert status["banned"] is True
    assert status["scientific_vs_legal_conflict"] is True
