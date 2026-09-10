"""Tests for legal precedence over scientific WRS signals."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

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
WORKER_LANES = ("veteran", "newcomer")


def _worker(kind: str) -> Worker:
    if kind == "veteran":
        return Worker("v", days_on_job=120, acclimatized=True)
    return Worker("n", days_on_job=0, acclimatized=False)


def _scientific_advisory(*, kind: str = "veteran", hour: int = 13, tdb_c: float = 26.0):
    """Cool July hour in Dubai — engine permits work; hour 13 is inside the AE ban."""
    site = get_site("dubai")
    weather = Weather(
        timestamp=datetime(2024, 7, 15, hour, 0, tzinfo=TZ4),
        tdb_c=tdb_c,
        rh_pct=40.0,
        wind_ms=2.0,
        shortwave_wm2=200.0,
        direct_wm2=150.0,
        dew_point_c=12.0,
        pressure_hpa=1000.0,
    )
    return schedule(weather, site, _worker(kind), MetabolicCategory.HEAVY)


def _scientific_work_advisory():
    return _scientific_advisory(kind="veteran", hour=13, tdb_c=26.0)


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


def test_rest_in_shade_preserved_during_ban_but_work_zeroed():
    """Protective REST_IN_SHADE stays; residual work minutes are removed."""
    from dataclasses import replace as dc_replace

    adv = _scientific_work_advisory()
    partial = dc_replace(
        adv,
        signal=Signal.REST_IN_SHADE,
        cycle=dc_replace(
            adv.cycle,
            work_fraction=0.25,
            work_min_per_hour=15,
            rest_min_per_hour=45,
        ),
    )
    assert precedence_applies(True, partial) is True
    eff = effective_advisory(partial, True, calendar_ban.describe("AE"))
    assert eff.signal is Signal.REST_IN_SHADE
    assert eff.cycle.work_min_per_hour == 0
    assert "WORK" not in effective_live(partial, True, calendar_ban.describe("AE"))


def test_effective_signal_preserves_protective_signals():
    assert effective_signal(Signal.REST_IN_SHADE, True, work_min_per_hour=15) is Signal.REST_IN_SHADE
    assert effective_signal(Signal.DRINK_NOW, True, work_min_per_hour=0) is Signal.DRINK_NOW
    assert effective_signal(Signal.WORK, True, work_min_per_hour=60) is Signal.STOP


def test_compliance_log_uses_effective_advisories_during_ban():
    from datetime import date

    from heatguard.service import compliance_for_day

    clog = compliance_for_day("riyadh", date(2024, 7, 15))
    noon = next(
        r for r in clog.records
        if r.payload.get("timestamp", "").startswith("2024-07-15T12:")
    )
    assert noon.payload["signal"] == "STOP"
    assert noon.payload["cycle"]["work_min_per_hour"] == 0
    assert "Legal prohibition" in noon.payload["rationale"]


def test_cli_decide_prints_operational_signal_during_ban(capsys, monkeypatch):
    """CLI decide must not present scientific WORK as the operational SIGNAL."""
    from argparse import Namespace
    from datetime import datetime, timedelta, timezone

    from heatguard import cli as cli_mod

    # Pin "now" inside UAE midday ban season so the test is calendar-stable.
    fixed = datetime(2024, 7, 15, 13, 0, tzinfo=timezone(timedelta(hours=4)))

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(cli_mod, "datetime", _FixedDateTime)

    args = Namespace(
        site="dubai",
        tdb=26.0,
        rh=40.0,
        wind=2.0,
        solar=200.0,
        hour=13,
        intensity="heavy",
        days_on_job=120,
        unacclimatized=False,
        experienced=False,
        measured_wbgt=None,
    )
    assert cli_mod.cmd_decide(args) == 0
    out = capsys.readouterr().out
    assert "SIGNAL (operational):" in out
    assert "STOP" in out
    assert "BANNED" in out
    assert "legal rules govern permission" in out


def test_legal_status_conflict_flag():
    adv = _scientific_work_advisory()
    status = legal_status("AE", adv.timestamp, adv.wbgt_c, adv)
    assert status["banned"] is True
    assert status["scientific_vs_legal_conflict"] is True


# ---- four-lane matrix (WO-014) ----------------------------------------------


def _assert_payload_scientific_immutable(payload: dict, scientific) -> None:
    sci = payload["scientific_advisory"]
    assert sci["signal"] == scientific.signal.value
    assert sci["cycle"]["work_min_per_hour"] == scientific.cycle.work_min_per_hour


@pytest.mark.parametrize("kind", WORKER_LANES)
@pytest.mark.parametrize(
    "hour,expect_banned",
    [(13, True), (8, False)],
)
def test_operational_payload_both_lanes_banned_and_permitted(
    kind: str, hour: int, expect_banned: bool
):
    adv = _scientific_advisory(kind=kind, hour=hour)
    assert adv.signal.value == "WORK"
    payload = operational_payload(adv, country="AE")
    _assert_payload_scientific_immutable(payload, adv)
    assert payload["legal"]["banned"] is expect_banned
    if expect_banned:
        assert payload["effective_advisory"]["signal"] != "WORK"
        assert payload["effective_advisory"]["cycle"]["work_min_per_hour"] == 0
        assert payload["advisory"]["signal"] == payload["effective_advisory"]["signal"]
        assert payload["legal"]["precedence_applied"] is True
        assert "WORK" not in payload["live"]
        assert adv.cycle.work_min_per_hour > 0
    else:
        assert payload["effective_advisory"]["signal"] == "WORK"
        assert payload["effective_advisory"]["cycle"]["work_min_per_hour"] == adv.cycle.work_min_per_hour
        assert payload["legal"]["precedence_applied"] is False


@pytest.mark.parametrize("kind", WORKER_LANES)
@pytest.mark.parametrize("protective", [Signal.REST_IN_SHADE, Signal.DRINK_NOW, Signal.STOP])
def test_protective_signals_and_hydration_survive_ban(kind: str, protective: Signal):
    from dataclasses import replace as dc_replace

    adv = _scientific_advisory(kind=kind, hour=13)
    if protective is Signal.STOP:
        partial = dc_replace(
            adv,
            signal=Signal.STOP,
            cycle=dc_replace(
                adv.cycle,
                work_fraction=0.0,
                work_min_per_hour=0,
                rest_min_per_hour=60,
            ),
        )
        assert precedence_applies(True, partial) is False
    else:
        partial = dc_replace(
            adv,
            signal=protective,
            cycle=dc_replace(
                adv.cycle,
                work_fraction=0.25,
                work_min_per_hour=15,
                rest_min_per_hour=45,
            ),
        )
        assert precedence_applies(True, partial) is True
    payload = operational_payload(partial, country="AE")
    _assert_payload_scientific_immutable(payload, partial)
    assert payload["effective_advisory"]["signal"] == protective.value
    sci_water = payload["scientific_advisory"]["hydration"]["water_ml_per_h"]
    assert payload["effective_advisory"]["hydration"]["water_ml_per_h"] == sci_water
    if protective is Signal.STOP:
        assert payload["legal"]["precedence_applied"] is False
        assert payload["effective_advisory"]["cycle"]["work_min_per_hour"] == 0
    else:
        assert payload["effective_advisory"]["cycle"]["work_min_per_hour"] == 0
        assert payload["legal"]["precedence_applied"] is True
        assert partial.cycle.work_min_per_hour == 15


@pytest.mark.parametrize("kind", WORKER_LANES)
def test_precedence_applied_polarity_both_lanes(kind: str):
    work = _scientific_advisory(kind=kind, hour=13, tdb_c=26.0)
    payload_work = operational_payload(work, country="AE")
    assert payload_work["legal"]["banned"] is True
    assert payload_work["scientific_advisory"]["signal"] == "WORK"
    assert payload_work["legal"]["precedence_applied"] is True

    stop = _scientific_advisory(kind=kind, hour=13, tdb_c=48.0)
    payload_stop = operational_payload(stop, country="AE")
    assert payload_stop["legal"]["banned"] is True
    assert payload_stop["scientific_advisory"]["signal"] == "STOP"
    assert payload_stop["legal"]["precedence_applied"] is False
    assert payload_stop["effective_advisory"]["signal"] == "STOP"


def assert_four_timeline_lanes(row: dict) -> None:
    from heatguard.contracts import LEGAL_CONTRACT_INVENTORY

    for lane in LEGAL_CONTRACT_INVENTORY.timeline_lanes:
        assert lane in row, f"missing lane {lane}"


def assert_banned_effective_non_authorizing(row: dict) -> None:
    """Effective lanes never authorize work during a ban; scientific lanes stay put."""
    assert_four_timeline_lanes(row)
    assert row["legal"]["banned"] is True
    for sci_key, eff_key in (("veteran", "veteran_effective"), ("newcomer", "newcomer_effective")):
        sci = row[sci_key]
        eff = row[eff_key]
        assert eff["signal"] != "WORK", eff_key
        assert eff["cycle"]["work_min_per_hour"] == 0, eff_key
        if sci["signal"] == "WORK":
            assert sci["cycle"]["work_min_per_hour"] > 0, sci_key
            assert row["legal"]["precedence_applied"] is True
        if sci["signal"] in {"REST_IN_SHADE", "DRINK_NOW", "STOP"}:
            assert eff["signal"] == sci["signal"], eff_key
            assert (
                eff["hydration"]["water_ml_per_h"] == sci["hydration"]["water_ml_per_h"]
            )


def test_negative_control_drop_newcomer_effective():
    row = {
        "veteran": {"signal": "WORK", "cycle": {"work_min_per_hour": 45}, "hydration": {"water_ml_per_h": 1}},
        "newcomer": {"signal": "STOP", "cycle": {"work_min_per_hour": 0}, "hydration": {"water_ml_per_h": 1}},
        "veteran_effective": {"signal": "STOP", "cycle": {"work_min_per_hour": 0}, "hydration": {"water_ml_per_h": 1}},
        "legal": {"banned": True, "precedence_applied": True},
    }
    mutated = copy.deepcopy(row)
    with pytest.raises(AssertionError):
        assert_banned_effective_non_authorizing(mutated)


def test_negative_control_collapse_effective_into_scientific():
    row = {
        "veteran": {"signal": "WORK", "cycle": {"work_min_per_hour": 45}, "hydration": {"water_ml_per_h": 1}},
        "newcomer": {"signal": "WORK", "cycle": {"work_min_per_hour": 30}, "hydration": {"water_ml_per_h": 1}},
        "veteran_effective": {"signal": "STOP", "cycle": {"work_min_per_hour": 0}, "hydration": {"water_ml_per_h": 1}},
        "newcomer_effective": {"signal": "STOP", "cycle": {"work_min_per_hour": 0}, "hydration": {"water_ml_per_h": 1}},
        "legal": {"banned": True, "precedence_applied": True},
    }
    mutated = copy.deepcopy(row)
    mutated["veteran_effective"] = copy.deepcopy(mutated["veteran"])
    with pytest.raises(AssertionError):
        assert_banned_effective_non_authorizing(mutated)
