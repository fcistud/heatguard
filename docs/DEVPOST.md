# HeatGuard — Devpost Submission

> Use these sections to fill in the Devpost form fields. Copy-paste each section into the corresponding field.

---

## Project Name

HeatGuard

---

## Tagline

An adaptive WBGT-driven work–rest–hydration scheduler that replaces the Gulf's blunt calendar-based midday work ban with condition-responsive, standards-based, and provable heat safety for outdoor labour crews.

---

## Inspiration

Millions of migrant workers do outdoor manual labour across the Gulf where summer wet-bulb-globe temperatures routinely exceed the limits of human thermoregulation. Every Gulf state mitigates this with a **calendar-based midday work ban** — a fixed clock window on fixed calendar dates. The problem: the calendar is wrong in *both directions*.

It's **too permissive**: Dubai hit extreme WBGT in May 2025 — weeks before the UAE ban season started on 15 June. On our demo day (16 May), HeatGuard identified **12 hours** of unprotected danger. A day-0 newcomer in Riyadh needs protection from 09:00, but the Saudi ban doesn't start until noon. In Doha, Qatar's WBGT law covers midday but leaves the humid morning and late shift exposed.

It's **too restrictive**: on cooler in-season days, the ban forces work stoppages during safe hours — destroying productivity and giving employers a financial incentive to *evade* the rule entirely.

We knew the intervention (water, rest, shade) is cheap and proven — a 2024 ILO study in Nicaraguan sugarcane fields showed **~94% AKI reduction** and **10–20% productivity gains**. What's missing isn't the science. It's the **adaptive implementation and verification layer** that makes WRS schedulable, provable, and fundable at scale.

That's what HeatGuard is.

---

## What it does

HeatGuard replaces the blunt calendar ban with a **condition-responsive heat-safety system** built on occupational-health standards (ISO 7243, ISO 7933, ACGIH TLV, NIOSH). It:

1. **Senses** — takes a WBGT reading from an on-site meter (~$300) or estimates it from weather data (Open-Meteo archive/forecast via the Liljegren 2008 model).

2. **Schedules** — computes the exact work-rest cycle (minutes of work per hour) and hydration target (cups per hour, sweat-loss-based) for current conditions, work intensity, and worker acclimatization status.

3. **Signals** — broadcasts one site-wide signal: **WORK · REST IN SHADE · DRINK NOW · STOP**. A horn or light on the job site — workers don't need apps or wearables.

4. **Verifies** — logs every decision to a SHA-256 hash-chained, tamper-evident audit trail. Exportable as CSV or JSONL for compliance, ESG reporting, and development-finance audits.

### What the dashboard shows

The React supervisor dashboard provides:

- **Ban vs. Adaptive timeline** — hour-by-hour comparison of what the calendar ban does vs. what HeatGuard recommends, exposing the gap hours the ban misses
- **Acclimatization tracker** — NIOSH staged re-entry for newcomers (day 0–14), showing how a new arrival needs different protection than a veteran
- **Near-live forecast** — Open-Meteo forecast with recommended shift window (start/end times for safe outdoor work)
- **Season impact** — mechanistic model of AKI cases averted, danger hours caught, and ban coverage gaps across an entire Gulf summer
- **Business case & ROI** — payback period, ROI multiple, recovered productive hours, fine avoidance
- **Gulf-scale projection** — what happens when you deploy HeatGuard to 100,000 or 5,000,000 workers (AKI averted, lives saved, economic value)
- **What-if engine** — live `POST /decide` with sliders for temperature, humidity, solar radiation, work intensity, acclimatization, age, weight, comorbidity
- **Policy gap auditor** — TF-IDF retrieval over GCC ban regulations and ILO Water–Rest–Shade evidence (cited, extractive answers; no external LLM)
- **Worker protection record** — the tamper-evident compliance chain with privacy-by-design (no worker tracking, site-level signal)
- **Data provenance** — full manifest of committed datasets, cache status, policy corpus, and evidence files

### Four demo sites

| Site | Narrative |
|------|-----------|
| **Dubai** | May 2025 — extreme heat arrived before the UAE ban started. 12 unprotected gap hours on focus day. |
| **Riyadh** | Summer 2024 — the Saudi ban covers noon but misses the humid morning. |
| **Abu Dhabi** | May 2025 — coastal humidity drives WBGT up in the shoulder season. |
| **Doha** | Summer 2024 — Qatar's WBGT law helps at midday but not the morning or late shift. |

