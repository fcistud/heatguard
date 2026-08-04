# Testing & golden masters

## Purpose

HeatGuard’s ISO 7243 / ISO 7933 PHS / ACGIH / NIOSH engine must stay **byte-stable**
across interpreter and dependency upgrades. Golden masters under `tests/golden/` are
the authoritative reference, currently captured on **Python 3.12** with the pinned
numerics stack (`numpy==1.26.4`, `pythermalcomfort==4.0.1`, `thermofeel==2.2.0`).

The pre-migration (Python 3.11) baseline remains in git history (Gate 0 / PR #15).
See `tests/golden/README.md` for the WO-008 re-baseline justification.

## Capture (offline)

Networking is disabled during capture. Only committed files under `data/cache/` are
read. SHA-256 digests live in `data/cache/CHECKSUMS.json` and are mirrored into each
site’s `MANIFEST.json`.

```bash
uv sync --frozen --extra api --extra ml --extra dev   # Python 3.12

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

Parity compares strip host/VCS fields from `MANIFEST.json` (`git_commit`,
`platform`, `python_implementation`) so Linux CI can match goldens captured on
macOS. Package pins and cache checksums still fail the gate if they drift.

## Canonical JSON

All golden files are written by `heatguard.canonical`:

- sorted keys, compact separators, UTF-8
- non-finite floats → `null`
- finite floats → shortest round-trip (`.17g`)
- datetimes → UTC ISO-8601 with `Z`

Equality checks are **byte comparisons** of file contents (including the trailing newline).

## Sign-off rule for regeneration

Regenerate and replace `tests/golden/` **only** when:

1. You intentionally change engine behaviour, the committed weather caches, **or**
   the supported interpreter (with a documented float-parity investigation), **and**
2. The PR description records the interpreter + dependency versions, **and**
3. Reviewers accept the diff as an intentional baseline move (not silent drift).

Do **not** regenerate solely because a newer NumPy is convenient.

## CI parity gate

Every push / PR runs (see `.github/workflows/ci.yml`):

| Job | Role |
|-----|------|
| **Interpreter version drift** | Dockerfile runtime Python == CI canonical (`3.12`) == `requires-python` floor |
| **Python engine + API tests** | Full pytest on Python **3.12** (matches Dockerfile) |
| **Dependency resolution determinism** | Two successive frozen `uv export`s must be identical |
| **Golden parity (3.12)** | `golden.check_against_committed()` offline — **required** |
| **React dashboard build + lint** | Node **24**, lint + test + build |
| **Container image smoke** | Build image; assert tooling extras absent; health reports 3.12; demo/forecast/dashboard |
| **Monitoring config** | `scripts/validate_monitoring.py` — alert policies, runbook anchors, SLO doc links |

Actions are SHA-pinned (checkout v7, setup-python v6, setup-node v6, upload-artifact v7).

### Branch protection (operator action)

Mark these as required status checks on `main`:

- Interpreter version drift
- Python engine + API tests
- Dependency resolution determinism
- Golden parity (Python 3.12)
- React dashboard build + lint
- Container image smoke
- Monitoring config

### When the golden-parity gate fails

1. Open the failed job → download the `golden-diff-py3.12` artifact.
2. Read `diff.txt` (bounded: first 20 differing paths) and `run_manifest.json` (interpreter + package versions).
3. Triage:
   - **Numerics / runner drift** — same science, different float stack → do **not** regenerate; pin deps / align interpreter.
   - **Intentional science or interpreter move** — regenerate with `heatguard golden capture` on Python 3.12, justify every file in the PR (see `tests/golden/README.md`), get reviewer sign-off.
4. To revert a bad baseline move: `git checkout origin/main -- tests/golden data/cache/CHECKSUMS.json` and re-run `heatguard golden check`.

### Proving the gate (scratch branches)

These are intentional failure drills — do not merge:

```bash
# 1) Perturb WBGT by 0.01°C → golden-parity must go red
# 2) Mutate a pin in requirements.txt → determinism / install drift
# 3) Change Dockerfile `python:3.12` → `python:3.11` → version-drift red
# 4) Introduce an ESLint error in web/src → web-build red
```

## Measured suite size

As of WO-017 (monitoring validation + policy retrieval rename), ``pytest --collect-only -q``
on Python **3.12** reports **265** collected tests. CI job output remains authoritative when
in doubt.

### Characterization baseline replaced by WO-003

`tests/test_demo_narrative.py` previously used tolerance bands
(`gap_hours >= 10`, `danger_hours_caught_vs_ban > 100`, etc.). Those are gone;
the module now byte-compares against `tests/golden/<site>/`.

## Tests

```bash
uv run pytest -q tests/test_canonical.py tests/test_golden.py
uv run pytest -q   # full suite
python scripts/check_python_version_drift.py --ci-python 3.12
```
