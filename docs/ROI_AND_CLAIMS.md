# ROI & Claims — methodology and provenance

Every ROI figure and every landing-page claim, with **how it's calculated, where the
numbers come from, and how certain they are.** This is the honesty backbone: it
separates *standards/measured facts* from *model-derived results* from *illustrative,
assumption-dependent projections*.

Confidence tags used below:
- **[STANDARD]** — a published standard, regulation, or peer-reviewed effect size.
- **[CONTEXT]** — an external statistic, cited (see `datasets.md` for sources).
- **[DERIVED]** — computed by the HeatGuard engine on **real Open-Meteo weather**; reproducible.
- **[ILLUSTRATIVE]** — depends on tunable, deliberately conservative assumptions; directional, not a promise.

All ROI logic lives in `src/heatguard/economics.py`; all assumptions in
`data/economics.json`; the impact inputs in `src/heatguard/impact.py`; the scale
projection in `src/heatguard/scale.py`. The numbers below regenerate with
`heatguard roi dubai` / `heatguard roi riyadh`.

---

## Part 1 — How the ROI is calculated

### 1.1 The assumptions (`data/economics.json`) — all **[ILLUSTRATIVE]**, all tunable

| Assumption | Value | Meaning / basis |
|---|---|---|
| `daily_value_per_worker_usd` | **$30** | Loaded value of a worker-day to the contractor (wage + overhead + output). Deliberately conservative for low-wage Gulf labour. |
| `work_hours_per_day` | **8** | → hourly value = 30 / 8 = **$3.75 / worker-hour**. |
| `aki_case_cost_usd` | **$1,200** | Cost of one acute-kidney-injury case avoided (medical + lost time + replacement). ⚠️ The peer-reviewed Nicaragua **mill-hospital AKI treatment cost is $253.48** (Schlader 2025); $1,200 is a higher proxy for total burden, not the clinical bill. |
| `fine_per_worker_usd` | **$1,361** | AED 5,000 (the UAE midday-ban fine per worker) in USD. **[STANDARD]** |
| `fine_probability_per_season` | **0.03** | Expected per-season probability of a fine the tamper-evident log helps avoid. |
| `heat_death_cost_usd` | **$150,000** | Settlement + investigation + reputational cost per heat death. **Not grounded in a Gulf-specific source** → excluded from the headline. |
| `heat_death_per_aki_case` | **0.005** | Deaths per AKI case (severity ratio). Conservative; also drives "lives saved". |
| `turnover_cost_per_worker_usd` / `turnover_reduction` | **$150 / 10%** | Recruitment cost and the share reduced by better conditions. Excluded from the headline. |

The **baseline AKI incidence** (`data/nicaragua_baseline.json`, default **0.10/worker-season**)
is the single biggest lever; it is shown as a *range* (5%–20%) in the sensitivity chart, not a point.

### 1.2 The impact inputs (`impact.py`) — **[DERIVED]** on real weather

For a 100-worker crew over the replayed season, the engine produces:
- `danger_hours_caught_vs_ban` — hours HeatGuard called STOP/REST that the calendar ban missed.
- `aki_cases_averted_vs_ban` = `0.94 × baseline_cases × (danger missed by ban / total danger)`
  — the **mechanistic** AKI model. `baseline_cases = 0.10 × crew = 10`. The 0.94 is the Nicaragua effect size. **[STANDARD × DERIVED]**
- `productivity_worker_hours_lo/hi` = `(0.10 … 0.20) × heat-exposed worker-hours`.
- `ban_only_safe_work_hours` — safe work the ban needlessly stopped (fraction-weighted).

### 1.3 The benefit terms (`economics.business_case`)

```
hourly_value      = daily_value_per_worker / work_hours_per_day            = $3.75

productivity_value      = productivity_worker_hours   × hourly_value
recovered_safe_work     = ban_only_safe_work_hours × crew × hourly_value
aki_value               = aki_cases_averted_vs_ban  × aki_case_cost
fines_avoided           = fine_per_worker × crew × fine_probability_per_season

# reported SEPARATELY, EXCLUDED from the headline (avoid over-claiming):
death_averted           = aki_cases_averted_vs_ban × heat_death_per_aki_case × heat_death_cost
turnover                = turnover_cost_per_worker × crew × turnover_reduction

headline_benefit = productivity_value + recovered_safe_work + aki_value + fines_avoided
program_cost     = capital ($55/worker) + recurring ($40/worker)            = $95/worker
ROI              = headline_benefit / program_cost
payback_days     = program_cost / (headline_benefit_lo / season_days)
```

Program cost itemisation (`data/nicaragua_baseline.json`): hats/thermos/shade-share $45 +
training $10 (capital) + electrolyte solution $15 + program staff $25 (recurring) = **$95/worker**.

### 1.4 Worked example — Dubai (crew 100, 138-day season)

| Term | Calculation | Value |
|---|---|---|
| Productivity (lo–hi) | 4,927.5 … 9,855.0 worker-hrs × $3.75 | **$18,478 – $36,956** |
| Recovered safe work | 0 hrs (Dubai ban is out of season in May) × … | **$0** |
| AKI value | 7.67 cases × $1,200 | **$9,204** |
| Fines avoided | $1,361 × 100 × 0.03 | **$4,083** |
| **Headline benefit** | sum of the four above | **$31,765 – $50,243** |
| Program cost | $95 × 100 | **$9,500** |
| **Net benefit** | headline − cost | **$22,265 – $40,743** |
| **ROI** | 31,765 / 9,500 … 50,243 / 9,500 | **3.3× – 5.3×** |
| **Payback** | 9,500 / (31,765 / 138) | **~41 days** |
| *Excluded upside* | death-averted $5,752 + turnover $1,500 | *(not in headline)* |

