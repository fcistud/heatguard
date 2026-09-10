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
    """Deprecated /health alias keeps unconditional 200 (WO-012 characterization)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "python" in body
    assert body["python"]["major"] == 3
    assert body["python"]["minor"] >= 12


def test_health_trailing_slash_still_ok():
    resp = client.get("/health/", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_sites_and_demos():
    sites = client.get("/sites").json()
    assert len(sites) >= 2 and all("ban" in s for s in sites)
    assert set(client.get("/demos").json()) == {"dubai", "riyadh", "abu_dhabi", "doha"}


@pytest.mark.parametrize("site", ["dubai", "riyadh", "abu_dhabi", "doha"])
def test_demo_payload_shape(site):
    d = client.get(f"/demo/{site}").json()
    for key in ("site", "timeline", "impact", "economics", "sensitivity", "compliance"):
        assert key in d, f"missing {key}"
    assert d["compliance"]["summary"]["verified"] is True
    assert d["impact"]["danger_hours_caught_vs_ban"] >= 0
    assert d["economics"]["roi_multiple_lo"] > 0
    assert len(d["sensitivity"]) == 5


def test_demo_dubai_gap_hours():
    d = client.get("/demo/dubai?crew=100").json()
    assert d["timeline"]["gap_hours"] > 0
    assert d["impact"]["danger_hours_caught_vs_ban"] > 0


def test_timeline_dubai_focus_day():
    focus = client.get("/demo/dubai").json()["focus_day"]
    tl = client.get(f"/timeline/dubai/{focus}").json()
    assert tl["gap_hours"] > 0


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


def test_decide_hot_conditions_personal_risk():
    r = client.post(
        "/decide",
        json={
            "site_key": "dubai",
            "tdb": 44.0,
            "rh": 35.0,
            "wind": 2.0,
            "solar": 850.0,
            "hour": 12,
            "intensity": "heavy",
            "days_on_job": 0,
            "acclimatized": False,
            "experienced": False,
            "measured_wbgt": None,
            "weight_kg": 90.0,
            "height_m": 1.75,
            "age": 52,
            "has_comorbidity": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["advisory"]["signal"] in SIGNALS
    assert "personal_risk_score" in body["advisory"]
    assert len(body["live"]) == 60


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


def test_hour_legal_precedence_blocks_work_during_ban():
    """Operational advisory must not authorize work when calendar ban is active."""
    r = client.get("/hour/riyadh/2024-07-15/12").json()
    assert r["legal"]["banned"] is True
    assert r["scientific_advisory"]["signal"] == "WORK"
    assert r["effective_advisory"]["signal"] == "STOP"
    assert r["advisory"]["signal"] == "STOP"
    assert r["legal"]["precedence_applied"] is True
    assert "WORK" not in r["live"]


def test_timeline_includes_effective_lanes():
    from test_legal_precedence import assert_banned_effective_non_authorizing

    tl = client.get("/timeline/riyadh/2024-07-15").json()
    banned_work = next(
        r for r in tl["rows"] if r["banned"] and r["veteran"]["signal"] == "WORK"
    )
    assert banned_work["veteran_effective"]["signal"] == "STOP"
    assert banned_work["newcomer_effective"]["signal"] != "WORK"
    assert banned_work["legal"]["precedence_applied"] is True
    assert_banned_effective_non_authorizing(banned_work)


def test_timeline_every_row_has_four_lanes_two_jurisdictions():
    """SA 12:00-15:00 vs AE 12:30-15:00 — every row carries all four lanes."""
    from heatguard.contracts import LEGAL_CONTRACT_INVENTORY
    from test_legal_precedence import (
        assert_banned_effective_non_authorizing,
        assert_four_timeline_lanes,
    )

    cases = (
        ("/timeline/riyadh/2024-07-15", {12, 13, 14, 15}),
        ("/timeline/dubai/2025-07-15", {13, 14, 15}),
    )
    for path, banned_hours in cases:
        tl = client.get(path)
        assert tl.status_code == 200, path
        body = tl.json()
        assert body["rows"], path
        seen_banned: set[int] = set()
        for row in body["rows"]:
            assert_four_timeline_lanes(row)
            for lane in LEGAL_CONTRACT_INVENTORY.timeline_lanes:
                assert row[lane]["signal"]
            if row["legal"]["banned"]:
                seen_banned.add(row["hour"])
                assert_banned_effective_non_authorizing(row)
        assert seen_banned == banned_hours, (path, seen_banned)


def test_hour_four_lane_invariants_two_jurisdictions():
    # Distinct windows: SA first/last 12 and 15; AE on-the-hour first/last 13 and 15.
    specs = (
        ("riyadh", "2024-07-15", 12, True),
        ("riyadh", "2024-07-15", 15, True),
        ("riyadh", "2024-07-15", 11, False),
        ("riyadh", "2024-07-15", 8, False),
        ("dubai", "2025-07-15", 13, True),
        ("dubai", "2025-07-15", 15, True),
        ("dubai", "2025-07-15", 12, False),
    )
    for site, day, hour, expect_banned in specs:
        for worker in ("veteran", "newcomer"):
            r = client.get(f"/hour/{site}/{day}/{hour}?worker={worker}")
            assert r.status_code == 200, (site, day, hour, worker)
            body = r.json()
            assert body["legal"]["banned"] is expect_banned
            sci = body["scientific_advisory"]
            eff = body["effective_advisory"]
            if expect_banned:
                assert eff["signal"] != "WORK"
                assert eff["cycle"]["work_min_per_hour"] == 0
                if sci["signal"] == "WORK":
                    assert sci["cycle"]["work_min_per_hour"] > 0
                    assert body["legal"]["precedence_applied"] is True
                else:
                    assert eff["signal"] == sci["signal"]
                    assert (
                        eff["hydration"]["water_ml_per_h"]
                        == sci["hydration"]["water_ml_per_h"]
                    )
                    if sci["cycle"]["work_min_per_hour"] == 0:
                        assert body["legal"]["precedence_applied"] is False
            else:
                assert eff["signal"] == sci["signal"]
                assert eff["cycle"]["work_min_per_hour"] == sci["cycle"]["work_min_per_hour"]
                assert body["legal"]["precedence_applied"] is False


def test_timeline_out_of_season_effective_matches_scientific():
    from test_legal_precedence import assert_four_timeline_lanes

    tl = client.get("/timeline/dubai/2025-05-16").json()
    assert tl["rows"]
    for row in tl["rows"]:
        assert_four_timeline_lanes(row)
        assert row["legal"]["banned"] is False
        assert row["legal"]["precedence_applied"] is False
        assert row["veteran_effective"]["signal"] == row["veteran"]["signal"]
        assert row["newcomer_effective"]["signal"] == row["newcomer"]["signal"]


def test_timeline_gap_hours_still_have_four_lanes():
    from test_legal_precedence import assert_four_timeline_lanes

    focus = client.get("/demo/dubai").json()["focus_day"]
    tl = client.get(f"/timeline/dubai/{focus}").json()
    gaps = [r for r in tl["rows"] if r["gap"]]
    assert gaps, "dubai focus day must include gap hours"
    for row in gaps:
        assert_four_timeline_lanes(row)
        assert row["legal"]["banned"] is False
        assert row["veteran_effective"]["signal"] == row["veteran"]["signal"]
        assert row["newcomer_effective"]["signal"] == row["newcomer"]["signal"]


def test_hour_protective_rest_survives_riyadh_ban():
    """Riyadh hours 13–14: veteran REST_IN_SHADE inside the SA window."""
    for hour in (13, 14):
        r = client.get(f"/hour/riyadh/2024-07-15/{hour}?worker=veteran")
        assert r.status_code == 200, hour
        body = r.json()
        sci = body["scientific_advisory"]
        eff = body["effective_advisory"]
        assert body["legal"]["banned"] is True
        assert sci["signal"] == "REST_IN_SHADE"
        assert sci["cycle"]["work_min_per_hour"] > 0
        assert eff["signal"] == "REST_IN_SHADE"
        assert eff["cycle"]["work_min_per_hour"] == 0
        assert eff["hydration"]["water_ml_per_h"] == sci["hydration"]["water_ml_per_h"]
        assert body["legal"]["precedence_applied"] is True


def test_legal_lanes_banned_fixture_is_canonical():
    from heatguard import canonical
    from heatguard._paths import _REPO_ROOT
    from heatguard.contracts import LEGAL_CONTRACT_INVENTORY

    path = _REPO_ROOT / "web" / "src" / "test" / "fixtures" / "legal_lanes_banned.json"
    loaded = canonical.load(path)
    assert path.read_bytes() == canonical.dumps(loaded).encode("utf-8") + b"\n"
    for lane in LEGAL_CONTRACT_INVENTORY.timeline_lanes:
        assert lane in loaded
    assert loaded["legal"]["banned"] is True
    from test_legal_precedence import assert_banned_effective_non_authorizing

    assert_banned_effective_non_authorizing(loaded)


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


# ---- datasets, forecast, policy retrieval -----------------------------------------
def test_policy_query():
    r = client.post(
        "/policy/query",
        json={"question": "When does the UAE midday ban start?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sources"]
    assert "policy corpus" in body["answer"].lower()


def test_policy_demo_questions():
    r = client.get("/policy/demo-questions")
    assert r.status_code == 200
    assert len(r.json()) >= 3


def test_forecast_dubai():
    r = client.get("/forecast/dubai")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "open-meteo-forecast"
    assert len(data["rows"]) >= 1


def test_datasets_inventory():
    r = client.get("/datasets")
    assert r.status_code == 200
    inv = r.json()
    assert inv["weather"]["archive_total"] >= 7
    assert inv["policy"]["file_count"] >= 4


# --- CORS allowlist (WO-001) -------------------------------------------------


def test_cors_allowed_origin_echoed():
    origin = "http://localhost:5173"
    r = client.get("/health", headers={"Origin": origin})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin
    assert r.headers.get("access-control-allow-origin") != "*"


def test_cors_denied_origin_has_no_allow_origin_header():
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") is None


def test_cors_preflight_allowed_origin():
    origin = "http://localhost:5173"
    r = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == origin
    allow_methods = r.headers.get("access-control-allow-methods", "")
    assert "GET" in allow_methods.upper()
    assert "*" not in allow_methods


def test_cors_preflight_unlisted_method_refused():
    origin = "http://localhost:5173"
    r = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PUT",
        },
    )
    # Starlette CORSMiddleware refuses disallowed methods with 400.
    assert r.status_code == 400
    allow_methods = r.headers.get("access-control-allow-methods", "").upper()
    assert "PUT" not in allow_methods
    # Request is not admitted as a successful preflight (no 2xx).
    assert not (200 <= r.status_code < 300)


def test_cors_no_origin_header_unaffected():
    """Server-to-server / curl callers without Origin must not be CORS-rejected."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_route_table_coverage_gate() -> None:
    """Enumerate app.routes against the production enforcement classifier (WO-006)."""
    from pathlib import Path

    from route_coverage_gate import (
        collect_live_route_entries,
        coverage_report,
        format_coverage_failure,
        report_is_clean,
    )

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "route_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    live = collect_live_route_entries(app)
    report = coverage_report(live, fixture)
    if not report_is_clean(report):
        raise AssertionError(format_coverage_failure(report))


def test_register_cors_boot_fails_on_production_wildcard():
    from fastapi import FastAPI

    from heatguard.api import register_cors_middleware
    from heatguard.boundary.cors_config import ConfigurationError

    tiny = FastAPI()
    with pytest.raises(ConfigurationError) as excinfo:
        register_cors_middleware(
            tiny,
            {
                "HEATGUARD_ENV": "production",
                "HEATGUARD_CORS_ORIGINS": "*",
            },
        )
    msg = str(excinfo.value)
    assert "HEATGUARD_CORS_ORIGINS" in msg
    assert "HEATGUARD_CORS_ALLOW_WILDCARD" in msg
