# Datasets, Research & Validation

What data HeatGuard actually uses, what's available in the wider domain, what it rests on
for validation — and, just as importantly, **what is not available**. Access is tagged
**[free]**, **[free+reg]** (free with a registration/licence), **[paid]**, or
**[restricted]** (no usable open access). Each source is also tagged by how HeatGuard
relates to it: **uses-now**, **could-use**, or **reference**.

> Findings below were gathered by web research and then **adversarially verified**; the
> corrections that survived that pass are folded in, and genuine uncertainties are flagged.
> Net assessment: the *physics* runs on free, open code + free reanalysis weather; the
> *standards* that define the science are mostly paywalled (but reimplemented in open
> libraries); and **granular Gulf worker exposure/health data is essentially a public void**
> — the single biggest gap, and one HeatGuard names rather than hides.

---

## 1. Data HeatGuard ships and uses *now*

Everything needed to run the demos is **in the repo** and works **offline**.

| Asset | What it is | Access |
|---|---|---|
| `data/cache/dubai_2025-05-01_2025-09-15.json` | 3,312 hourly rows, Dubai (25.20 N, 55.30 E), Open-Meteo archive | committed |
| `data/cache/riyadh_2024-06-01_2024-09-15.json` | 2,568 hourly rows, Riyadh (24.71 N, 46.69 E) | committed |
| Variables in each | `temperature_2m` (°C), `relative_humidity_2m` (%), `wind_speed_10m` (m/s), `shortwave_radiation` (W/m²), `direct_radiation` (W/m²), `dew_point_2m` (°C), `surface_pressure` (hPa) | — |
| `data/locales.json` | 7 demo sites (lat/lon/elevation/tz/country) | committed |
| `data/nicaragua_baseline.json` | Intervention effect sizes + cost items (see §6, §9) | committed |
| `data/economics.json` | ROI assumptions (see §9) | committed |
| In-code standards | ACGIH TLV/Action-Limit WBGT tables; ISO 8996 metabolic categories; NIOSH acclimatization ramp | hard-coded |

Engine dependencies actually imported: **`pythermalcomfort==4.0.1`** (ISO 7933 PHS),
**`thermofeel==2.2.0`** (Liljegren WBGT), `numpy`, `httpx`.

---

## 2. Climate & WBGT data — *confidence: high*

The physics runs entirely on free reanalysis weather + open WBGT code. WBGT itself is
**computed in-process** (no public Gulf WBGT grid exists at the hourly resolution a
scheduler needs).

| Source | Access | Use | Notes |
|---|---|---|---|
| **Open-Meteo Historical (Archive) API** — `archive-api.open-meteo.com/v1/archive` | free | **uses-now** | Key-less ERA5/ERA5-Land reanalysis, hourly, **1940→present**, global. All 7 variables confirmed; wind requestable in m/s, pressure in hPa. |
| **Open-Meteo Forecast API** — `api.open-meteo.com/v1/forecast` | free | **uses-now** | Same variables; near-live signal (`fetch_forecast`). Not cached in-repo (hits network). |
| **ERA5 single-levels** (Copernicus CDS) | free+reg | could-use | The authoritative source Open-Meteo repackages. 0.25° (~28 km), hourly, 1940→. Needs ECMWF/CDS account + per-dataset Copernicus licence; bulk requests queue; ERA5T ~5-day, final ERA5 ~2–3-month latency. |
| **ERA5-Land** (Copernicus CDS) | free+reg | could-use | Land-only, 0.1° (~9–11 km), hourly, 1950→. Same registration/latency. |
| **ERA5-HEAT** (C3S thermal-comfort) | free+reg | reference | ⚠️ **Contains UTCI + mean-radiant-temperature only — NOT WBGT.** Common misconception; there is no official Copernicus WBGT variable. Now spans 1940→near-real-time. |
| **`thermofeel`** (ECMWF, Apache-2.0) | free | **uses-now** | `calculate_wbgt_liljegren` — the project's WBGT solver. Quirks already handled: pressure in **hPa** (Pa→NaN), output in **Kelvin**, **NaN when sun below horizon**. |
| **Brimicombe global WBGT grid** (Zenodo, CC-BY) | free | could-use | `zenodo.org/records/8021197`. Global, ERA5 grid, **daily** max/mean/min, **1979–2021**. Good for climatology/back-testing; daily-only + ends 2021, so not for hourly scheduling. |
| **OSHA Outdoor WBGT Calculator** | free | reference | Liljegren-based point estimator — sanity-check our `thermofeel` output against an independent implementation. |
| **Liljegren et al. (2008) reference C code** (`github.com/mdljts/wbgt`) | free | reference | Original Argonne algorithm; the paper itself is paywalled. Carries a UChicago-Argonne software notice (exact redistribution terms unverified). |
| **Gulf national met services** (UAE NCM, Saudi NCM/PME, Qatar Met) | restricted | reference | Public consumer feeds only; **no documented open historical/station archive or bulk API.** Effectively unusable as an engine backbone. |

