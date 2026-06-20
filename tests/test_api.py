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
