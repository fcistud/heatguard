# Testing & golden masters

## Purpose

HeatGuard’s ISO 7243 / ISO 7933 PHS / ACGIH / NIOSH engine must stay **byte-stable**
across interpreter and dependency upgrades. Golden masters under `tests/golden/` are
the pre-migration reference captured on **Python 3.11** with the currently pinned
numerics stack (`numpy==1.26.4`, `pythermalcomfort==4.0.1`, `thermofeel==2.2.0`).

Once the interpreter or those packages move, the pre-migration reference **cannot**
be recaptured honestly — treat regeneration as a deliberate, reviewed sign-off.

## Capture (offline)

Networking is disabled during capture. Only committed files under `data/cache/` are
read. SHA-256 digests live in `data/cache/CHECKSUMS.json` and are mirrored into each
site’s `MANIFEST.json`.

```bash
# Prefer the heatguard conda env (Python 3.11)
conda activate heatguard
pip install -e ".[api,ml,dev]"

# Write / refresh CHECKSUMS + tests/golden/<site>/
heatguard golden capture
# or:
python scripts/capture_golden_masters.py

# Prove two consecutive runs are byte-identical
python scripts/capture_golden_masters.py --idempotent

# Regenerate into a temp dir and byte-compare against the committed tree
heatguard golden check
```

### Artifacts per site (`tests/golden/<site_key>/`)

| File | Contents |
|------|----------|
| `hourly.json` | Focus-day work hours: WBGT + provenance, veteran/newcomer advisories, ban/gap |
| `focus_day.json` | Full `timeline_for_day` payload + demo metadata |
| `forecast.json` | `forecast_timeline` for the site |
| `impact_economics_sensitivity.json` | Season impact, business case, sensitivity (crew=100) |
| `compliance_chain.json` | Full hash chain (`prev_hash`, `record_hash`, genesis) + verify result |
| `MANIFEST.json` | Python/platform/git/package versions, input cache SHA-256, chain verified |

## Canonical JSON

All golden files are written by `heatguard.canonical`:

- sorted keys, compact separators, UTF-8
- non-finite floats → `null`
- finite floats → shortest round-trip (`.17g`)
- datetimes → UTC ISO-8601 with `Z`

Equality checks are **byte comparisons** of file contents (including the trailing newline).

## Sign-off rule for regeneration

Regenerate and replace `tests/golden/` **only** when:

1. You intentionally change engine behaviour or the committed weather caches, **and**
2. The PR description records the interpreter + dependency versions, **and**
3. Reviewers accept the diff as an intentional baseline move (not silent drift).

Do **not** regenerate solely because a newer Python or NumPy is convenient.

## Tests

```bash
pytest -q tests/test_canonical.py tests/test_golden.py
pytest -q -m slow   # includes full regenerate-vs-committed check
```