**Verifier notes:** ERA5 is 0.25° (~28 km at the equator, not "31 km"); ERA5-HEAT now
extends back to 1940 (originally 1979). Open-Meteo's free tier is **non-commercial only**,
rate-limited (≈600/min, 5k/hr, 10k/day, ~300k/month) under **CC-BY 4.0** — a paid
subscription is required if HeatGuard is ever commercialised.

---

## 3. Physiological standards & software libraries — *confidence: high*

The standards that *define* the science are mostly paywalled; HeatGuard runs them via free
reimplementations and hard-coded (publicly-reproduced) values.

| Source | Access | Use | Notes |
|---|---|---|---|
| **ISO 7933:2023** — Predicted Heat Strain | paid (~CHF 159) | **uses-now** | Run free via `pythermalcomfort.phs`. Valid envelope: M ∈ [100, 450] W/m², bounded tdb/tr/v/clo. |
| **ISO 7243:2017** — WBGT assessment | paid (~CHF 100) | reference | 18 pp. WBGT math implemented via thermofeel/Liljegren — no need to buy. |
| **ISO 8996:2021** — metabolic rate | paid (~CHF 159) | reference | We hard-code categories (rest/light/moderate/heavy/very-heavy in met units, 1 met = 58.15 W/m²). |
| **ISO 9920:2007** — clothing insulation | paid (~CHF 227) | reference | Unused as tables; we hard-code a single `clo = 0.6` (coveralls + hard hat). Under systematic review. |
| **ACGIH TLV / Action-Limit** WBGT screening tables | paid | **uses-now** | ⚠️ **Copyrighted, NOT freely redistributable.** The numeric thresholds are reproduced publicly with attribution (e.g. CCOHS); HeatGuard hard-codes those values. |
| **NIOSH 2016-106** — Occupational Exposure to Heat | **free** | **uses-now** | The one unrestricted standard in the stack (US public domain). Our acclimatization ramp follows it. |
| **`pythermalcomfort`** (MIT, v4.0.1) | free | **uses-now** | PHS per ISO 7933:2023. We use `phs`, deliberately *not* its `wbgt` (which needs twb/tg inputs). |
| **`thermofeel`** (Apache-2.0, v2.2.0) | free | **uses-now** | Liljegren WBGT (see §2). |
| **`pywbgt`** (GPL-3.0) | free | could-use | The most feature-complete open WBGT lib (3 algorithms), but **GPL is a license mismatch** for this MIT project. |

To *own* the full ISO set (7243 + 7933 + 8996 + 9920) costs **≈ CHF 645**. None of it is
needed to run HeatGuard — but conformance auditing would need the authoritative texts.

**Honest deviation:** our experienced-worker ramp (`[0.50, 1.00]` over 2 days) is *more
permissive than NIOSH* on days 2–3 (NIOSH: ≤20%/day, reaching 100% by day 5, within an
overall 7–14-day acclimatization). It's a deliberate simplification, flagged here.

---

## 4. Worker demographics, anthropometrics & exposure — *confidence: high*

