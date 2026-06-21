"""Tests for dataset manifest, policy corpus, and forecast caching."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from heatguard import datasets
from heatguard.service import forecast_timeline
from heatguard.weather.openmeteo import forecast_cache_name_for


@pytest.fixture
def dubai_forecast_cache(dubai, tmp_path, monkeypatch):
    """Copy committed Dubai archive slice into a synthetic forecast cache file."""
    from heatguard._paths import CACHE_DIR, cache_file
    from heatguard.weather.openmeteo import cache_name_for, fetch_archive

    archive_path = cache_file(cache_name_for(dubai, __import__("datetime").date(2025, 5, 1),
                               __import__("datetime").date(2025, 9, 15)))
    if not archive_path.exists():
        pytest.skip("Dubai archive cache not present")

    payload = json.loads(archive_path.read_text())
    # Trim to a short window so the forecast parser still gets valid hourly data.
    h = payload["hourly"]
    n = min(72, len(h["time"]))
    trimmed = {**payload, "hourly": {k: v[:n] for k, v in h.items()}}
    fc_name = forecast_cache_name_for(dubai, 2, 1)
    fc_path = tmp_path / fc_name
    fc_path.write_text(json.dumps(trimmed))
    monkeypatch.setattr(datasets, "CACHE_DIR", tmp_path)
    from heatguard.weather import openmeteo

    monkeypatch.setattr(openmeteo, "CACHE_DIR", tmp_path)

    def _cache_file(name: str) -> Path:
        return tmp_path / name

    monkeypatch.setattr(openmeteo, "cache_file", _cache_file)
    return fc_path


def test_manifest_lists_all_gulf_archives():
    archives = datasets.archive_specs()
    keys = {a.site_key for a in archives}
    assert "dubai" in keys
    assert "riyadh" in keys
    assert "doha" in keys
    assert len(archives) >= 7


def test_policy_corpus_has_real_documents():
    corpus = datasets.load_policy_corpus()
    assert len(corpus) >= 4
    ids = {p["id"] for p in corpus}
    assert "gcc_ban_summary" in ids
    assert "ilo_wrs_excerpt" in ids
    assert all(len(p["text"]) > 100 for p in corpus)


def test_epidemiology_loads():
    epi = datasets.load_epidemiology()
    assert "gulf_outdoor_labour" in epi
    assert epi["gulf_outdoor_labour"]["intervention_aki_reduction"] == 0.94


def test_inventory_reports_policy_and_weather():
    inv = datasets.inventory()
    assert inv["weather"]["archive_total"] >= 7
    assert inv["policy"]["file_count"] >= 4
    assert inv["epidemiology"]["source_count"] >= 1


def test_forecast_timeline_uses_cache(dubai, dubai_forecast_cache):
    tl = forecast_timeline("dubai")
    assert tl["site"]["key"] == "dubai"
    assert tl["source"] == "open-meteo-forecast"
    assert len(tl["rows"]) >= 1
    assert "recommended_shift_start" in tl["summary"]
