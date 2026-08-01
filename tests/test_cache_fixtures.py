"""Offline cache fixtures — presence, checksums, and docs consistency."""
from __future__ import annotations

import re
from pathlib import Path

from heatguard import cache_integrity as ci
from heatguard import datasets
from heatguard._paths import CACHE_DIR, _REPO_ROOT
from heatguard.sites import get_site
from heatguard.weather import openmeteo


def test_required_caches_present_and_parse():
    demo_keys = {r["site_key"] for r in datasets.load_manifest()["weather"]["archive"]["demo"]}
    for spec in datasets.archive_specs():
        if not spec.required:
            continue
        assert spec.site_key in demo_keys
        path = CACHE_DIR / spec.cache_file
        assert path.exists(), f"missing required archive {spec.cache_file}"
        rows = openmeteo._parse(
            __import__("json").loads(path.read_text()), get_site(spec.site_key)
        )
        assert len(rows) > 0

    for spec in datasets.forecast_specs():
        path = CACHE_DIR / spec.cache_file
        assert path.exists(), f"missing required forecast {spec.cache_file}"
        rows = openmeteo._parse(
            __import__("json").loads(path.read_text()), get_site(spec.site_key)
        )
        assert len(rows) > 0


def test_checksums_match_required_set():
    problems = ci.verify_cache_manifest()
    assert problems == [], "\n".join(p.message() for p in problems)
    entries = ci.load_checksum_entries()
    for name in ci.required_cache_names():
        assert name in entries
        assert entries[name].required is True
        assert entries[name].row_count > 0


def test_inventory_distinguishes_manifest_from_cache():
    inv = datasets.inventory()
    weather = inv["weather"]
    assert weather["archive_total"] >= 7
    assert weather["archive_required"] == 4
    assert weather["archive_required_cached"] == weather["archive_required"]
    assert weather["forecast_cached"] == weather["forecast_total"] == 4
    # Manifest may list optional gulf_season; all currently committed
    assert weather["archive_cached"] == weather["archive_total"]


def test_docs_list_committed_cache_files():
    data_md = (_REPO_ROOT / "docs" / "DATA.md").read_text()
    site_html = (_REPO_ROOT / "website" / "data.html").read_text()
    on_disk = sorted(
        p.name for p in CACHE_DIR.glob("*.json") if p.name != "CHECKSUMS.json"
    )
    # Every required demo/forecast filename must appear in both docs.
    for name in sorted(ci.required_cache_names()):
        assert name in data_md, f"docs/DATA.md missing {name}"
        # website may show shortened form; require stem prefix at least
        stem = name.split("_20")[0] if "_20" in name else name.split("_forecast")[0]
        assert stem in site_html or name in site_html, (
            f"website/data.html missing reference to {name} / {stem}"
        )
    assert "CHECKSUMS.json" in data_md
    assert "CC-BY 4.0" in data_md or "CC-BY" in data_md
    assert "non-commercial" in data_md.lower() or "non-commercial" in site_html.lower()
    # Docs must not claim forecast is uncached
    assert not re.search(r"Forecast API.*[Nn]ot cached", site_html)
    assert len(on_disk) >= 8