Population scaling is well-served and mostly free; **individual exposure/anthropometry for
Gulf workers is the void.**

| Source | Access | Use | Notes |
|---|---|---|---|
| **ILO Global Estimates on Migrant Workers** (3rd ed., 2021/ref. 2019) | free | reference | Arab States hosted **~24M migrant workers (2019)**, 41.4% of its labour force — the highest share of any region. Bloc-level only. |
| **ILOSTAT — Labour Migration (ILMS)** | free | could-use | Country-level; **construction-sector granularity for the Gulf is thin** (inconsistent administrative data). |
| **KNOMAD / World Bank migration matrices** | free | could-use | Origin×destination corridors → nationality mix for population scaling; no occupation/health. |
| **World Bank Microdata Library** (incl. KNOMAD-ILO migration-cost surveys) | free+reg | could-use | Worker demographics; no anthropometry or exposure. |
| **DHS Program** (Nepal, Bangladesh, India NFHS, Pakistan) | free+reg | **uses-now** (priors) | Body-weight/height distributions for origin countries. ⚠️ **Recent rounds measure height/weight mainly for women 15–49 and under-5 children; adult-MALE anthropometry is largely absent** (some rounds have a male biomarker subsample). Redistribution prohibited. |
| **Bates & Schneider 2008** — UAE construction hydration/workload | free | reference | Open-access, but **n = 22**, one site; per-worker data not released. |
| **FAME Laboratory / Qatar heat-stress study (2019)** | restricted | reference | 5,500+ work-hours; methodology public, **dataset not downloadable**. |
| **Pradhan et al. 2019** — Nepali cardiac mortality in Qatar | restricted | reference | Ecological mortality study; no individual exposure/anthropometry. |
| **Nepali-returnee CKD risk** (medRxiv preprint, 2025) | free | reference | ⚠️ Found **low measured CKD prevalence / no migration-status association** — weak/null evidence, returnees not in-Gulf exposure; preprint, unverified figures. |

---

## 5. Intervention effect sizes & heat-health epidemiology — *confidence: high*

HeatGuard's impact model rests on the La Isla Network **Adelante Initiative** at Ingenio San
Antonio (ISA), Nicaragua. The effect sizes are real and peer-reviewed — but **more specific
than a flat multiplier implies** (read §9 before quoting them).

| Source | Access | Use | Notes |
|---|---|---|---|
| **Hansson et al. 2025**, *Occupational & Environmental Medicine* (kidney outcomes) | free | **uses-now** | ~1,044 cane workers, 2017/18–2020/21. The **"94%"** is the decline in **incident kidney injury among the highest-risk subgroup (burned cane cutters), harvest 1 → harvest 3/4** — *not* a whole-workforce effect. The narrower AKI rate fell ~60% (20→8 per 1,000 worker-months). |
| **Hansson et al. 2024**, *Annals of Work Exposures and Health* (productivity) | free | **uses-now** | The **10–20%** band rounds subgroup gains (~9% burned cane cutters, ~19% seed cutters), measured harvest-over-harvest. Worker-level data "on reasonable request." |
| **Schlader et al. 2025**, *Annals of Global Health* (economics) | free | **uses-now** | ⚠️ Documented mill-hospital **AKI treatment cost = $253.48** (our `economics.json` uses $1,200 — see §9). ROI framings: $1.02/$1 5-yr average, $1.60/$1 by 2022, **negative in years 1–2**; the "22%" is an ILO/LIN summary number. |
| **ILO — *Heat at work*** (2024) | free | uses-now | Secondary repackaging of the LIN studies (the 94%/10–20% are not independent of the papers above). |
| **Butler-Dawson et al. 2019** — Guatemala sugarcane AKI | free | could-use | Cross-shift/biochemical AKI runs far higher than clinical AKI — frames our `baseline_aki_incidence`. |
| **Lancet Countdown** heat & labour-capacity portal; **Kjellstrom et al.** ERFs | free | could-use / reference | Global heat-productivity exposure-response functions (calibrated mainly on outdoor-worker studies). |
| **Global CKD cost reviews** (e.g. Chen et al. 2023) | free | reference | CKD/dialysis costs are downstream + high-income-skewed — not occupational-AKI treatment cost. |

