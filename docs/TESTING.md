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

## CI parity gate

Every push / PR runs (see `.github/workflows/ci.yml`):

| Job | Role |
|-----|------|
| **Interpreter version drift** | Dockerfile runtime Python == CI canonical (`3.11`) and satisfies `requires-python` |
| **Python engine + API tests** | Full pytest on Python **3.11** (matches Dockerfile) |
| **Dependency resolution determinism** | Two successive `pip install -e ".[api,ml,dev]"` freezes must be identical |
| **Golden parity (3.11)** | `golden.check_against_committed()` offline — **required** |
| **Golden parity (3.12)** | Same check on the migration target — **advisory** (`continue-on-error`) until WO-008 |
| **React dashboard build + lint** | Node **24**, `npm run lint` then `npm run build` |

Actions are SHA-pinned (checkout v7, setup-python v6, setup-node v6, upload-artifact v7).

### Branch protection (operator action)

Mark these as required status checks on `main`:

- Interpreter version drift
- Python engine + API tests
- Dependency resolution determinism
- Golden parity (Python 3.11)
- React dashboard build + lint

Do **not** require Golden parity (Python 3.12) until that matrix leg is green after the 3.12 migration.

### When the golden-parity gate fails

1. Open the failed job → download the `golden-diff-py3.11` (or `…3.12`) artifact.
2. Read `diff.txt` (bounded: first 20 differing paths) and `run_manifest.json` (interpreter + package versions).
3. Triage:
   - **Numerics / runner drift** — same science, different float stack → do **not** regenerate; pin deps / align interpreter.
   - **Intentional science change** — regenerate with `heatguard golden capture` on Python 3.11, justify every file in the PR, get reviewer sign-off.
4. To revert a bad baseline move: `git checkout origin/main -- tests/golden data/cache/CHECKSUMS.json` and re-run `heatguard golden check`.

### Proving the gate (scratch branches)

These are intentional failure drills — do not merge:

```bash
# 1) Perturb WBGT by 0.01°C → golden-parity must go red
# 2) Mutate a pin in requirements.txt → determinism / install drift
# 3) Change Dockerfile `python:3.11` → `python:3.12` → version-drift red
# 4) Introduce an ESLint error in web/src → web-build red
```

## Measured suite size

As of the golden-masters gate (WO-001–003), ``pytest --collect-only`` on
Python 3.11 reports **152** collected tests (measured 2026-07-31). The old
“79 vs 110” ambiguity is resolved by that measured number. CI output remains
authoritative if the suite grows.

### Characterization baseline replaced by WO-003

`tests/test_demo_narrative.py` previously used tolerance bands
(`gap_hours >= 10`, `danger_hours_caught_vs_ban > 100`, etc.). Those are gone;
the module now byte-compares against `tests/golden/<site>/`.

## Tests

```bash
pytest -q tests/test_canonical.py tests/test_golden.py
pytest -q   # full suite (measured count is the source of truth)
python scripts/ci_version_drift.py --ci-python 3.11
```
