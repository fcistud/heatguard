# ILO / La Isla Water–Rest–Shade (WRS) intervention

## Intervention

Structured **Water–Rest–Shade (WRS)** program for outdoor manual labour:

- Mandated rest breaks in shade
- Shade tents / cooled rest areas
- Purified drinking water with electrolytes
- Supervisor-led implementation (site-level, not per-worker wearables)

## Documented outcomes (Nicaragua — Ingenio San Antonio / Adelante Initiative)

Per the **2024 ILO report** on occupational heat stress (cited in HeatGuard `data/nicaragua_baseline.json`):

| Outcome | Effect size |
|---|---|
| Acute kidney injury (AKI) | **~94% reduction** vs baseline |
| Productivity | **+10% to +20%** despite reduced raw working time |

## Transfer to Gulf construction

Effect sizes are **transferred with uncertainty** from Mesoamerican sugarcane to Gulf outdoor construction. HeatGuard surfaces this via:

- `impact.backtest_nicaragua()` — asserts reproduced effect sizes in tests
- `impact.sensitivity()` — varies baseline AKI incidence (5%–20% per worker-season)

The mechanistic AKI model compares HeatGuard (all danger hours) vs calendar ban (danger hours inside fixed window only).

## Implementation fidelity

ILO and field research emphasize that intervention effectiveness depends on **implementation fidelity** — breaks, shade, and water actually delivered. HeatGuard's hash-chained compliance log targets that verification gap.

## References

- La Isla Network / Adelante Initiative, Ingenio San Antonio, Nicaragua
- ILO (2024) — occupational heat stress and WRS interventions
- HeatGuard: `data/nicaragua_baseline.json`, `impact.py`
