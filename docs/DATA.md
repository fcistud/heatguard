# HeatGuard datasets

Real and curated data used by the engine, demos, and (future) policy RAG.  
**Manifest:** `data/datasets.json`

## Quick start

```bash
conda activate heatguard          # or your venv
heatguard fetch-datasets          # download + cache all listed weather data
heatguard fetch-datasets --refresh  # force re-download
```

Demo weather for Dubai and Riyadh is **already committed** under `data/cache/` so `pytest` and the dashboard work offline.

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

## Archive seasons (manifest)

**Demo (primary narratives):**

- `dubai` — 2025-05-01 → 2025-09-15 (shoulder season before UAE ban)
- `riyadh` — 2024-06-01 → 2024-09-15 (in-season morning gap)

**Extended Gulf coverage:**

- `abu_dhabi`, `doha`, `kuwait_city`, `muscat`, `manama` — see `data/datasets.json` for date ranges

## Forecast

Manifest sites: `dubai`, `riyadh`, `doha`, `abu_dhabi` (2 forecast days + 1 past day).

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
4. Commit the new `data/cache/*.json` file for offline demos.

## What we do not ship

- Individual worker health records (not publicly available)
- On-site WBGT meter time series (use `measured_wbgt` on `/decide` for ad-hoc input)
- UK/NHS datasets (see [hackathon data page](https://healthinclimate.ai/hackathons/london/data) — not used in this Gulf MVP)