---

## How we built it

### Architecture: one engine, five interfaces

The entire system is built around a **single deterministic Python engine** — the scheduler,
WBGT, PHS, and compliance modules are pure functions with no hidden side effects. Weather
fetch and disk cache I/O live at the **service/API boundary** (`service.py`, Open-Meteo
client). Five thin presentation layers sit on top: CLI, FastAPI REST API, React dashboard,
Streamlit app, and Jupyter validation notebook. They all call the same `service.py`, so
every interface shows the same numbers.

### The scientific engine

| Module | What it does | Standard |
|--------|-------------|----------|
| `wbgt.py` | Outdoor WBGT from air temp, humidity, wind, solar radiation | Liljegren 2008 + Stull 2011 fallback |
| `solar.py` | Vendored NOAA cosine solar zenith (50 lines, no heavy deps) | NOAA solar position |
| `worktables.py` | ACGIH Threshold Limit Value / Action Limit step tables | ISO 7243 / ACGIH |
| `hydration.py` | Sweat-loss-based hydration targets + max safe exposure | ISO 7933 PHS via pythermalcomfort |
| `acclimatization.py` | Newcomer ramp (day 0–14 exposure caps) | NIOSH 2016 |
| `scheduler.py` | Orchestrator: three independent safety limits → most conservative wins | — |
| `calendar_ban.py` | GCC ban rules (the foil HeatGuard improves upon) | GCC labour law |
| `compliance.py` | SHA-256 hash-chained append-only audit log | — |
| `impact.py` | Mechanistic AKI model + productivity recovery | Literature-derived |
| `risk_model.py` | Gradient-boosting personal risk (advisory only, never overrides signal) | PHS-labelled |
| `policy_retrieval.py` | TF-IDF retrieval over committed GCC + ILO corpus (extractive, no LLM) | — |

The **decision pipeline** flows: Weather → `estimate_wbgt` → Conditions → `scheduler.decide` → Advisory → `compliance.append` → LogRecord (hash-chained). The scheduler takes the **most conservative** of three independent limits: the ACGIH work-rest table, the NIOSH acclimatization cap, and the PHS physiological cap.

### Frontend

The React dashboard (TypeScript, Vite, Tailwind CSS, Recharts) fetches from the FastAPI backend. A static marketing landing page introduces the problem and links to the live dashboard.

### Data pipeline

Weather data comes from **Open-Meteo** (ERA5-class reanalysis archive + hourly forecast API). All caches are **committed to the repo** under `data/cache/` so the demo runs fully offline. The `datasets.json` manifest tracks 7 Gulf cities across archive and forecast windows. A CLI command (`heatguard fetch-datasets`) refreshes all caches.

### Deployment

Docker multi-stage build (Node for Vite, Python 3.12-slim for runtime) deployed to **Google Cloud Run** via Cloud Build. Landing page at `/`, dashboard at `/dashboard/`, API at `/health`, `/demo/{site}`, etc.

---

## Challenges we ran into

- **PHS at Gulf extremes**: ISO 7933's Predicted Heat Strain model was not designed for 50°C+ air temperatures with high solar load. We hit NaN outputs and had to clamp inputs (T_r to 60°C, T_db to 50°C, wind to 3 m/s) and add a metabolic-rate floor (the standard is only valid for M ∈ [100, 450] W/m²).

- **WBGT estimation at night**: The Liljegren model requires solar radiation and a converging natural wet-bulb iteration. Below the horizon, it returns NaN. We fall back to the Stull 2011 approximation for nighttime/overcast conditions.

- **thermofeel library quirks**: Pressure must be in hPa (not Pa), WBGT is returned in Kelvin (not °C), and NaN comes back silently when the sun is below the horizon. Each of these took debugging time to discover.

- **Globe temperature recovery**: PHS needs mean radiant temperature, which we don't have directly. We back-calculate it from the WBGT components: `T_g = (WBGT - 0.7·T_nwb - 0.1·T_db) / 0.2`. This is a principled approximation but adds uncertainty.