**Naming:** La Isla / OEM term the program **RSHH / RSH-S** (Rest-Shade-Hydration[-Hygiene/
Sanitation]); the repo's `nicaragua_baseline.json` calls it "Water-Rest-Shade (WRS)" — same
program, different label.

---

## 6. Regulatory specs & validation references — *confidence: high*

Every GCC ban window/season encoded in `calendar_ban.py` was verified against official or
authoritative secondary sources, with two refinements.

| State | Instrument | Window / season | Penalty |
|---|---|---|---|
| Saudi Arabia | MHRSD annual decision | 12:00–15:00, 15 Jun–15 Sep | fine amount not officially stated |
| UAE | **Ministerial Resolution 44 of 2022** (MOHRE) | 12:30–15:00, 15 Jun–15 Sep | **AED 5,000/worker, max 50,000** ✓ |
| Kuwait | **Admin Resolution 535/2015** (PAM) | 11:00–16:00, 1 Jun–31 Aug | not disclosed |
| Oman | **MoL Decision 286/2008** | 12:30–15:30, 1 Jun–31 Aug | figures vary (don't cite a single number) |
| Bahrain | **Min. Res. 3/2013** (amended 11/2025; Decision 5/2026) | 12:00–16:00, 15 Jun–31 Aug | up to BHD 1,000 + up to 3 months prison (reported) |
| Qatar | **Ministerial Decision 17 of 2021** | 10:00–15:30, 1 Jun–15 Sep **+ WBGT > 32.1 °C** year-round stop (31.1 °C monitor) | — |

- Qatar is the **only** GCC state with a WBGT trigger; **32.1 °C is widely argued to be too
  high** (HRW notes severe strain at wet-bulb 30–32 °C). The prior rule was Min. Decision
  16 of 2007. **Bahrain's season is a moving target** year to year; our encoded 15 Jun–31
  Aug matches the 2026 decision.
- **Advocacy / documentation:** HRW *"Gulf States: Protect Workers from Extreme Heat"* (Jun
  2025) and *"…Serious Risk from Dangerous Heat"* (May 2023); FairSquare / Vital Signs
  *"Killer Heat"* and *"The Deaths of Migrants in the Gulf"*; Amnesty International on Qatar
  death-certification. All **free**, all **advocacy syntheses** (no measurement datasets).
- **WBGT-estimator validation:** Liljegren (2008), Kong & Huber (2024, zero-iteration
  analytic WBGT), OSHA/NIOSH calculators — all validate estimators against *models or US
  measurements*, **never against in-situ Gulf WBGT instruments**.

---

## 7. The honest gaps — what is *not* available

The most important section. These are real voids, not oversights:

- **No public hourly Gulf WBGT dataset.** The only open global WBGT grids (Brimicombe/Zenodo)
  are **daily** and end **2021**. WBGT is modelled from reanalysis, never measured on-site.
- **No public Gulf WBGT-meter ground truth.** Qatar mandates WBGT-based stoppage but doesn't
  publish the underlying site measurements; no GCC state releases instrument time-series.
- **ERA5-HEAT has no WBGT** (UTCI + MRT only) — there is no official reanalysis WBGT variable.
- **Near-total Gulf worker-exposure evidence void.** A 2025 systematic review found **only 1
  of 19** migrant-worker heat studies (2,293 workers) came from the entire Gulf region.
- **No open individual-level Gulf exposure dataset** (the defining studies don't release
  per-worker data); **no public Gulf worker sweat-rate or fluid-balance dataset**.
- **Adult-male anthropometry is largely missing from DHS** (recent rounds focus on women
  15–49 and under-5s) — so body-mass priors for the (overwhelmingly male) workforce are thin.
- **No open AKI/CKDu incidence registry** for Gulf migrant workers; evidence is fragmentary
  (returnee surveys, single-clinic observations).
- **Migrant heat-death data is structurally unavailable.** The oft-cited ~10,000 deaths/year
  is **all-cause**, many certified as "cardiac arrest"/"natural causes" without autopsy, so
  heat-attributable mortality is indeterminate.
- **Primary legal texts are hard to ingest.** Government portals block automated fetch
  (spa.gov.sa → 403; u.ae/mohre.gov.ae time out); Saudi & Kuwait fine amounts aren't
  officially published; windows/seasons drift year to year (Bahrain especially).
- **The standards are paywalled** (ISO ≈ CHF 645 for the set; ACGIH tables copyrighted) — fine
  for running the engine, a constraint for formal conformance auditing.
- **Open-Meteo's free tier is non-commercial**; a production/commercial deployment needs a paid
  subscription or a direct ERA5/CDS pipeline.

---

## 8. Provenance caveats in the repo's tunable assumptions

The verifier flagged where shipped numbers are illustrative rather than directly sourced.
All live in `data/economics.json` / `data/nicaragua_baseline.json` and are **meant to be
tuned**; this is the honest accounting:

| Assumption | Shipped value | Status |
|---|---|---|
| `aki_case_cost_usd` | $1,200 | The peer-reviewed ISA mill-hospital AKI treatment cost is **$253.48**. Our figure is a higher proxy for medical + lost-time + replacement; **not the cited clinical cost.** |
| `baseline_aki_incidence` | 0.10 / worker-season | **Definition-dependent and ambiguous**: cross-shift biochemical AKI runs 45–98%/season; clinically-diagnosed AKI is far rarer. 0.10 is a deliberately conservative midpoint, shown as a sensitivity range in the app. |
| `heat_death_cost_usd` / `heat_death_per_aki_case` | $150,000 / 0.005 | **Not grounded in a Gulf-specific source** (no published value-of-statistical-life for GCC migrant workers was found). Excluded from the headline ROI for this reason. |
| AKI "−94%" | effect size | A **highest-risk-subgroup, harvest-over-harvest** figure — not whole-workforce. The mechanistic model scales it by danger-coverage, but the headline should be quoted with this nuance. |
| Effect-size transfer | Nicaragua → Gulf | **All** hard effect-size and cost data are Central-American sugarcane; transfer to Gulf construction carries real uncertainty. |
| Intervention name | "Water-Rest-Shade (WRS)" | La Isla terms it **RSHH / RSH-S**. |

---

## 9. Summary: availability at a glance

| Need | Best available | Access | Verdict |
|---|---|---|---|
| Hourly Gulf weather | Open-Meteo archive/forecast; ERA5/CDS | free / free+reg | ✅ solid |
| Outdoor WBGT from weather | thermofeel (Liljegren), pywbgt | free | ✅ solid (modelled) |
| Hourly Gulf WBGT grid | Brimicombe (daily, ≤2021) | free | ⚠️ partial only |
| On-site Gulf WBGT measurements | — | — | ❌ not public |
| Heat-strain / work-rest standards | ISO 7933/7243/8996, ACGIH, NIOSH | mostly paid; NIOSH free | ✅ implemented in code |
| Worker population scaling | ILO, ILOSTAT, KNOMAD | free | ✅ solid |
| Worker anthropometry (male) | DHS | free+reg | ⚠️ thin for adult men |
| Gulf worker heat exposure (individual) | — | — | ❌ near-total void |
| Intervention effect sizes | La Isla / Adelante (Hansson, Schlader) | free | ✅ real, but subgroup-specific |
| Gulf AKI/heat-death incidence & cost | — | — | ❌ not available |
| GCC ban regulations | Official + HRW/FairSquare | free | ✅ verified (specs accurate) |

**Bottom line:** the science and the weather are free and open; the worker-side ground truth
for the Gulf is the gap — which is exactly why HeatGuard pairs an estimate with a *measured*
WBGT path and treats its impact assumptions as tunable, sensitivity-tested inputs rather than
settled facts.
