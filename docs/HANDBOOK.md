# HeatGuard Handbook

The complete guide to HeatGuard: what it is, how every part works (explained for both
newcomers and specialists), how to run and extend it, frequently asked questions, and a
detailed roadmap of where it goes next.

This handbook is the connective tissue between the other docs:
- [`README.md`](../README.md) — the technical writeup
- [`datasets.md`](../datasets.md) — every data source + the honest gaps
- [`ROI_AND_CLAIMS.md`](ROI_AND_CLAIMS.md) — how every ROI/landing number is calculated
- [`DASHBOARD_WALKTHROUGH.md`](DASHBOARD_WALKTHROUGH.md) — the presenter's script

---

## Contents

1. [What HeatGuard is, in one minute](#1-what-heatguard-is-in-one-minute)
2. [The problem, explained](#2-the-problem-explained)
3. [The solution, explained](#3-the-solution-explained)
4. [The science, explained](#4-the-science-explained)
5. [The codebase, module by module](#5-the-codebase-module-by-module)
6. [The interfaces and how to use them](#6-the-interfaces-and-how-to-use-them)
7. [Data, assumptions, and how to tune them](#7-data-assumptions-and-how-to-tune-them)
8. [Validation and testing](#8-validation-and-testing)
9. [Honest limitations](#9-honest-limitations)
10. [FAQ](#10-faq)
11. [Roadmap and next steps](#11-roadmap-and-next-steps)
12. [Glossary](#12-glossary)

---

## 1. What HeatGuard is, in one minute

HeatGuard is an **adaptive heat-safety scheduler** for outdoor labour crews in the Gulf. It
replaces the region's fixed **calendar-based midday work ban** (e.g. Saudi Arabia: outdoor
work banned 12:00–15:00, 15 Jun–15 Sep) with a rule that responds to the *actual* heat-stress
conditions, the work intensity, and the worker.

Each hour it reads the weather (or an on-site sensor), computes the heat-stress index (WBGT),
and outputs:
- a **work-rest cycle** (how many minutes to work vs rest, per ACGIH/ISO 7243),
- a **hydration target** (how much to drink, per ISO 7933), and
- one broadcast **signal**: **WORK · REST IN SHADE · DRINK NOW · STOP**.

It enforces an acclimatization ramp for new arrivals, writes every decision into a
tamper-evident log, and turns the avoided harm into a business case. It's one pure Python
engine with five interfaces over it (CLI, API, React dashboard, Streamlit, notebook).

---

## 2. The problem, explained

### Who and where
Millions of migrant workers do outdoor manual labour across the Gulf — construction,
infrastructure, delivery. Summers there routinely push past the limits of human
thermoregulation. The Arab States host **~24 million migrant workers (41.4% of the labour
force — the highest share of any world region)**, and an estimated **~10,000 migrant deaths a
year** are recorded (all-cause; over half are certified with no underlying cause, so the
heat-attributable toll is hidden).

### What heat does to a working body
When you work hard in heat, your muscles produce heat faster than your body can shed it. To
cool down, you sweat — but sweating only works if the sweat can *evaporate*, which humidity
prevents. If cooling fails, core temperature rises, leading to heat exhaustion, heat stroke,
and a now well-documented epidemic of **acute kidney injury (AKI)** and chronic kidney disease
among manual labourers in hot climates.

### The current control is a calendar — and it's wrong in both directions
Every Gulf state runs a fixed midday ban. Because it's a *clock window on fixed dates*, it:
- **starts too late** — extreme heat now arrives in May, before the season begins;
- **misses the edges of the day** — dangerous humid mornings/evenings fall outside noon;
- **ignores the conditions** — a cool, breezy noon is banned; a brutal humid morning is allowed;
- **ignores the worker** — a day-1 unacclimatized arrival (the group that actually dies) gets
  the same protection as a 10-year veteran;
- and **over-restricts** — on cool in-season days it needlessly stops safe, productive work, so
  employers resent and evade it.

A fixed rule can't be both safe and efficient, because the underlying risk isn't fixed — it
depends on the weather, the job, and the worker.

### The deeper insight
The *intervention* science is already solved and cheap: water, rest, and shade. The La Isla
Network's Adelante Initiative in Nicaragua showed it cut kidney injury ~94% and raised
productivity 10–20%. **The gap isn't knowing what to do — it's doing it adaptively, reliably,
and verifiably.** That implementation-and-verification layer is what HeatGuard supplies.

---

## 3. The solution, explained

HeatGuard is a **site-level scheduler deployed to the supervisor**, not a wearable on every
worker. It does four things:

1. **Senses** — one on-site WBGT reading (a ~$300 meter) *or* an estimate from weather.
2. **Schedules** — the actual work-rest cycle + hydration target for the current conditions,
   work intensity, and worker.
3. **Signals** — one cheap, universally understood broadcast (a site horn/light or a phone):
   WORK / REST IN SHADE / DRINK NOW / STOP.
4. **Verifies** — a tamper-evident, hash-chained record that conditions were monitored and
   breaks/water were provided.

…plus an **acclimatization ramp** for new arrivals.

### Why site-level, not per-worker (for now)
Per-worker hardware is where adoption friction lives — cost, charging, breakage, and
surveillance concerns. One sensor per site, riding on existing infrastructure, with near-zero
marginal cost per worker, is what actually gets adopted: it gives the employer a *productivity*
story and a *liability shield* rather than a cost. (Per-worker wearables are a powerful
*next step* — see the [Roadmap](#11-roadmap-and-next-steps) — but the site-level core is the
adoptable wedge.)

---

## 4. The science, explained

This section explains each concept twice: a plain-language version, then the technical detail.

### 4.1 WBGT — the heat-stress index

**Plain:** Air temperature alone is a poor measure of danger. WBGT (Wet-Bulb Globe
Temperature) is the standard index that also accounts for **humidity, sun, and wind** — the
things that decide whether your body can actually cool itself. A humid, sunny 38 °C can be far
more dangerous than a dry, breezy 45 °C.

**Technical:** WBGT (ISO 7243) is a weighted blend of three thermometers:
```
WBGT = 0.7 · Tnwb  +  0.2 · Tg  +  0.1 · Tdb       (outdoor, with sun)
```
- **Tnwb** (natural wet-bulb) captures evaporative cooling — how well sweat can shed heat. It
  gets the **0.7 weight**, which is why humidity dominates: in humid air sweat can't evaporate,
  so the body can't cool.
- **Tg** (black-globe) captures radiant load — direct sun.
- **Tdb** is plain air temperature.

HeatGuard estimates outdoor WBGT from weather (air temp, humidity, wind, solar radiation, and
the sun's position) using the **validated Liljegren (2008) model** via ECMWF's `thermofeel`,
with a Stull natural-wet-bulb fallback at night. Or it takes a **measured** reading from an
on-site meter, which bypasses estimation. Every value carries its provenance
(`liljegren | fallback | measured`).

### 4.2 The work-rest cycle — ACGIH / ISO 7243

**Plain:** Given how hot it is (WBGT), how hard the job is, and whether the worker is
acclimatized, published safety tables say what fraction of each hour is safe to work — 100%,
75%, 50%, 25%, or STOP. Hotter or harder → more rest.

**Technical:** HeatGuard hardcodes the **ACGIH TLV** (acclimatized) and **Action-Limit**
(unacclimatized, ~3 °C stricter) screening tables. A **step lookup** by metabolic category
(light/moderate/heavy/very-heavy) returns the highest work allocation whose WBGT ceiling ≥ the
current WBGT; above the most permissive ceiling → STOP. (A separate continuous "risk score" is
shown on the UI gauge, but the legally-meaningful cycle is stepped — that's the standard's
intent and what an inspector expects.)

### 4.3 Hydration and max exposure — ISO 7933 Predicted Heat Strain

**Plain:** A physiological model simulates the worker's heat balance to predict how much they'll
sweat (so HeatGuard can tell them how much water to drink) and how long they can keep going
before overheating.

**Technical:** HeatGuard runs the **ISO 7933:2023 Predicted Heat Strain (PHS)** model via
`pythermalcomfort`. Given air temperature, radiant temperature, wind, humidity, metabolic rate,
clothing, and the worker's weight/height/acclimatization, PHS integrates the heat balance over
time and outputs core temperature, sweat loss, and the time to reach physiological limits. Two
calls per decision:
- a 60-minute call at the cycle-weighted metabolic rate → **sweat loss** (the per-hour water
  target) and end-of-hour core temperature;
- a 480-minute call at the full working rate → the true **minutes-to-limit** (the max safe
  continuous exposure), which becomes a work-fraction cap.

PHS is only valid for metabolic rate 100–450 W/m² and radiant temp ≤ 60 °C, so inputs are
clamped to that envelope (Gulf desert globe temperatures can exceed it).

### 4.4 Acclimatization — the NIOSH ramp

**Plain:** A body adapts to heat over ~1–2 weeks. A brand-new arrival is far more vulnerable —
and is the group that actually dies. So new workers should ramp up exposure gradually.

**Technical:** Per NIOSH guidance, a brand-new worker is capped at **20% of normal exposure on
day 0, rising ~20%/day to 100% by day 5**; a heat-experienced-but-new-to-the-job worker ramps
over ~2 days. While ramping, the worker is also screened against the stricter Action-Limit
table. The cap only *binds* when heat stress is actually present (a newcomer still works
normally in a cool dawn). This is **pure scheduling — zero cost — targeting the deadliest
group**.

### 4.5 The decision — most-conservative-of-three

The called work fraction is the **minimum** of:
1. the ACGIH/ISO 7243 table (regulatory),
2. the acclimatization cap (new-worker protection), and
3. the PHS physiological cap (max safe minutes ÷ 60).

**STOP** fires only when no safe block remains (under ~5 minutes) or WBGT is above the table's
most-permissive ceiling. Otherwise a work-rest cycle is prescribed, and one signal is broadcast.

### 4.6 The compliance log — a tamper-evident record

Every reading, cycle, drink prompt, water attestation, and STOP is appended to a **SHA-256
hash-chained** log: each record commits to the previous one, so any later edit or deletion
breaks the chain. It's **worker-protective first** (the worker's own immutable heat-safety
history) and a **compliance shield** second (verifiable proof against fines and liability),
and it's **privacy by design** — it records site conditions and protective actions, not
individual location, biometrics, or tracking.

### 4.7 Impact, ROI, and scale

The impact model is **mechanistic**: it credits AKI cases averted in proportion to the
dangerous hours HeatGuard catches that the calendar ban misses, anchored to the Nicaragua
effect sizes (AKI −94%, productivity +10–20%). The ROI monetises this conservatively (headline
= productivity + recovered safe work + AKI averted + fines avoided; death/turnover excluded).
The scale projection extrapolates the per-crew result to a workforce → danger-hours, AKI cases,
**lives saved**, and value. **Every term and number is documented in
[`ROI_AND_CLAIMS.md`](ROI_AND_CLAIMS.md).**

---

## 5. The codebase, module by module

One pure, deterministic Python engine (`src/heatguard/`); every interface is a thin layer over
it. The engine does no I/O — weather ingestion and exports live at the edges — which is what
makes the test suite trustworthy.

| Module | Responsibility |
|---|---|
| `types.py` | Shared frozen dataclasses + enums (`Site`, `Weather`, `Conditions`, `Worker`, `Advisory`, `Signal`, `MetabolicCategory`). |
| `solar.py` | Vendored NOAA cosine-solar-zenith calc (no heavy dependency) — needed for the WBGT model. |
| `wbgt.py` | Outdoor WBGT: Liljegren via `thermofeel` + Stull fallback + the `measured` path; carries provenance. |
| `worktables.py` | The ACGIH TLV / Action-Limit tables and the WBGT→work-fraction step mapping. |
| `hydration.py` | The ISO 7933 PHS adapter (sweat→water target + max exposure), with the validity clamps. |
| `acclimatization.py` | The NIOSH new-worker ramp. |
| `scheduler.py` | The orchestrator: `Conditions + Worker → Advisory`. |
| `calendar_ban.py` | The GCC midday-ban rules (the foil). |
| `compliance.py` | The hash-chained, privacy-by-design protection record. |
| `impact.py` | The mechanistic AKI/productivity model + the Nicaragua back-test + sensitivity. |
| `economics.py` | The business case / ROI. |
| `scale.py` | The workforce-scale / lives-saved projection. |
| `weather/` | The Open-Meteo client (archive + forecast) and the replay helpers. |
| `service.py` | Assembles the demo/timeline/impact/economics/scale payloads for every interface. |
| `cli.py`, `api.py` | The CLI and the FastAPI surface. |

The decision flow for one (worker, hour):
```
Weather --estimate_wbgt--> Conditions --scheduler.decide--> Advisory --compliance.append-->
```

---

## 6. The interfaces and how to use them

```bash
pip install -e . && pip install -r requirements.txt
pytest -q                  # the test suite
heatguard fetch-demo       # cache real Open-Meteo weather (committed; run once)
scripts/run_demo.sh        # API + dashboard in one command
```

- **CLI** — `heatguard demo dubai|riyadh` (the narrative), `roi`, `backtest`, `decide`
  (one-off decision from explicit conditions), `fetch` / `fetch-demo`, `sites`.
- **FastAPI** (`uvicorn heatguard.api:app`) — `/demo/{site}`, `/timeline/{site}/{date}`
  (with `?intensity=&newcomer_days=`), `/hour/{site}/{date}/{hour}` (per-worker recompute,
  `?measured_wbgt=`), `/impact`, `/economics`, `/sensitivity`, `/scale`, `/backtest`,
  `/compliance/{site}/export`, `POST /decide`. Interactive docs at `/docs`.
- **React dashboard** (`web/`) — the primary UI: the "how to read this" explainer, the danger
  & scale panel, the live signal, the WBGT gauge with an Estimated⟷Measured toggle, the
  calendar-ban-vs-HeatGuard timeline with per-worker controls, the interactive acclimatization
  tracker, season impact, the business-case panel, the worker-protection record, and a live
  what-if.
- **Streamlit** (`streamlit run streamlit_app.py`) — the same story, pure-Python, no build.
- **Notebook** (`notebooks/heatguard_validation.ipynb`) — the narrated validation with charts.
- **Landing page** (`landing/index.html`) — the marketing explainer.

---

## 7. Data, assumptions, and how to tune them

- **Weather** — free Open-Meteo reanalysis (archive) + forecast, cached under `data/cache/` so
  the demo runs offline. Swappable for ERA5/CDS or a national met feed.
- **Sites** — `data/locales.json` (lat/lon/elevation/timezone/country). Add any site.
- **Standards** — ACGIH tables, ISO metabolic categories, NIOSH ramp are in code.
- **Intervention effect sizes** — `data/nicaragua_baseline.json` (AKI −94%, productivity
  +10–20%, the baseline AKI incidence, the cost items).
- **Economic assumptions** — `data/economics.json` (worker-day value, AKI cost, fine, death
  cost, turnover). All **deliberately conservative and tunable**; see `ROI_AND_CLAIMS.md` for
  each one's basis and caveat.

Full source list and the honest "what's NOT available" gaps are in `datasets.md`.

---

## 8. Validation and testing

- **81 automated tests** (`pytest`) — table values, WBGT/PHS sanity, the acclimatization ramp,
  the scheduler logic, tamper detection, the mechanistic impact, the economics, the scale
  projection, and the full API surface.
- **Nicaragua back-test** (`heatguard backtest`) — asserts the impact model reproduces the
  documented La Isla / Adelante outcome (AKI −94%, productivity +10–20%); fails loudly if an
  effect size is ever changed.
- **GitHub Actions CI** runs the tests + the React build on every push and PR.
- **Adversarial code review** of the engine (units, edge cases, scaling) was run and its
  findings fixed.

---

## 9. Honest limitations

- **WBGT estimation is approximate** without an on-site black-globe sensor; the production path
  uses a ~$300 meter, and the dashboard exposes an Estimated⟷Measured toggle.
- **Effect sizes transfer** from Mesoamerican sugarcane to Gulf construction with uncertainty;
  the documented "94%" is a highest-risk-subgroup figure, and the baseline AKI incidence is a
  tunable assumption shown as a range.
- **The ROI** rests on illustrative, conservative cost/value assumptions (the AKI-cost proxy is
  higher than the cited clinical figure; the death-averted and turnover terms are excluded from
  the headline).
- **Work intensity** is a supervisor input (now selectable per worker).
- **The genuinely hard problem is adoption and enforcement**, which is why HeatGuard leads with
  the productivity and compliance-shield framing.
- **It is a prototype, not certified safety equipment.**

---

## 10. FAQ

**Why not put a wearable on every worker?**
Cost, charging, breakage, and surveillance concerns kill per-worker hardware adoption. One
sensor per site, near-zero marginal cost per worker, is the adoptable wedge. Wearables are a
strong *next step* for personalisation and enforcement — see the roadmap.

**Is WBGT accurate without a sensor?**
The estimate uses the validated Liljegren model from real weather; it's good for the calendar-
vs-adaptive comparison and the demo. For an operational deployment you drop in a cheap on-site
meter and the same engine runs on the measured value — the dashboard shows both side by side.

**How is "lives saved" calculated, and is it real?**
It's AKI-cases-averted × a conservative death-per-AKI severity ratio, scaled to a workforce.
It's the most assumption-laden number and is labelled *illustrative/conservative* everywhere.
The per-crew danger-hours and AKI-averted figures (derived on real weather) and the Nicaragua
back-test are the verifiable backbone. See `ROI_AND_CLAIMS.md`.

**Does it need the internet?**
No — the demo weather is cached in the repo, so everything runs offline.

**What standards is it built on?**
ISO 7243 (WBGT), ISO 7933 (Predicted Heat Strain), ISO 8996 (metabolic rate), the ACGIH
TLV/Action-Limit screening tables, and NIOSH acclimatization guidance.

**Is the Nicaragua → Gulf transfer valid?**
Directionally yes (the physiology is universal), but with real uncertainty in magnitude — the
sectors and climates differ. We're explicit about it, show the AKI assumption as a range, and
flag it as the headline area to validate with a Gulf pilot.

**Won't employers just game it / not enforce it?**
The hash-chained record makes monitoring and breaks *verifiable* (the compliance shield), which
raises the cost of non-compliance. But enforcement is ultimately the hard part — which is one
reason wearable-based confirmation of breaks (roadmap) is valuable.

**Why does the calendar ban "miss" so much?**
It's a clock window. WBGT (which captures humidity and sun) can be lethal at 9 a.m. or in May,
outside the noon-in-season window; and a cool in-season noon is needlessly banned.

**Can it handle other regions or sectors?**
Yes — sites, weather sources, the ban rules, and work intensities are all configurable. The
engine is generic occupational heat-stress; agriculture and logistics are natural extensions.

**What does it cost?**
~$95/worker/season in the modelled program (mostly one-time capital) plus a ~$300 on-site WBGT
meter per site. The modelled ROI is 3–10×.

**What about privacy?**
The compliance log records *conditions and protective actions*, not individual location,
biometrics, or continuous tracking. The only identifier is a worker/crew id the operator
controls and can pseudonymise.

**What happens at the edges of the physiological model (e.g. extreme humidity)?**
Inputs are clamped to the ISO 7933 validity envelope; if the model still can't solve, HeatGuard
falls back to a conservative estimate and the regulatory table remains the backstop — PHS can
only *tighten* the schedule, never loosen it.

---

## 11. Roadmap and next steps

The site-level scheduler is the adoptable core. Each step below **layers onto the existing
engine** — the `Worker` dataclass already carries weight, height, days-on-job, and
acclimatization status, and the PHS model already consumes them, so personalisation is mostly a
matter of *feeding better per-worker inputs and closing the loop with measurement*.

### 11.1 Cheap wearables for personalisation and enforcement
**What:** a low-cost per-worker tag — a passive **NFC** wristband, or a cheap **BLE** band —
read at the water station and at break checkpoints.
**Why:** it adds the two things a site-level system can't do alone — *per-worker
personalisation* and *enforcement verification* — without the cost/friction of a full
physiological wearable.
**How it plugs in:**
- *Enforcement*: tap-to-confirm a worker actually took the called break and drank at the
  station → those events append to the existing `compliance.py` hash chain, turning "breaks
  were provided" into "breaks were *taken*" — a far stronger record for an inspector or a
  lender's ESG audit.
- *Personalisation*: the tag identifies the worker, so the scheduler can use that worker's real
  `days_on_job` (acclimatization tenure) and body metrics instead of a crew default — the
  `Worker` fields the engine already accepts.
**Tradeoffs:** even cheap tags add hardware and a tap workflow; keep them *at fixed
checkpoints* (station/gate), not worn continuously, to minimise friction and surveillance
concerns. Frame the data as worker-protective (their own break/hydration record).
**Phasing:** start with hydration-verification tags at the water station (the optional premium
layer already in the design), then add break-confirmation checkpoints.

### 11.2 Demographic personalisation
**What:** tailor the physiological inputs to the worker's anthropometrics — body weight,
height, BMI, age — drawn from a worker profile and/or origin-country distributions.
**Why:** sweat rate, heat storage, and strain depend strongly on body size and fitness. PHS
already takes `weight_kg`/`height_m`; today the demo uses a 75 kg / 1.75 m default. Real values
sharpen the hydration target and the max-exposure cap per worker.
**How it plugs in:**
- A simple per-worker profile (entered once, or from an HR system) sets the PHS body inputs.
- Where individual data is missing, **origin-country anthropometric distributions** (e.g. DHS
  surveys for Nepal/Bangladesh/India/Pakistan — see `datasets.md`) give better priors than a
  single default. The known data gap: recent DHS rounds under-measure adult *male*
  anthropometry, so this needs a real measurement partnership.
**The ethical guardrail:** this must personalise *protection*, never *screening*. The Nicaragua
research is explicit that hiring only "resilient" workers fails — preventing exposure is the
answer. HeatGuard would use demographics to make a *more vulnerable* worker *more* protected,
never to exclude anyone or to push a higher-risk worker harder.
**Phasing:** opt-in worker profiles first (weight/height/age), then population priors for
gap-filling, with a clear anti-discrimination policy.

### 11.3 Heart-rate or sweat-rate integration (closing the physiological loop)
**What:** feed *measured* physiological signals — heart rate from a cheap chest strap or
wrist optical sensor, and/or hydration loss from a sweat-rate patch or pre/post-shift
body-mass weigh-in — back into the engine.
**Why:** today HeatGuard *predicts* sweat rate and core temperature (ISO 7933). Real sensors
**close the loop**: they let the system compare predicted vs measured strain and act on the
individual's *actual* state, upgrading from a site-level predictive schedule to per-worker
measured-strain protection with real-time alarms.
**How it plugs in (grounded in standards already in the project):**
- **Heart rate** is the cheapest, most mature signal. ISO 8996 already defines a *heart-rate
  method* for estimating metabolic rate, and ISO 9886 defines physiological strain monitoring
  (heart rate, core temperature, body-mass loss). Sustained HR above an age-adjusted limit, or
  poor HR recovery during a rest break, is a direct individual strain alarm — it would trigger
  an individual DRINK/REST/STOP overriding the site signal for that worker, and could feed back
  a better real-time metabolic-rate estimate (replacing the supervisor's intensity guess).
- **Sweat / body-mass loss** directly measures dehydration — the thing the hydration target is
  trying to prevent. A pre/post-shift weigh-in (near-zero cost) validates and calibrates the
  PHS sweat prediction; a continuous sweat patch enables per-worker hydration alarms.
**Tradeoffs:** this is where wearable cost, comfort, charging, and surveillance friction are
highest — so it's the *premium tier*, best justified on the highest-risk crews or as a
calibration study, not a universal mandate.
**Phasing:** (1) pre/post-shift weigh-ins to validate the sweat model (cheap, high-value
science); (2) heart-rate straps on a pilot crew to add individual strain alarms and improve the
metabolic-rate input; (3) optional continuous sweat sensing for the highest-risk roles.

### 11.4 Other near-term steps
- **On-site sensor + signal hardware**: a ~$300 WBGT meter and a relay to a site light/horn —
  the production version of the `measured` path and the broadcast signal.
- **A Gulf pilot** with a labour-supply contractor to validate the effect-size transfer and the
  ROI against real outcomes (the single most important credibility step).
- **Development-finance pathway**: lenders and ESG mandates already attach occupational-safety
  conditions; HeatGuard is the affordable implementation-and-verification layer that satisfies
  them.
- **Close the data gap**: there is almost no public Gulf worker-heat data — partner to collect
  it (and contribute it back).
- **Multi-sector / multi-region**: extend to agriculture and logistics, and to other
  heat-exposed regions, by swapping the site config, weather source, and ban rules.
- **Forecast-driven planning**: use the Open-Meteo forecast endpoint to pre-plan the next day's
  schedule (e.g. start earlier on a brutal day), not just react hour by hour.

---

## 12. Glossary

- **WBGT** — Wet-Bulb Globe Temperature; the standard occupational heat-stress index (ISO 7243),
  combining humidity, radiant/sun load, and air temperature.
- **PHS** — Predicted Heat Strain (ISO 7933); a physiological model of core temperature and
  sweat loss over time.
- **TLV / Action Limit** — ACGIH screening thresholds for acclimatized / unacclimatized workers.
- **Acclimatization** — the body's ~1–2-week adaptation to heat; new arrivals are most at risk.
- **AKI** — Acute Kidney Injury; the kidney damage caused by repeated heat-and-dehydration
  exposure during manual labour.
- **Metabolic category** — the work intensity (light/moderate/heavy/very-heavy), per ISO 8996.
- **The calendar ban** — the Gulf's fixed midday outdoor-work prohibition (the system HeatGuard
  replaces).
- **The signal** — the single hourly broadcast: WORK / REST IN SHADE / DRINK NOW / STOP.
