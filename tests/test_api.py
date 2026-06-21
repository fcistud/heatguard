"""FastAPI smoke tests — offline, uses committed demo weather cache."""
from __future__ import annotations

from fastapi.testclient import TestClient

from heatguard.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_demos_list():
    r = client.get("/demos")
    assert r.status_code == 200
    demos = r.json()
    assert "dubai" in demos
    assert "riyadh" in demos


def test_demo_dubai_payload():
    r = client.get("/demo/dubai?crew=100")
    assert r.status_code == 200
    data = r.json()
    assert data["site"]["key"] == "dubai"
    assert data["timeline"]["gap_hours"] > 0
    assert data["impact"]["danger_hours_caught_vs_ban"] > 0
    assert "economics" in data
    assert data["compliance"]["summary"]["verified"] is True


def test_timeline_dubai_focus_day():
    r = client.get("/demo/dubai")
    focus = r.json()["focus_day"]
    r2 = client.get(f"/timeline/dubai/{focus}")
    assert r2.status_code == 200
    assert r2.json()["gap_hours"] > 0


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


def test_decide_hot_conditions():
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
    assert body["advisory"]["signal"] in ("WORK", "REST_IN_SHADE", "STOP")
    assert "personal_risk_score" in body["advisory"]
    assert len(body["live"]) == 60


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


def test_unknown_demo_404():
    r = client.get("/demo/invalid_site")
    assert r.status_code == 404
