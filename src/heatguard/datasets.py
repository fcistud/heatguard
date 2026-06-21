"""Dataset manifest — lists real data files, cache paths, and policy corpus entries.

Used by the CLI (``fetch-datasets``), API (``/datasets``), and future policy RAG.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ._paths import CACHE_DIR, DATA_DIR, data_file
from .sites import get_site, load_sites
from .weather.openmeteo import cache_name_for, fetch_archive, forecast_cache_name_for


def load_manifest() -> dict:
    return json.loads(data_file("datasets.json").read_text())


def _archive_entries() -> list[dict]:
    m = load_manifest()
    return m["weather"]["archive"]["demo"] + m["weather"]["archive"]["gulf_season"]


def _forecast_cfg() -> dict:
    return load_manifest()["weather"]["forecast"]


@dataclass(frozen=True, slots=True)
class ArchiveSpec:
    site_key: str
    start: date
    end: date
    note: str | None
    cache_file: str
    cached: bool


@dataclass(frozen=True, slots=True)
class ForecastSpec:
    site_key: str
    forecast_days: int
    past_days: int
    cache_file: str
    cached: bool


def archive_specs() -> list[ArchiveSpec]:
    out: list[ArchiveSpec] = []
    for row in _archive_entries():
        site = get_site(row["site_key"])
        start = date.fromisoformat(row["start"])
        end = date.fromisoformat(row["end"])
        name = cache_name_for(site, start, end)
        out.append(
            ArchiveSpec(
                site_key=row["site_key"],
                start=start,
                end=end,
                note=row.get("note"),
                cache_file=name,
                cached=(CACHE_DIR / name).exists(),
            )
        )
    return out


def forecast_specs() -> list[ForecastSpec]:
    cfg = _forecast_cfg()
    days = int(cfg["forecast_days"])
    past = int(cfg["past_days"])
    out: list[ForecastSpec] = []
    for key in cfg["sites"]:
        site = get_site(key)
        name = forecast_cache_name_for(site, days, past)
        out.append(
            ForecastSpec(
                site_key=key,
                forecast_days=days,
                past_days=past,
                cache_file=name,
                cached=(CACHE_DIR / name).exists(),
            )
        )
    return out


def policy_dir() -> Path:
    return data_file(load_manifest()["policy"]["directory"])


def policy_files() -> list[Path]:
    root = policy_dir()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.md"))


def load_policy_corpus() -> list[dict]:
    """Return ``[{id, title, path, text}]`` for each markdown file in ``data/policy/``."""
    out: list[dict] = []
    for path in policy_files():
        text = path.read_text(encoding="utf-8")
        title = path.stem.replace("_", " ").title()
        if text.startswith("#"):
            title = text.splitlines()[0].lstrip("# ").strip()
        out.append({
            "id": path.stem,
            "title": title,
            "path": str(path.relative_to(DATA_DIR)),
            "text": text,
        })
    return out


def load_epidemiology() -> dict:
    rel = load_manifest()["epidemiology"]["path"]
    return json.loads(data_file(rel).read_text())


def fetch_all_archives(refresh: bool = False) -> list[tuple[str, int]]:
    """Fetch every archive row in the manifest. Returns ``[(site_key, row_count), ...]``."""
    results: list[tuple[str, int]] = []
    for spec in archive_specs():
        site = get_site(spec.site_key)
        rows = fetch_archive(site, spec.start, spec.end, refresh=refresh)
        results.append((spec.site_key, len(rows)))
    return results


def fetch_all_forecasts(refresh: bool = False) -> list[tuple[str, int]]:
    from .weather.openmeteo import fetch_forecast

    cfg = _forecast_cfg()
    days = int(cfg["forecast_days"])
    past = int(cfg["past_days"])
    results: list[tuple[str, int]] = []
    for key in cfg["sites"]:
        site = get_site(key)
        rows = fetch_forecast(site, forecast_days=days, past_days=past, refresh=refresh)
        results.append((key, len(rows)))
    return results


def inventory() -> dict:
    """JSON-serialisable snapshot for ``GET /datasets``."""
    archives = archive_specs()
    forecasts = forecast_specs()
    policies = load_policy_corpus()
    return {
        "manifest_version": load_manifest()["version"],
        "sites_registered": len(load_sites()),
        "weather": {
            "source": load_manifest()["weather"]["source"],
            "source_url": load_manifest()["weather"]["source_url"],
            "archive": [
                {
                    "site_key": a.site_key,
                    "start": str(a.start),
                    "end": str(a.end),
                    "note": a.note,
                    "cache_file": f"data/cache/{a.cache_file}",
                    "cached": a.cached,
                }
                for a in archives
            ],
            "archive_cached": sum(1 for a in archives if a.cached),
            "archive_total": len(archives),
            "forecast": [
                {
                    "site_key": f.site_key,
                    "forecast_days": f.forecast_days,
                    "past_days": f.past_days,
                    "cache_file": f"data/cache/{f.cache_file}",
                    "cached": f.cached,
                }
                for f in forecasts
            ],
            "forecast_cached": sum(1 for f in forecasts if f.cached),
            "forecast_total": len(forecasts),
        },
        "policy": {
            "files": [{"id": p["id"], "title": p["title"], "path": p["path"]} for p in policies],
            "file_count": len(policies),
        },
        "epidemiology": {
            "path": f"data/{load_manifest()['epidemiology']['path']}",
            "source_count": len(load_epidemiology().get("sources", [])),
        },
        "intervention": {"path": "data/nicaragua_baseline.json"},
        "economics": {"path": "data/economics.json", "type": "assumptions"},
    }
