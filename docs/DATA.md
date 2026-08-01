# HeatGuard datasets

Real and curated data used by the engine, demos, policy RAG, and personal-risk training.  
**Manifest:** `data/datasets.json`  
**Cache digests:** `data/cache/CHECKSUMS.json` (SHA-256 + row counts; v2 schema)

## Quick start

```bash
conda activate heatguard          # or your venv
heatguard fetch-datasets          # download + cache all listed weather data
heatguard fetch-datasets --refresh  # force re-download
```

All **demo** archives and **forecast** payloads required for offline pytest / dashboard
are **already committed** under `data/cache/`. CI and golden capture never fetch.

Open-Meteo free-tier data is **CC-BY 4.0, non-commercial**. Attribution: [Open-Meteo](https://open-meteo.com).

## Committed weather caches

Checksums and hourly row counts live in `data/cache/CHECKSUMS.json`.

### Demo archives (required offline)

| File | Site | Season | Role |
|---|---|---|---|
| `dubai_2025-05-01_2025-09-15.json` | Dubai | 2025-05-01 → 2025-09-15 | Primary demo (pre-ban May) |
| `riyadh_2024-06-01_2024-09-15.json` | Riyadh | 2024-06-01 → 2024-09-15 | Primary demo (in-season) |
| `abu_dhabi_2025-05-01_2025-09-15.json` | Abu Dhabi | 2025-05-01 → 2025-09-15 | UAE capital demo |
| `doha_2024-06-01_2024-09-15.json` | Doha | 2024-06-01 → 2024-09-15 | Qatar WBGT-cutoff demo |

### Forecast caches (required offline)

| File | Site |
|---|---|
| `dubai_forecast_2d_past1d.json` | Dubai |
| `riyadh_forecast_2d_past1d.json` | Riyadh |
| `abu_dhabi_forecast_2d_past1d.json` | Abu Dhabi |
| `doha_forecast_2d_past1d.json` | Doha |

### Optional gulf-season archives (committed, not required for goldens)

| File | Site |
|---|---|
| `kuwait_city_2024-06-01_2024-09-15.json` | Kuwait City |
| `muscat_2024-06-01_2024-09-15.json` | Muscat |
| `manama_2024-06-01_2024-09-15.json` | Manama |

After changing any cache file, regenerate digests:

```bash
python -c "from heatguard.cache_integrity import write_checksums_manifest; write_checksums_manifest()"
# or: heatguard golden capture  (also refreshes CHECKSUMS)
```

## Inventory

| Dataset | Type | Location | Wired to |
|---|---|---|---|
| Gulf site coordinates | Real | `data/locales.json` | `sites.py` |
| Hourly weather (archive) | Real (Open-Meteo / ERA5-class) | `data/cache/{site}_{start}_{end}.json` | `fetch_archive()` → engine |
| Hourly weather (forecast) | Real (Open-Meteo forecast) | `data/cache/{site}_forecast_2d_past1d.json` | `fetch_forecast()` → `/forecast/{site}` |
| WRS intervention effects | Real (published) | `data/nicaragua_baseline.json` | `impact.py`, `/backtest` |
| GCC ban summaries | Real (curated from regulations) | `data/policy/*.md` | `/policy/query` RAG + `/policy/corpus` |
| Gulf epidemiology constants | Published aggregates | `data/epidemiology/gulf_heat.json` | future risk model |
| ML personal risk model | PHS-labelled, real weather inputs | `data/models/risk_model.joblib` | `risk_model.assess()` on each `Advisory` |

Retrain after changing demo weather archives:

```bash
python scripts/train_risk_model.py
```

Check what's cached:

```bash
curl http://localhost:8000/datasets
# or: python -c "from heatguard.datasets import inventory; import json; print(json.dumps(inventory(), indent=2))"
```

## Forecast

Manifest sites: `dubai`, `riyadh`, `doha`, `abu_dhabi` (2 forecast days + 1 past day).
Payloads are committed under `data/cache/*_forecast_2d_past1d.json` for offline demos.

```bash
curl http://localhost:8000/forecast/dubai
```

Returns hourly signals and a **recommended shift window** for the veteran worker profile.

## Policy corpus

Markdown summaries in `data/policy/` — queried via TF-IDF RAG:

```bash
heatguard policy-query "When does the UAE ban start?"
curl -X POST http://localhost:8000/policy/query -H 'Content-Type: application/json' \
  -d '{"question":"How is Qatar WBGT different?"}'
```

Not a substitute for legal advice.

## Adding a new site season

1. Add the site to `data/locales.json` (if missing).
2. Add an entry under `weather.archive` in `data/datasets.json`.
3. Run `heatguard fetch-datasets`.
4. Commit the new `data/cache/*.json` file and refresh `CHECKSUMS.json`.

## What we do not ship

- Individual worker health records (not publicly available)
- On-site WBGT meter time series (use `measured_wbgt` on `/decide` for ad-hoc input)
- UK/NHS datasets (see [hackathon data page](https://healthinclimate.ai/hackathons/london/data) — not used in this Gulf MVP)
