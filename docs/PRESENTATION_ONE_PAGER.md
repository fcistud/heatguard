# HeatGuard — Presentation One-Pager

**For slide team · [Health in Climate AI London](https://healthinclimate.ai/hackathons/london) (Prevent + Prepare)**  
**Judging:** 22 core points + bonus (sustainability, evidence, ethics) · Full rubric map: [`JUDGING_RUBRIC.md`](JUDGING_RUBRIC.md)

Repo: `fcistud/heatguard` · Demo: `scripts/run_demo.sh` → http://localhost:5173

---

## Elevator pitch (30 sec)

Gulf states ban outdoor work at **fixed noon windows on fixed calendar dates**. That misses real danger (May heat before the ban starts; humid mornings; unacclimatized newcomers) and needlessly stops safe work (cool in-season hours). **HeatGuard** replaces the calendar with a **WBGT-driven work–rest–hydration scheduler** built on ISO/ACGIH/NIOSH standards, broadcasts one site signal (**WORK · REST IN SHADE · DRINK NOW · STOP**), logs every decision in a **tamper-evident chain**, and proves the business case. We already know WRS works (Nicaragua: **~94% AKI reduction**); HeatGuard is the **adaptive implementation + verification layer**.

**Rubric hook:** *Climate change moved the heat earlier; the ban didn't move with it.* → **Impact**

---

## Judging rubric — what to hit (22 pts)

| Criterion | Pts | Our story (one line) | Demo / evidence moment |
|-----------|-----|----------------------|-------------------------|
| **Impact** | 5 | Adaptive WRS closes calendar gaps → fewer AKI cases, climate-resilient scheduling | Dubai timeline **12 gap hours**; season **1,237** danger hours; Nicaragua ✓ card |
| **Team** | 4 | Domain + eng + data/ML + product on **one engine** (`service.py`) | Mention split roles; five interfaces, same numbers |
| **AI + Data** | 4 | Open-Meteo weather, Nicaragua/ILO/GCC corpus, PHS-labelled ML, TF-IDF policy retrieval | Policy query *“UAE ban starts 15 June”*; personal-risk badges |
| **Innovation** | 3 | Schedulable + **verifiable** WRS — not new science, new **implementation layer** | Sense → schedule → signal → verify diagram |
| **Feasibility** | 3 | ~$300 site sensor, ROI **3–10×**, horn/light signal, offline-capable | ROI panel; worker protection record (compliance log) |
| **Scalability** | 3 | 7 Gulf sites, `/scale` workforce projection, config swap for new regions | Scale panel; Central Valley transfer slide |

**Honest gaps (say once):** Gulf pilot outcomes not yet measured; Nicaragua→Gulf magnitude shown as sensitivity range; prototype not certified equipment.

---

## 1. The problem → **Impact**

| Who | ~24M migrant workers in Arab States; outdoor construction, infrastructure, delivery |
| Current control | Calendar midday ban (e.g. UAE 12:30–15:00, 15 Jun–15 Sep) — blind to weather, job, worker |
| Failure mode A | **Too permissive** — Dubai May 2025 heat before ban season → **12 gap hours** on demo day (16 May) |
| Failure mode B | **Misses edges** — Riyadh ban covers noon; day-0 newcomer needs protection from ~09:00 → **9 gap hours** |
| Failure mode C | **Over-restricts** — stops safe productive hours → employers evade the rule |
| Science gap | Intervention is cheap and proven; **implementation fidelity + proof** is what's missing |

**Sound bite:** *Wrong in both directions — too permissive and too restrictive.*

---

## 2. Datasets → **AI + Data**

| Data | Source | Use |
|------|--------|-----|
| Hourly weather (archive + forecast) | Open-Meteo (ERA5-class) | Real Gulf replay; WBGT; shift planning |
| Demo sites | Dubai, Riyadh (+ Abu Dhabi, Doha, Kuwait, Muscat, Manama) | Primary narratives: Dubai May / Riyadh Jul |
| Nicaragua WRS effects | La Isla / Adelante (2024 ILO) | Impact model + back-test (94% AKI, 10–20% productivity) |
| GCC ban + ILO corpus | Curated regulations (`data/policy/`) | Policy-gap retrieval (cited excerpts, no external LLM) |
| Economics assumptions | Tunable JSON | ROI — conservative, documented in `docs/ROI_AND_CLAIMS.md` |
| ML risk model | PHS labels on real weather | Personal-risk overlay — **never overrides regulatory signal** |

**Not used:** individual worker health records, UK/NHS datasets — **deliberate scope** (Gulf outdoor labour, not omission).

**Sound bite:** *Real weather, published effect sizes, committed policy corpus — AI on top, never replaces the standard.*

---

## 3. Scope of what we built → **Innovation + Feasibility**

**In scope (MVP):**
- Pure Python **standards engine** → work-rest (ISO 7243), hydration (ISO 7933 PHS), acclimatization (NIOSH)
- **Site-level** supervisor product: one WBGT input, one crew signal, hash-chained compliance log
- **React dashboard** — timeline (calendar vs adaptive), ROI, scale projection, policy auditor, what-if, measured-WBGT toggle
- **AI layer (advisory only):** personal-risk badges + TF-IDF policy retrieval (extractive, no LLM)
- **265+ tests**; Nicaragua back-test; offline demo via committed weather cache

**Out of scope (honest):**
- Certified safety equipment / legal product
- Per-worker wearables or production horn hardware
- Gulf pilot outcome data (effect sizes transferred with stated uncertainty)

**Demo beats (90 sec):** Dubai empty ban lane → Riyadh + newcomer → season impact + Nicaragua ✓ → ROI + scale → policy query (“UAE ban starts **15 June**”) → live what-if.

Presenter script: `docs/DASHBOARD_WALKTHROUGH.md`

---

## 4. Key numbers → **Impact + Feasibility**

| | Dubai (May focus) | Riyadh (Jul focus) |
|--|-------------------|---------------------|
| Gap hours ban missed (focus day) | **12** | **9** (newcomer) |
| Danger hours caught vs ban (season) | **1,237** | ~100s |
| AKI cases averted vs ban | **7.7** / 10 baseline | ~3–4 |
| ROI (headline) | **3.3×–5.3×**, ~41-day payback | **7×–10×**, ~15-day payback |

**Validation anchor:** Nicaragua back-test reproduces 94% AKI reduction — fails loudly if effect sizes change.

---

## 5. Growth & transfer → **Scalability + Impact**

**Roadmap (post-hackathon):** forecast panel · on-site WBGT + horn · checkpoint NFC · Gulf pilot · ESG compliance export. Detail: `docs/HANDBOOK.md` §11

| Region / sector | Fit |
|-----------------|-----|
| **California Central Valley agriculture** | Migrant farm workforce; field heat; Cal/OSHA rules — **strong parallel** |
| **Mesoamerica sugarcane** | Direct validation (source of effect sizes) |
| **Gulf logistics / mining / humanitarian** | Swap site config + ban rules + weather |

**Sound bite:** *Same engine, new JSON config — Gulf today, California fields tomorrow.*

---

## 6. Bonus criteria (weave into slides or Q&A)

| Bonus | Message | Where in demo |
|-------|---------|---------------|
| **Sustainability & resources** | One sensor per site; local Python engine; TF-IDF retrieval (no GPU/LLM API); low hardware/maintenance footprint | Mention in feasibility / roadmap |
| **Evidence & measurement** | **Measured:** gap-hours on real weather, Nicaragua back-test. **Projected:** AKI $, lives saved — labelled + sensitivity range | Season impact, scale panel, `ROI_AND_CLAIMS.md` |
| **Ethics & governance** | Privacy-by-design compliance log; ML never changes Signal (unit tested); protection not screening; policy retrieval returns cited excerpts, not legal advice | Worker protection record; what-if with elevated badge |

---

## 7. Q&A — highest-risk judge questions

| Question | Response |
|----------|----------|
| “Nicaragua ≠ Gulf?” | Physiology universal; magnitude uncertain; sensitivity chart; pilot proposed |
| “Why not wearables?” | Adoption friction; site-level wedge; NFC at checkpoints later |
| “Does AI override safety?” | **No** — show test + live what-if |
| “Where's the health data?” | Published aggregates + mechanistic model; no public individual records — explicit |
| “Who pays?” | Employer ROI positive; ESG lenders; cost ≪ fine exposure (UAE AED 5,000/worker) |
| “Is WBGT real?” | Liljegren for demo; ~$300 meter in production — Estimated ⟷ Measured toggle |
| “Surveillance?” | Site-level default; record is worker-protective |

---

## Slide deck — mapped to rubric (9 slides)

| # | Slide | Rubric | Content |
|---|-------|--------|---------|
| 1 | Title | — | HeatGuard: stop scheduling heat safety by the calendar |
| 2 | Problem | **Impact** | Calendar wrong both ways — Dubai May + Riyadh newcomer |
| 3 | Solution | **Innovation · Feasibility** | Sense → schedule → signal → verify |
| 4 | Science + data | **Impact · AI+Data** | ISO stack + Open-Meteo + Nicaragua validation |
| 5 | Live demo | **AI+Data · Innovation** | Timeline · policy retrieval · what-if |
| 6 | Impact + ROI | **Impact · Feasibility** | 1,237 hours · 3–10× ROI · compliance log |
| 7 | Scale + transfer | **Scalability · Impact** | `/scale` panel · Central Valley ag |
| 8 | Team + roadmap | **Team · Scalability** | Roles · pilot · ESG pathway |
| 9 | Ethics & measurement | **Bonus** | Privacy · ML guardrails · what we measure vs project |

*Optional footer on each slide: criterion tag (e.g. “Impact · 5 pts”)*

---

## Assets for designers

- **Dashboard:** `web/` — WORK `#16a34a` · REST `#f59e0b` · DRINK `#0ea5e9` · STOP `#dc2626`
- **Landing:** `landing/index.html`
- **Handbook:** `docs/HANDBOOK.md` · **ROI:** `docs/ROI_AND_CLAIMS.md` · **Data:** `docs/DATA.md`
- **Full rubric detail:** `docs/JUDGING_RUBRIC.md`

---

*Run: `heatguard demo dubai` · `heatguard policy-query "When does the UAE ban start?"`*
