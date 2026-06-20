"""End-to-end tests for the FastAPI surface (and, through it, the service layer).

Requires the committed demo cache (data/cache/*.json). Skipped if fastapi isn't
installed so the core test run still works with only the engine deps.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from heatguard.api import app  # noqa: E402
from heatguard.types import Signal  # noqa: E402

client = TestClient(app)
SIGNALS = {s.value for s in Signal}


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_sites_and_demos():
    sites = client.get("/sites").json()
    assert len(sites) >= 2 and all("ban" in s for s in sites)
    assert set(client.get("/demos").json()) == {"dubai", "riyadh"}


@pytest.mark.parametrize("site", ["dubai", "riyadh"])
def test_demo_payload_shape(site):
    d = client.get(f"/demo/{site}").json()
    for key in ("site", "timeline", "impact", "economics", "sensitivity", "compliance"):
        assert key in d, f"missing {key}"
    assert d["compliance"]["summary"]["verified"] is True
    assert d["impact"]["danger_hours_caught_vs_ban"] >= 0
    assert d["economics"]["roi_multiple_lo"] > 0
    assert len(d["sensitivity"]) == 5


def test_demo_unknown_site_404():
    assert client.get("/demo/atlantis").status_code == 404


def test_timeline_bad_date_400():
    assert client.get("/timeline/riyadh/not-a-date").status_code == 400


def test_economics_and_backtest():
    assert client.get("/economics/dubai").json()["payback_days"] > 0
    assert client.get("/backtest").json()["passed"] is True


def test_compliance_export_csv():
    r = client.get("/compliance/dubai/export?fmt=csv")
    assert r.status_code == 200 and "record_hash" in r.text.splitlines()[0]


def test_decide_valid():
    r = client.post("/decide", json={"site_key": "riyadh", "tdb": 45, "rh": 18, "hour": 12, "intensity": "heavy"}).json()
    assert r["advisory"]["signal"] in SIGNALS
    assert isinstance(r["live"], list) and len(r["live"]) == 60


def test_decide_hour_out_of_range_is_422():
    r = client.post("/decide", json={"site_key": "riyadh", "tdb": 40, "rh": 20, "hour": 99, "intensity": "heavy"})
    assert r.status_code == 422  # validated, not a 500 crash


def test_decide_unknown_site_404():
    r = client.post("/decide", json={"site_key": "atlantis", "tdb": 40, "rh": 20, "hour": 12, "intensity": "heavy"})
    assert r.status_code == 404


def test_decide_bad_intensity_400():
    r = client.post("/decide", json={"site_key": "riyadh", "tdb": 40, "rh": 20, "hour": 12, "intensity": "sprint"})
    assert r.status_code == 400


def test_extreme_humidity_day_emits_strict_json():
    # Riyadh early-June hours push PHS out of its envelope -> NaN core temp internally.
    # The API must still emit strictly-valid JSON (no bare NaN token).
    txt = client.get("/timeline/riyadh/2024-06-07").text
    assert "NaN" not in txt
    json.loads(txt)  # must not raise


# ---- per-worker intensity & acclimatization ---------------------------------
def _noon_work(tl):
    return [r for r in tl["rows"] if r["hour"] == 12][0]["veteran"]["cycle"]["work_min_per_hour"]


def test_timeline_intensity_individualizes_schedule():
    light = client.get("/timeline/riyadh/2024-07-15?intensity=light").json()
    heavy = client.get("/timeline/riyadh/2024-07-15?intensity=heavy").json()
    assert light["intensity"] == "light"
    assert _noon_work(light) >= _noon_work(heavy)  # lighter work -> more minutes permitted


def test_timeline_newcomer_days_relaxes_cap():
    def nine_cap(tl):
        return [r for r in tl["rows"] if r["hour"] == 9][0]["newcomer"]["acclim_fraction"]

    d0 = client.get("/timeline/riyadh/2024-07-15?newcomer_days=0").json()
    d5 = client.get("/timeline/riyadh/2024-07-15?newcomer_days=5").json()
    assert nine_cap(d0) == 0.2 and nine_cap(d5) == 1.0


def test_timeline_bad_intensity_400():
    assert client.get("/timeline/riyadh/2024-07-15?intensity=sprint").status_code == 400


# ---- measured WBGT (sensor vs estimate) -------------------------------------
def test_hour_estimated_vs_measured():
    est = client.get("/hour/dubai/2025-05-16/12").json()
    assert est["measured"] is False and est["advisory"]["wbgt_source"] == "liljegren"
    assert isinstance(est["estimated_wbgt_c"], (int, float))
    assert len(est["live"]) == 60

    meas = client.get("/hour/dubai/2025-05-16/12?measured_wbgt=33.5").json()
    assert meas["measured"] is True
    assert meas["advisory"]["wbgt_source"] == "measured"
    assert meas["advisory"]["wbgt_c"] == 33.5
    assert "estimated_wbgt_c" in meas  # both shown for comparison


def test_hour_measured_out_of_range_422():
    assert client.get("/hour/dubai/2025-05-16/12?measured_wbgt=99").status_code == 422


def test_hour_no_weather_404():
    assert client.get("/hour/dubai/1999-01-01/12").status_code == 404


# ---- scale / lives-saved projection -----------------------------------------
def test_scale_projection():
    r = client.get("/scale/dubai?workforce=100000").json()
    p = r["projection"]
    assert p["workforce"] == 100000
    assert p["aki_cases_averted"] > 0 and p["lives_saved"] > 0
    assert p["value_usd_hi"] >= p["value_usd_lo"] > 0
    assert "presets" in r
    assert r["context"]["arab_states_migrant_workers"] > 0


def test_scale_scales_with_workforce():
    a = client.get("/scale/dubai?workforce=1000").json()["projection"]
    b = client.get("/scale/dubai?workforce=10000").json()["projection"]
    assert b["aki_cases_averted"] > a["aki_cases_averted"] * 8  # ~10x


# ---- compliance reframe (worker-protective + privacy) -----------------------
def test_compliance_summary_has_privacy_block():
    s = client.get("/demo/dubai").json()["compliance"]["summary"]
    assert "purpose" in s
    assert "privacy" in s and "does_not_record" in s["privacy"]