### 1.5 Worked example — Riyadh (crew 100, 107-day season)

Riyadh runs **higher** because the ban is *in season*, so it also **destroys safe work** that
HeatGuard recovers (`ban_only_safe_work_hours = 82.8`/worker → $31,050):

| Term | Value |
|---|---|
| Productivity | $29,826 – $59,651 |
| Recovered safe work | **$31,050** |
| AKI value | $4,296 (3.58 cases × $1,200) |
| Fines avoided | $4,083 |
| **Headline benefit** | **$69,255 – $99,080** |
| Program cost | $9,500 |
| **ROI** | **7.3× – 10.4×**, payback **~15 days** |

### 1.6 Why it's conservative
- The headline **excludes** the two most dramatic terms (death-averted, turnover).
- Recovered work is **fraction-weighted** (credits actual productive hours, accounting for breaks).
- The worker-day value ($30) is low for the region.
- AKI averted scales **mechanistically** with the coverage gap, not a flat 94%.
- The biggest assumption (baseline AKI incidence) is shown as a range.

### 1.7 Honest limitations
The ROI is **[ILLUSTRATIVE]**: it depends on the tunable cost/value assumptions, the
$1,200 AKI-cost proxy (vs the $253.48 clinical figure), and the transfer of the Nicaragua
sugarcane effect sizes to Gulf construction. It is a credible *direction and order of
magnitude*, not a guaranteed return.

---

## Part 2 — Every landing-page claim

### 2.1 The danger & scale (context strip)

| Claim | Source | Tag |
|---|---|---|
| **24,000,000** migrant workers in the Arab States | ILO Global Estimates on Migrant Workers (2021, ref. 2019) | **[CONTEXT]** |
| **41.4%** — highest migrant-worker share of any region | same ILO source | **[CONTEXT]** |
| **~50 °C** Gulf summers | station records (reanalysis ~46–47 °C) | **[CONTEXT]** |
| **~10,000** migrant deaths/year, >50% uncertified | FairSquare / Vital Signs (all-cause; heat a hidden contributor) | **[CONTEXT]** |
| **1 of 19** worker-heat studies from the Gulf | 2025 systematic review (a near-total evidence void) | **[CONTEXT]** |
| The calendar ban (Saudi 12:00–15:00, 15 Jun–15 Sep) misses May/Sep heat, humid mornings, newcomers | GCC regulations + HRW reporting | **[STANDARD]** |

> The "~10,000" is **all-cause** migrant deaths, *not* heat deaths specifically — stated as such. Heat-attributable mortality is genuinely unknown because deaths are largely uncertified.

### 2.2 Impact — per 100-worker crew, one Dubai season

| Claim | How it's computed | Tag |
|---|---|---|
| **1,237** danger-hours the ban missed | engine, real Open-Meteo Dubai season; hours HeatGuard protected that the ban didn't cover | **[DERIVED]** |
| **7.7** AKI cases averted vs ban | `0.94 × 10 baseline × (danger missed / total danger)` | **[STANDARD × DERIVED]** |
| **3.3–5.3×** ROI · **~41-day** payback | Part 1.4 | **[ILLUSTRATIVE]** |
| **~$95/worker** | program cost itemisation (§1.3) | **[ILLUSTRATIVE]** |
| productivity **+10–20%** | Nicaragua effect-size band applied to heat-exposed work | **[STANDARD]** |

### 2.3 Impact at scale (`scale.py`)

Scaling reduces the per-crew result to **per worker**, then multiplies by the workforce:
- `lives_saved = (aki_averted_vs_ban / crew) × heat_death_per_aki_case × workforce`
- `aki_cases_averted = (aki_averted_vs_ban / crew) × workforce`
- value = `(headline_benefit / crew) × workforce`

| Claim (Dubai season) | Workforce | Tag |
|---|---|---|
| ~38 lives · 7,670 AKI averted · $32–50M value | 100,000 (megaproject) | **[ILLUSTRATIVE]** |
| ~1,900 lives · ~383,500 AKI averted · $1.6–2.5B value | 5,000,000 (regional slice) | **[ILLUSTRATIVE]** |

> "Lives saved" is the most assumption-laden number: it is AKI-cases-averted × a 0.005
> death-per-AKI severity ratio. It is labelled *illustrative/conservative* everywhere it appears.

### 2.4 Credibility claims

| Claim | Basis | Tag |
|---|---|---|
| Reproduces **AKI −94%, productivity +10–20%** (La Isla / Adelante, Nicaragua) | `heatguard backtest` asserts the model reproduces the documented outcome; the "94%" is a highest-risk-subgroup (burned cane cutters) figure | **[STANDARD]** |
| Built on **ISO 7243, ISO 7933, ACGIH, NIOSH**; WBGT via the validated **Liljegren** model | implemented in code; see README §4 | **[STANDARD]** |
| **79 tests + green CI** | `pytest` + GitHub Actions | **[DERIVED]** |
| "A prototype, not certified safety equipment" | disclaimer | — |

---

## Reproduce everything

```bash
heatguard roi dubai      # full benefit breakdown + ROI + payback
heatguard roi riyadh
heatguard backtest       # the 94% / 10–20% reproduction
heatguard demo dubai     # the 1,237 danger-hours, gap, AKI
curl 'localhost:8011/scale/dubai?workforce=5000000'   # the scale / lives-saved projection
```

See `datasets.md` for the full source list and the provenance caveats on each assumption.