- **numpy scalar serialization**: numpy scalars break both JSON serialization and SHA-256 hash-chain determinism. We coerce every numeric output to Python-native types.

- **ML safety**: Our gradient-boosting personal risk model must **never** override the regulatory signal — an elevated risk badge is advisory information for a supervisor, not a gate. This is unit-tested and enforced in the scheduler.

- **Nicaragua → Gulf transfer**: The intervention effect sizes come from Mesoamerican sugarcane. Physiology is universal but magnitude is uncertain. We present all projections as ranges with sensitivity analysis, and the back-test fails loudly if the underlying effect sizes change.

---

## Accomplishments that we're proud of

- **265 tests passing** — including golden-file narrative tests that break if the Dubai/Riyadh/Abu Dhabi/Doha stories change, a Nicaragua back-test that reproduces the 94% AKI reduction, and full API endpoint coverage.

- **One engine, five interfaces** — CLI, FastAPI, React, Streamlit, Jupyter all share `service.py`. No divergence between what the notebook validates and what the dashboard shows.

- **Tamper-evident compliance chain** — every advisory is logged with a SHA-256 hash linking to the previous record. Deletion or modification breaks the chain. This is the "proof of protection" that makes the system auditable for ESG, development-finance, and labour-rights reporting.

- **The calendar gap is *visible*** — the side-by-side timeline makes the failure of the calendar ban viscerally obvious. Dubai May 16: the ban lane is completely empty (ban season hasn't started), but HeatGuard's lane is lit up with REST and STOP signals.

- **Productivity-positive safety** — the ROI model shows that HeatGuard doesn't just save lives, it recovers productive hours the ban unnecessarily blocks. Riyadh ROI is 7–10×. That's the argument that gets employers to adopt.

- **Fully offline demo** — committed weather caches mean you can run the entire demo, including season replay, impact model, and forecast panel, on an airplane with no internet.

---

## What we learned

- **Standards are the moat.** Building on ISO/ACGIH/NIOSH means the system isn't a black box — it's auditable, defensible, and aligned with what occupational health professionals already use. This matters enormously for adoption in a regulated space.

- **The calendar ban isn't stupid — it's blunt.** Understanding *why* it exists (enforcement simplicity, no per-site instrumentation) helped us design a replacement that's almost as simple to operate (one signal, one sensor) but dramatically more accurate.

- **Effect-size transfer requires honesty.** The Nicaragua WRS study is our strongest evidence, but it's not Gulf construction. Presenting it as a validated range with sensitivity analysis (not a point estimate) is both more honest and more credible to judges and potential adopters.

- **Privacy-by-design is a design constraint, not an afterthought.** The compliance log is deliberately site-level, not worker-level. It proves the *employer* did the right thing — it's a protection record, not a surveillance system. This distinction shapes the entire data model.

---

## What's next for HeatGuard

| Phase | What | Why |
|-------|------|-----|
| **Pilot** | Deploy with 1–2 Gulf labour contractors on live construction sites | Validate effect sizes with real Gulf outcome data |
| **Hardware** | On-site WBGT meter + horn/light integration (IoT-simple) | Replace the weather estimate with a measured reading |
| **Checkpoints** | NFC tap at water/shade stations → feed compliance log | Prove rest and hydration *happened*, not just that they were scheduled |
| **Demographics** | Heart rate, age/weight/comorbidity in the scheduling loop | Move personal risk from advisory badge to tighter protection |
| **Transfer** | California Central Valley agriculture, Mesoamerican sugarcane, mining | Same engine, new site config + ban rules |
| **ESG/Finance** | Hash-chained compliance export for development-finance lender audits | Make heat-safety a *fundable* requirement |

---

## Built with

Python, FastAPI, React, TypeScript, Vite, Tailwind CSS, Recharts, scikit-learn, pythermalcomfort, thermofeel, Open-Meteo API, Docker, Google Cloud Run, GitHub Actions

---

## Try it out

- **Live dashboard:** https://heatguard-5ysoalxi5q-uc.a.run.app/dashboard/
- **Landing page:** https://heatguard-5ysoalxi5q-uc.a.run.app/
- **API health:** https://heatguard-5ysoalxi5q-uc.a.run.app/health
- **GitHub:** https://github.com/fcistud/heatguard
