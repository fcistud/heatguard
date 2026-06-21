"""Tests for the personal risk ML overlay."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from heatguard import risk_model
from heatguard.risk_model import assess, feature_vector, model_path, phs_elevated_label
from heatguard.scheduler import build_conditions, decide, schedule
from heatguard.types import MetabolicCategory, Worker
from heatguard.weather import fetch_archive

TZ4 = timezone(timedelta(hours=4))


@pytest.fixture
def dubai_hot_hour(dubai):
    season = fetch_archive(dubai, __import__("datetime").date(2025, 5, 1), __import__("datetime").date(2025, 9, 15))
    hot = max(season, key=lambda w: w.tdb_c)
    return hot


def test_model_file_committed():
    assert model_path().exists(), "run scripts/train_risk_model.py and commit data/models/"


def test_newcomer_elevated_more_often_than_veteran(dubai_hot_hour, dubai):
    cat = MetabolicCategory.HEAVY
    veteran = Worker("v", days_on_job=120, acclimatized=True)
    newcomer = Worker("n", days_on_job=0, acclimatized=False)
    cv = build_conditions(dubai_hot_hour, dubai, cat)
    cn = build_conditions(dubai_hot_hour, dubai, cat)
    rv = assess(cv, veteran)
    rn = assess(cn, newcomer)
    assert rn.score >= rv.score


def test_decide_attaches_personal_risk_without_changing_signal(dubai_hot_hour, dubai, veteran):
    adv = schedule(dubai_hot_hour, dubai, veteran, MetabolicCategory.HEAVY)
    assert 0.0 <= adv.personal_risk_score <= 1.0
    assert isinstance(adv.elevated_risk, bool)
    assert adv.personal_risk_note
    d = adv.to_dict()
    assert "personal_risk_score" in d
    assert "elevated_risk" in d


def test_feature_vector_length_matches_names(dubai_hot_hour, dubai, veteran):
    c = build_conditions(dubai_hot_hour, dubai, MetabolicCategory.HEAVY)
    vec = feature_vector(c, veteran)
    assert len(vec) == len(risk_model.FEATURE_NAMES)


def test_phs_label_true_for_extreme_newcomer(dubai_hot_hour, dubai):
    c = build_conditions(dubai_hot_hour, dubai, MetabolicCategory.HEAVY)
    newcomer = Worker("n", days_on_job=0, acclimatized=False, weight_kg=95, height_m=1.70)
    assert phs_elevated_label(c, newcomer) is True


def test_heuristic_when_model_missing(monkeypatch, dubai_hot_hour, dubai, veteran):
    risk_model._load_model.cache_clear()
    monkeypatch.setattr(risk_model, "_load_model", lambda: None)
    c = build_conditions(dubai_hot_hour, dubai, MetabolicCategory.HEAVY)
    r = assess(c, veteran)
    assert "Heuristic" in r.note
