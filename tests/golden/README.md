# Golden masters (`tests/golden/`)

Byte-stable reference outputs for the four demo sites (`dubai`, `riyadh`,
`abu_dhabi`, `doha`). Capture and compare with:

```bash
uv sync --frozen --extra api --extra ml --extra dev
heatguard golden capture   # opt-in write path — never run casually
heatguard golden check     # regenerate to a temp dir and byte-compare
```

## Canonical serialization

See `docs/TESTING.md`. Floats use shortest round-trip (`.17g`); equality is a
byte comparison of the committed JSON files.

## WO-008 re-baseline (Python 3.12) — reviewer sign-off required

**Date:** 2026-08-01  
**Interpreter:** Python 3.12.13  
**Pins unchanged:** `numpy==1.26.4`, `pythermalcomfort==4.0.1`, `thermofeel==2.2.0`

### Investigation

On 3.12, `heatguard golden check` against the 3.11-captured tree reported:

| Artifact | Sites | Nature |
|----------|-------|--------|
| `MANIFEST.json` | all four | `python_version` `3.11.15` → `3.12.13` only (package pins identical) |
| `impact_economics_sensitivity.json` | dubai, riyadh | Season aggregate `heatguard_work_hours_per_worker` drifted by **+0.1 h** (492.7→492.8 dubai; 795.3→795.4 riyadh) |
| All other artifacts | all four | **Byte-identical** (hourly WBGT/signals, focus day, forecast, compliance chain) |

Root cause: float accumulation / 1-decimal rounding of season work-hour totals under
CPython 3.12 vs 3.11. No ACGIH work-rest table boundary, broadcast signal, PHS
hydration, or compliance hash changed.

### Justification for re-baseline

Engine science is unchanged. Re-capture on 3.12 updates MANIFEST interpreter
metadata and the two season-total fields so the required golden-parity gate can
run on the production interpreter. Pre-migration 3.11 artifacts remain in git
history (`golden-masters` / PR #15).

Regeneration command used:

```bash
uv run --python 3.12 heatguard golden capture
uv run --python 3.12 heatguard golden check   # OK
```
