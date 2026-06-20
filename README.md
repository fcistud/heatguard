# HeatGuard 🌡️

**An adaptive, WBGT-driven work–rest–hydration scheduler that replaces the Gulf's blunt
calendar-based midday work ban with a condition-responsive, standards-based, and
*provable* heat-safety system for outdoor labour crews.**

HeatGuard takes live or replayed weather, computes the heat-stress index, and outputs the
*actual* mandated work-rest cycle and hydration schedule for current conditions and work
intensity — broadcasting a single signal (**WORK · REST IN SHADE · DRINK NOW · STOP**) to
the whole site. It enforces an acclimatization ramp for new arrivals, logs every decision
to a tamper-evident audit trail, and turns the avoided harm into a hard business case.

It is built as one pure, deterministic **Python engine** with five interfaces over it: a
**CLI**, a **FastAPI** backend, a polished **React dashboard**, a pure-Python **Streamlit**
app, and a validation **Jupyter notebook**.

```bash
pip install -e . && pip install -r requirements.txt
pytest -q                 # 59 tests, incl. the Nicaragua back-test
heatguard fetch-demo      # cache real Open-Meteo weather (committed; run once)
scripts/run_demo.sh       # API + dashboard in one command  →  http://localhost:5173
```

---

## Table of contents

1. [The problem](#1-the-problem)
2. [The solution, and why this exact form](#2-the-solution-and-why-this-exact-form)
3. [System architecture](#3-system-architecture)
4. [The scientific engine, module by module](#4-the-scientific-engine-module-by-module)
5. [The decision pipeline](#5-the-decision-pipeline)
6. [Hard-won technical details (the gotchas)](#6-hard-won-technical-details-the-gotchas)
7. [Impact: the model, the math, the numbers](#7-impact-the-model-the-math-the-numbers)
8. [The business case](#8-the-business-case)
9. [Validation & testing](#9-validation--testing)
10. [Interfaces](#10-interfaces)
11. [Install, run, project layout](#11-install-run-project-layout)
12. [Honest limitations](#12-honest-limitations)
13. [Data sources & standards](#13-data-sources--standards)

---

## 1. The problem

### 1.1 The setting

Millions of migrant workers do outdoor manual labour — construction, infrastructure,
delivery — across the Gulf, where summer wet-bulb-globe temperatures routinely exceed the
limits of human thermoregulation. Sustained heat exposure during heavy work causes acute
kidney injury (AKI), heat exhaustion, heat stroke, and death. The kidney-injury epidemic
among manual labourers in hot climates is now a well-documented occupational disease.

### 1.2 The current control: a calendar

Every Gulf state mitigates this with a **calendar-based midday ban** — a fixed clock window,
on fixed calendar dates, during which outdoor work under the sun is prohibited:

| State | Daily window | Season | Notes |
|---|---|---|---|
| **Saudi Arabia** | 12:00–15:00 | 15 Jun – 15 Sep | MHRSD / National Council for OSH |
| **UAE** | 12:30–15:00 | 15 Jun – 15 Sep | Fines AED 5,000/worker (max 50,000); 8 h/day cap; shaded rest required |
| **Kuwait** | 11:00–16:00 | 01 Jun – 31 Aug | Widest window |
| **Oman** | 12:30–15:30 | 01 Jun – 31 Aug | |
| **Bahrain** | 12:00–16:00 | 15 Jun – 31 Aug | |
| **Qatar** | 10:00–15:30 | 01 Jun – 15 Sep | **Only WBGT rule** — work stops if WBGT > 32.1 °C |

### 1.3 Why the calendar is wrong — in *both* directions

Human-rights bodies (HRW and others) have documented the specific failure modes, each of
which is a design target for HeatGuard:

- **It starts too late.** The bans begin 15 June, yet extreme heat now arrives in May —
  Dubai saw a major heat event in **May 2025, before any ban was in force**. A worker can
  die in a May heatwave that the calendar simply does not cover.
- **It misses the edges of the day.** Dangerous *humid mornings and evenings* fall outside
  the noon window. WBGT can be lethal at 9 a.m. while the calendar says "work."
- **It ignores actual conditions.** Except in Qatar, the rule is blind to temperature,
  humidity, wind, solar load, and work intensity. A cool, breezy noon is banned; a brutal
  humid morning is permitted.
- **It ignores acclimatization.** A newly-arrived, unacclimatized worker — the group that
  actually dies — gets exactly the same protection as a 10-year veteran. None of it is
  individualized.
- **It only addresses "direct sunlight."** Shaded but high-humidity work is unregulated.
- **It over-restricts.** On many in-season days, part of the noon window is genuinely
  workable, so the blunt ban also *destroys safe, productive hours* — which is precisely
  why employers resent it and why it gets evaded.

The contradiction the calendar can't resolve: **it is simultaneously too permissive (it
misses real danger) and too restrictive (it stops safe work).** A fixed rule cannot be both
safe and efficient because the underlying risk is not fixed — it depends on the weather, the
job, and the worker.

### 1.4 The intervention science is already solved — implementation is not

The most important reframe: **we already know what prevents heat illness, and it is cheap.**
The La Isla Network's *Adelante Initiative* at the Ingenio San Antonio sugar mill in
Nicaragua ran a structured **Water–Rest–Shade (WRS)** program — mandated breaks, shade
tents, and purified water with electrolytes. Per a 2024 ILO report, it **reduced acute
kidney injury by ~94% and raised productivity 10–20%** *despite* reduced raw working time,
because protecting workers reverses the heat-driven productivity collapse.

The science is cheap, simple, and proven. **The gap is not knowing what to do — it is doing
it adaptively, reliably, and verifiably.** The research repeatedly found that the
effectiveness of an intervention cannot be assessed without considering *implementation
fidelity*. Screening workers out (ISA spent a decade hiring only people with good kidney
function — they still got injured) is not the answer; **preventing the exposure** is.

> **That implementation-and-verification layer is the missing piece HeatGuard supplies.**

---

## 2. The solution, and why this exact form

HeatGuard is a **site-level, WBGT-driven work–rest–hydration scheduler with a verification
layer**, deployed to the *supervisor*, not to each worker. Concretely it does four things:

1. **Senses** — takes one on-site WBGT reading (a ~$300 meter) *or* estimates WBGT from
   weather, per ISO 7243.
2. **Schedules** — outputs the *actual* work-rest cycle (ACGIH/ISO 7243) and hydration
   target (ISO 7933 Predicted Heat Strain) for the current conditions and work intensity,
   replacing the calendar with a responsive rule.
3. **Signals** — drives one dumb, cheap signal everyone already understands (site horn /
   light / one supervisor phone): **WORK · REST IN SHADE · DRINK NOW · STOP**.
4. **Verifies** — logs every reading, break, drink prompt, and water-availability
   attestation into a **tamper-evident, hash-chained record** that doubles as the
   employer's compliance shield against inspection and fines.

…plus a graded **acclimatization ramp** for new arrivals (the deadliest group, and the
cheapest to manage because it is pure scheduling).

### Why a site-level scheduler, not a wearable

Per-worker hardware is where adoption friction lives — cost, charging, breakage, and
surveillance concerns. The adoptable form is **one sensor per site, riding on existing
infrastructure, with near-zero marginal cost per worker**, that gives the employer a
*productivity story* and a *liability shield* rather than a cost — and supplies exactly the
implementation-fidelity layer the evidence says is the real missing piece. (A per-worker NFC
wristband *at the water station only*, to verify hydration, is an optional premium layer.)

---

## 3. System architecture

One shared, **pure, deterministic** Python core holds all the science and economics. The
core does no I/O; weather ingestion and exports live at the edges. Every interface is a thin
presentation layer over the same engine, so the numbers are computed in exactly one place.

```
                 ┌───────────────── heatguard (core, pure Python) ─────────────────┐
                 │  types        shared dataclasses + enums (the data model)        │
                 │  solar        vendored NOAA cosine-solar-zenith (no heavy dep)   │
                 │  wbgt         outdoor WBGT (Liljegren + Stull fallback + source) │
                 │  worktables   ACGIH TLV/AL step tables (ISO 7243)               │
                 │  hydration    ISO 7933 PHS via pythermalcomfort                  │
                 │  acclimatization   NIOSH new-worker ramp                         │
                 │  scheduler    orchestrator: Conditions+Worker → Advisory         │
                 │  calendar_ban GCC ban rules (the foil)                           │
                 │  compliance   SHA-256 hash-chained audit log                     │
                 │  impact       mechanistic AKI + productivity model               │
                 │  economics    business case / ROI                               │
                 │  weather/     Open-Meteo client + replay                         │
                 │  service      assembles demo/timeline/impact/economics payloads  │
                 └─────────────────────────────────────────────────────────────────┘
                      ▲            ▲              ▲              ▲            ▲
                    CLI        FastAPI      React dashboard   Streamlit   Notebook
                 (cli.py)     (api.py)        (web/)      (streamlit_app) (notebooks/)
```

**Design invariants**
- `scheduler`, `worktables`, `hydration`, `acclimatization`, `impact`, `economics` are
  **I/O-free and deterministic** → the test suite and the back-test are trustworthy.
- Input/output records are **frozen dataclasses** → the audit trail is immutable.
- Every WBGT value carries its **provenance** (`liljegren | fallback | measured`) all the
  way into the compliance log and the UI — the approximation is never hidden.

---

## 4. The scientific engine, module by module

### 4.1 `wbgt.py` + `solar.py` — outdoor WBGT estimation

WBGT (Wet-Bulb Globe Temperature) is the standard occupational heat-stress index. Outdoor
WBGT is a weighted blend:

```
WBGT = 0.7·T_nwb + 0.2·T_g + 0.1·T_db          (with solar load)
WBGT = 0.7·T_nwb + 0.3·T_db                      (shade / no sun)
```

where `T_nwb` = natural wet-bulb, `T_g` = black-globe, `T_db` = dry-bulb air. `pythermalcomfort`'s
`wbgt()` needs wet-bulb and globe temperatures as *inputs*, so it can't estimate outdoor WBGT
from ordinary weather. HeatGuard therefore computes it:

- **Daytime:** the validated **Liljegren et al. (2008)** model via `thermofeel`, fed air
  temperature, humidity, wind, surface pressure, and shortwave/direct solar radiation, plus
  the **cosine of the solar zenith angle**.
- **Solar geometry:** `thermofeel` no longer ships a solar-position function (it defers to
  the heavy `earthkit-meteo`). `solar.py` is a **vendored ~50-line NOAA solar-position
  implementation** (Julian date → equation of time → hour angle → cos zenith) — zero extra
  dependencies, sub-degree accuracy.
- **Night / non-convergence:** a **Stull (2011)** natural-wet-bulb fallback plus a bounded
  solar-globe bump; Liljegren returns NaN below the horizon, so this branch is required.
- **Globe temperature** for the radiant load is recovered consistently from the WBGT value
  (`T_g = (WBGT − 0.7·T_nwb − 0.1·T_db)/0.2`) and fed to the PHS model as mean-radiant
  temperature — never `T_r = T_db`, which would badly understate strain under sun.
- **Measured path:** a supervisor's on-site meter reading bypasses estimation entirely
  (`source="measured"`), mirroring the real product.

### 4.2 `worktables.py` — the regulatory work-rest cycle (ACGIH / ISO 7243)

The legally-meaningful output. Hard-coded **ACGIH TLV** (acclimatized) and **Action-Limit**
(unacclimatized) screening tables give the highest WBGT (°C) at which each work allocation is
permitted, by metabolic category:

**TLV (acclimatized)** — WBGT °C ceilings:

| Allocation | Light | Moderate | Heavy | Very heavy |
|---|---|---|---|---|
| 100% work | 31.0 | 28.0 | — | — |
| 75% / 25% rest | 31.0 | 29.0 | 27.5 | — |
| 50% / 50% | 32.0 | 30.0 | 29.0 | 28.0 |
| 25% / 75% | 32.5 | 31.5 | 30.5 | 30.0 |

**Action Limit (unacclimatized)** is ~3 °C stricter throughout (e.g. moderate 100% → 25.0).

- **Mapping is a STEP lookup**, not interpolation — the standard's intent and what an
  inspector expects: scan 100→75→50→25 and take the first allocation whose ceiling ≥ current
  WBGT; above the 25% ceiling → **STOP**; below the lowest listed ceiling → unrestricted
  (heat-stress screening simply doesn't apply yet). A `"—"` cell means that allocation has no
  screening WBGT for that intensity (the physiological PHS layer catches metabolic danger
  there).
- A separate **continuous `risk_score`** (interpolated 0–1) is exposed **for the UI gauge
  only** — the legal cycle stays stepped.

### 4.3 `hydration.py` — physiology via ISO 7933 PHS

Wraps `pythermalcomfort.models.phs` (Predicted Heat Strain, ISO 7933:2023). Two calls per
decision, by design:

- **Per-hour hydration:** PHS at the *cycle-weighted* metabolic rate over **60 minutes** →
  `sweat_loss_g` (the per-hour drink target; 1 g ≈ 1 mL ≈ cups/250) and end-of-hour core
  temperature `t_cr`.
- **Max safe exposure:** PHS at the *full working* metabolic rate over a **480-minute
  horizon** → the true minutes-to-limit `min(d_lim_t_re, d_lim_loss_95)`. (`d_lim_*` are
  *cumulative and cap at `duration`*, so a long horizon is required to read the real limit.)

This max-safe time becomes a **work-fraction cap** in the scheduler — `max_safe_min / 60` —
so PHS contributes *work-then-break*, not a hard STOP.

### 4.4 `acclimatization.py` — the NIOSH ramp

New arrivals are the deadliest group and the cheapest to protect (pure scheduling). Two
effects, applied only when heat stress is actually present:

- **Exposure cap:** brand-new worker `[0.20, 0.40, 0.60, 0.80, 1.00]` over days 0–4;
  heat-experienced-but-new-to-the-job `[0.50, 1.00]` over days 0–1.
- **Threshold:** while ramping, screen against the stricter **Action-Limit** table; the
  ramp length and the table window are aligned (5 days new / 2 days experienced).

### 4.5 `scheduler.py` — the orchestrator

`decide(Conditions, Worker) → Advisory`. The called work fraction is the **most conservative
of three independent limits**:

```
eff_fraction = min( ACGIH_table_fraction ,
                    acclimatization_cap ,        # only when heat stress present
                    PHS_cap = max_safe_min / 60 )
```

**STOP** fires only when `work_min < 5` (no safe block remains) or WBGT is above the table's
most-permissive ceiling. Otherwise a work-rest cycle is prescribed. The advisory carries the
signal, the cycle, the hydration target, the acclimatization fraction, the WBGT + provenance,
a continuous risk score, and a human-readable rationale. `live_signal()` expands an advisory
into the minute-by-minute broadcast (Work block → Drink pulses → Rest break).

### 4.6 `calendar_ban.py` — the foil

The GCC ban rules above as data, with `is_banned(country, timestamp, wbgt)` (season + daily
window, plus Qatar's WBGT > 32.1 °C override). This is what HeatGuard is benchmarked against.

### 4.7 `compliance.py` — the tamper-evident audit trail

An append-only, **SHA-256 hash-chained** log. Each record commits to the previous
(`record_hash = sha256(prev_hash + canonical_json(body))`), so any later edit or deletion
breaks `verify_chain()`. Records the WBGT + source, the called cycle, drink prompts, STOPs,
and the supervisor's water-availability attestation; exports to CSV (audit binder) and JSONL
(directly verifiable). This is the **compliance shield** — cryptographic proof that conditions
were monitored and breaks/water were provided, defending against fines and liability.

### 4.8 `impact.py` & `economics.py`

The health/productivity model and the ROI — detailed in [§7](#7-impact-the-model-the-math-the-numbers)
and [§8](#8-the-business-case).

### 4.9 `weather/` — Open-Meteo client + replay

Free, no-key historical archive (for replaying real days/seasons) and forecast (for a near-live
signal). Responses are cached to `data/cache/` and committed, so the demo runs **fully offline**.
Wind is requested in m/s, pressure arrives in hPa — matching the engine's units.

---

## 5. The decision pipeline

A single decision for one (worker, hour) flows through frozen dataclasses:

```
Weather  ──estimate_wbgt──▶  Conditions  ──scheduler.decide──▶  Advisory  ──compliance.append──▶  LogRecord
(tdb, rh,                    (+ wbgt_c,                          (signal, cycle,                   (hash-chained)
 wind, solar,                 wbgt_source,                        hydration, rationale,
 pressure)                    globe_c,                            risk_score, ...)
                              met_category)
```

Core data structures (`types.py`): `Site`, `Weather`, `Conditions`, `Worker`,
`WorkRestCycle`, `HydrationTarget`, `Advisory`; enums `Signal`, `MetabolicCategory`,
`Posture`. `MetabolicCategory` carries the metabolic rate in **met units**
(rest 1.1 · light 1.8 · moderate 2.9 · heavy 4.0 · very-heavy 5.0).

---

## 6. Hard-won technical details (the gotchas)

These were discovered by probing the actual libraries against real Gulf conditions, and they
are why the engine is correct rather than merely plausible:

- **PHS `met` is W/m², valid only on [100, 450].** `pythermalcomfort` interprets `met` as
  met-units × 58.15 = W/m², and ISO 7933 is valid only for M ∈ [100, 450] W/m² (met ∈
  [1.72, 7.74]). Rest/light fall below the floor → NaN. The hydration adapter **clamps the
  effective met** into this window (conservative for low intensities).
- **ISO 7933 input envelope: T_r ≤ 60 °C, T_db ≤ 50, v ≤ 3.** A desert black-globe can hit
  ~63 °C, which silently NaNs the whole PHS result. Inputs are **clamped to the Annex-A
  envelope** so PHS stays solvable in Gulf extremes (the clamped 60 °C is still a severe
  radiant load).
- **`d_lim_*` and `sweat_loss_g` are cumulative over `duration`.** Reading the true
  minutes-to-limit requires a long horizon (480 min), while per-hour hydration needs
  exactly 60 min — hence the deliberate two-call design.
- **`thermofeel` wants pressure in hPa, not Pa** (Pa → NaN), returns WBGT in **Kelvin**, and
  **returns NaN when the sun is below the horizon** — which is exactly why the night fallback
  branch exists.
- **numpy scalars leak through PHS** and aren't JSON-serializable; the engine coerces to
  native Python at the boundaries (and the compliance encoder has a numpy-aware fallback) so
  the hash chain is stable and the API returns valid JSON.
- **The acclimatization cap must not bite in cool conditions** — it limits exposure to *heat
  stress*, so it only binds when the table or PHS already restricts work; a newcomer still
  works a full hour at a cool dawn.

---

## 7. Impact: the model, the math, the numbers

### 7.1 A mechanistic AKI model (not a flat multiplier)

HeatGuard delivers water-rest-shade during **every** dangerous hour; the calendar ban only
covers the dangerous hours that happen to fall in its fixed window. The incremental kidney-
injury cases averted **vs the ban** are scaled by that coverage gap:

```
danger hour          := HeatGuard signalled STOP or REST_IN_SHADE
ban_coverage         := danger_hours_in_ban / total_danger_hours
danger_missed_frac   := (total_danger − danger_in_ban) / total_danger        (0 if no danger)

AKI_baseline         := baseline_incidence × crew_size            (default incidence 0.10/worker-season)
AKI_averted_HeatGuard:= 0.94 × AKI_baseline                       (covers all danger)   [0 if no danger]
AKI_averted_vs_ban   := 0.94 × AKI_baseline × danger_missed_frac
```

This collapses to **0** when the ban already covers all danger, to the **full 94%** when the
ban covers none (e.g. a May heatwave before the season), and gates to **0** when a season has
no dangerous hours at all (a degenerate case a flat multiplier would wrongly credit). The
0.94 and the 10–20% productivity band come from the documented Nicaragua effect sizes
(`data/nicaragua_baseline.json`); `sensitivity()` reports the averted-cases band across a
range of the (uncertain) baseline incidence (5%–20%) so the biggest assumption is shown as a
range, not a point.

### 7.2 The demo results

Real Open-Meteo weather, representative acclimatized worker, **crew of 100**:

| | **Dubai** (May focus / season) | **Riyadh** (Jul focus / season) |
|---|---|---|
| Calendar ban on the focus day | **0 of 15 h** (out of season) | 12:00–15:00 (4 h) |
| Gap hours HeatGuard caught, ban missed (focus day) | **12** | **9** |
| Danger hours caught vs ban (season) | **1,237** | ~100s |
| Hours the ban needlessly stopped safe work (season) | 0 | **214** |
| AKI cases averted vs the ban | **7.7** of 10 baseline | ~3–4 |
| Productivity | maintained / +10–20% | maintained / +10–20% |
| Program cost | **~$95 / worker** | ~$95 / worker |

The two demos make complementary points: **Dubai** shows the ban missing whole shoulder-
seasons (the May lane is empty all day); **Riyadh** shows that even in season the fixed
window misses humid mornings and unacclimatized newcomers *and* needlessly stops safe work.

---

## 8. The business case

Adoption is the real game, so the impact is monetised into a defensible ROI (`economics.py`,
assumptions in `data/economics.json`, all illustrative, conservative, and tunable).

```
hourly_value         := daily_value_per_worker / hours_per_day        ($30/day ÷ 8 h)

headline_benefit     := productivity_value                            (10–20% × heat-exposed worker-hours)
                      + recovered_safe_work                           (ban-blocked SAFE hours, fraction-weighted × crew)
                      + AKI_value                                     (AKI_averted_vs_ban × $1,200/case)
                      + fines_avoided                                 ($1,361/worker × 3% expected exposure)

excluded_upside      := death_risk_averted + turnover_reduction       (reported SEPARATELY, never in the headline)

ROI                  := headline_benefit / program_cost
payback_days         := program_cost / (headline_benefit / season_days)
```

The headline deliberately **excludes** the death-averted and turnover terms (so it can't be
accused of inflation), and "recovered safe work" is **fraction-weighted** (it credits actual
productive hours, accounting for breaks). Results, crew of 100:

| | Program cost | Headline benefit | **ROI** | Payback |
|---|---|---|---|---|
| **Dubai** | $9,500 | $31.8k–$50.2k | **3.3×–5.3×** | ~41 days |
| **Riyadh** | $9,500 | — | **7.3×–10.4×** | ~15 days |

Riyadh is higher because the blunt ban there *also* destroys safe work that HeatGuard
recovers. The pitch line: **it is not a safety cost — it is productivity-positive with a
~6-week payback, plus a compliance shield.**

---

## 9. Validation & testing

- **59 pytest tests** (`pytest -q`, network tests skipped by default): exact ACGIH/AL table
  values and step-boundary mapping; WBGT sanity (below air temp, rises with humidity/solar,
  night ≈ wet-bulb); solar geometry; PHS monotonicity and attribute pinning; the
  acclimatization ramp; the most-conservative scheduler logic and STOP consistency; GCC ban
  windows incl. Qatar's WBGT cutoff and out-of-season; compliance chain verification + tamper
  detection; the mechanistic impact (zero-danger, full/zero coverage, crew scaling); and the
  economics ROI.
- **Nicaragua back-test** (`heatguard backtest`): the impact model reproduces the documented
  La Isla / Adelante outcomes — **94% AKI reduction, 10–20% productivity** — as an assertion
  that fails loudly if anyone changes an effect size. This is the validity backbone: the
  numbers rest on a real, measured intervention.
- **Adversarial code review** of the engine (correctness, units, edge cases) confirmed the
  safety chain and the per-worker-vs-crew economics scaling, and drove three fixes
  (zero-danger AKI gating, experienced-worker ramp consistency, work-window alignment).

---

## 10. Interfaces

All five share the engine via `service.py`.

- **CLI** — `heatguard demo dubai|riyadh` (the narrative), `roi`, `backtest`, `decide`,
  `fetch` / `fetch-demo`, `sites`.
- **FastAPI** (`uvicorn heatguard.api:app`) — `/sites`, `/demo/{site}`,
  `/timeline/{site}/{date}`, `/impact/{site}`, `/economics/{site}`, `/sensitivity/{site}`,
  `/backtest`, `/compliance/{site}/export`, `POST /decide`.
- **React dashboard** (`web/`, Vite + TS + Tailwind) — the primary pitch UI: live signal
  tile, WBGT gauge, the **calendar-ban-vs-HeatGuard timeline** with a day scrubber and a
  veteran/new-worker toggle, acclimatization tracker, season impact, the **business-case /
  ROI panel** with an AKI sensitivity chart, the compliance feed, and a live what-if. See
  [`docs/DASHBOARD_WALKTHROUGH.md`](docs/DASHBOARD_WALKTHROUGH.md) for a presenter's guide.
- **Streamlit** (`streamlit run streamlit_app.py`) — a pure-Python, no-build version of the
  same story.
- **Notebook** (`notebooks/heatguard_validation.ipynb`) — the narrated back-test, the
  calendar-vs-adaptive gap on real data, season impact, and the ROI/sensitivity, with charts.

---

## 11. Install, run, project layout

```bash
pip install -e .                 # the `heatguard` CLI + engine
pip install -r requirements.txt  # interface deps
pytest -q                        # 59 tests
heatguard fetch-demo             # cache real Open-Meteo data (committed)

scripts/run_demo.sh --setup      # one command: installs deps + starts API + dashboard
# or individually:
uvicorn heatguard.api:app        # API on :8000
cd web && npm install && npm run dev   # dashboard on :5173 (VITE_API_BASE → API)
```

```
src/heatguard/      the engine (17 modules) + service + cli + api
  weather/          Open-Meteo client + replay
data/locales.json           demo sites
data/nicaragua_baseline.json · data/economics.json   tunable assumptions
data/cache/*.json           committed Open-Meteo weather (offline demo)
tests/                      pytest suite (59)
web/                        React dashboard           streamlit_app.py
notebooks/                  validation notebook        scripts/run_demo.sh
docs/DASHBOARD_WALKTHROUGH.md   presenter's guide
```

---

## 12. Honest limitations

- **WBGT estimation is approximate** without an on-site black-globe sensor (we use the
  validated Liljegren model from reanalysis, with a Stull night fallback). The production
  system measures directly with a ~$300 meter — the engine already accepts a `measured`
  reading that bypasses estimation.
- **Effect sizes transfer** from Mesoamerican agriculture to Gulf construction with
  uncertainty; the baseline AKI incidence is a tunable assumption surfaced via
  `impact.EffectSizes` and shown as a sensitivity range.
- **Work intensity** (light/moderate/heavy/very-heavy, ISO 8996) is a supervisor input.
- **The ROI** rests on illustrative, deliberately conservative cost/value assumptions
  (`data/economics.json`); the headline excludes the death-averted and turnover terms.
- The genuinely hard problem is **adoption**, which is why HeatGuard leads with the
  productivity and compliance-shield framing — the technology is the cheap, proven part.

---

## 13. Data sources & standards

- **Weather:** [Open-Meteo](https://open-meteo.com) free archive + forecast APIs (no key).
- **WBGT:** ISO 7243; Liljegren et al. (2008) via [`thermofeel`](https://github.com/ecmwf/thermofeel);
  Stull (2011) wet-bulb; NOAA solar-position equations (vendored).
- **Heat strain:** ISO 7933:2023 Predicted Heat Strain via
  [`pythermalcomfort`](https://pythermalcomfort.readthedocs.io).
- **Work-rest:** ACGIH TLV / Action Limit screening criteria; ISO 8996 metabolic categories.
- **Acclimatization:** NIOSH criteria for occupational heat exposure.
- **Intervention effect sizes:** La Isla Network / Adelante Initiative (Nicaragua), per the
  2024 ILO report.
- **The foil:** published GCC midday-ban regulations.

MIT-licensed. Built as a hackathon project; the engine is standards-based and unit-tested,
but this is a prototype, not certified safety equipment.
