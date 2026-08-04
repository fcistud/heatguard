# HeatGuard — Hackathon Judging Rubric Map

**Track:** Prevent + Prepare · **Max score:** 22 + bonus considerations  
**Companion:** [`PRESENTATION_ONE_PAGER.md`](PRESENTATION_ONE_PAGER.md) · **Demo:** `scripts/run_demo.sh`

Use this to align slides and Q&A with what judges score. Each row: **claim → evidence in the build → demo moment → honest gap**.

---

## Core criteria (22 points)

### Impact — 5 pts
*Potential to improve health outcomes or increase resilience to climate risks*

| Claim | Evidence | Demo moment |
|-------|----------|-------------|
| Closes **calendar vs climate** gap | Real Open-Meteo replay; Dubai May before ban season | Timeline: empty ban lane, **12 gap hours** on 16 May |
| Protects **most vulnerable** workers | NIOSH acclimatization + Action-Limit table for newcomers | Riyadh + New worker toggle → STOP from ~09:00 |
| **Mechanistic AKI model** vs blunt ban | `impact.py`; danger-hours coverage gap | Season impact: **1,237** danger hours ban missed |
| **Validated intervention science** | Nicaragua back-test (`/backtest`, unit test) | Green card: *94% AKI reduction reproduced ✓* |
| **Climate resilience** = adaptive scheduling | Forecast API + shift-window logic (not fixed dates) | Mention forecast endpoint; shoulder-season argument |

**Sound bite:** *Climate change moved the heat earlier; the ban didn't move with it.*

**Gap to acknowledge:** Gulf-specific outcome data not yet collected; Nicaragua effect sizes shown as range/sensitivity.

---

### Team — 4 pts
*Interdisciplinary and collaborative*

| Angle | How to present |
|-------|----------------|
| **Domain** | Occupational heat standards (ISO/ACGIH/NIOSH), Gulf labour policy, migrant health |
| **Engineering** | Deterministic Python engine, 265+ tests, FastAPI + React, offline demo |
| **Data / ML** | Real weather archives, PHS-labelled risk model, TF-IDF policy retrieval (no LLM) |
| **Product / biz** | ROI model, compliance shield, ESG / development-finance angle |
| **Collaboration** | Split roles: engine, dashboard, landing, slides, copy — shared `service.py` single source of truth |

**Sound bite:** *One engine, five interfaces — everyone works off the same numbers.*

---

### AI + Data — 4 pts
*Built using provided or relevant datasets and/or AI tools*

| Data / AI | Source | Wired in repo |
|-----------|--------|---------------|
| **Weather (archive + forecast)** | Open-Meteo (hackathon-relevant climate data) | `data/cache/`, `/forecast/{site}`, `/datasets` |
| **WRS intervention effects** | La Isla / Adelante (2024 ILO) | `nicaragua_baseline.json`, `/backtest` |
| **GCC policy corpus** | Curated regulations + ILO WRS | `data/policy/*.md`, `/policy/query` |
| **Personal risk ML** | Gradient boosting; labels from ISO 7933 PHS on real weather | `risk_model.joblib`, dashboard badges |
| **Policy retrieval** | TF-IDF retrieval (no external LLM — offline, auditable) | Policy gap auditor panel |

**Not using UK/NHS sets** — deliberate: problem is Gulf outdoor labour; say so explicitly (scope choice, not omission).

**Sound bite:** *Real weather, published effect sizes, committed policy corpus — AI layers on top, never replaces the standard.*

---

### Innovation — 3 pts
*Novel, creative, unique approach*

| What's different | vs status quo |
|------------------|---------------|
| **Calendar → condition-responsive** | Same legal intent, better targeting |
| **Implementation fidelity layer** | Not another screening tool — schedules WRS and *proves* it |
| **Most-conservative stack** | ACGIH + NIOSH ramp + PHS cap → one signal |
| **Policy-gap retrieval** | Supervisors ask “when does the ban start?” — cited answer in seconds |
| **Productivity-positive safety** | Recovers safe work ban blocks (Riyadh ROI 7–10×) |

**Sound bite:** *We didn't invent water and shade — we made them schedulable, verifiable, and fundable.*

---

### Feasibility — 3 pts
*Realistic and actionable for intended audience*

| Constraint | How HeatGuard fits |
|------------|---------------------|
| **Cost** | ~$300 WBGT meter + supervisor phone; no per-worker wearable required |
| **Adoption friction** | Site-level signal (horn/light); workers don't need apps |
| **Employer incentive** | ROI 3–10×, ~6-week payback; fines shield (UAE AED 5,000/worker) |
| **Offline / low connectivity** | Committed weather cache; engine runs locally |
| **Standards-aligned** | ISO 7243, 7933, 8996; ACGIH; NIOSH — not a black box |

**Gap:** Pilot with labour contractor still needed; prototype not certified equipment.

---

### Scalability — 3 pts
*Expandable beyond pilot; implementable at scale*

| Scale lever | In build |
|-------------|----------|
| **Multi-site manifest** | 7 Gulf cities in `datasets.json` |
| **Workforce projection** | `/scale/{site}` + Scale panel (AKI averted, lives saved at 100k workers) |
| **Multi-region transfer** | Swap `locales.json` + ban rules — Central Valley ag, logistics, mining |
| **ESG / dev finance** | Hash-chained compliance export for lender audits |
| **Marginal cost** | Near-zero per worker after one site sensor |

**Sound bite:** *Same engine, new JSON config — Gulf today, California fields tomorrow.*

---

## Bonus considerations

### Sustainability & resource use

| Point | Message |
|-------|---------|
| **Low hardware footprint** | One sensor per site vs wearables for every worker |
| **Software-only core** | Python engine; no cloud dependency for decisions |
| **Energy** | Edge/local scheduling; policy retrieval is TF-IDF (no GPU, no LLM API calls) |
| **Maintenance** | Standards-based tables update with regulation changes, not model retraining |
| **Long-term** | Committed caches + manifest = reproducible, auditable deployments |

---

### Evidence & measurement

| Metric | How we'd measure | Already in build |
|--------|------------------|------------------|
| **Health** | AKI incidence, heat illness events, hydration compliance | Mechanistic model + sensitivity range |
| **Adoption** | Sites deployed, signals followed, break/water confirmations | Compliance log + future NFC checkpoints |
| **Productivity** | Output per heat-exposed hour vs baseline | Nicaragua 10–20%; ROI productivity term |
| **Climate gap closed** | Danger-hours covered vs calendar ban | `gap_hours`, season impact stats |
| **Validation** | Nicaragua back-test; future Gulf pilot | `/backtest` assertion test |

**Say:** *We separate what's measured (Nicaragua, real weather gaps) from what's projected (AKI $, lives saved) — and label both.*

Doc: [`ROI_AND_CLAIMS.md`](ROI_AND_CLAIMS.md)

---

### Ethics & governance

| Concern | Response |
|---------|----------|
| **Privacy** | Site-level default; compliance summary includes privacy block; no continuous worker tracking |
| **Surveillance** | Signal is for protection; NFC only at water/break checkpoints (roadmap) |
| **ML safety** | Personal risk **never changes** regulatory Signal — unit tested |
| **Screening vs protection** | Demographics tighten protection, never exclude workers (handbook guardrail) |
| **Policy retrieval** | Extractive + cited sources; not legal advice |
| **Honest limits** | WBGT estimate vs measured; Nicaragua→Gulf transfer uncertainty stated |

**Demo:** Compliance panel “worker protection record”; what-if shows ML badge alongside unchanged STOP/WORK.

---

## Suggested slide → criterion mapping

| Slide | Primary criterion |
|-------|-------------------|
| Problem (calendar fails) | Impact |
| Solution (sense → schedule → signal → verify) | Innovation + Feasibility |
| Science + Nicaragua validation | Impact + AI/Data |
| Live demo (timeline, policy, what-if) | AI/Data + Innovation |
| ROI + scale panel | Feasibility + Scalability |
| Transfer (Gulf → Central Valley) | Scalability + Impact |
| Team + roadmap | Team + Scalability |
| Ethics / measurement (1 slide) | Bonus |

---

## Q&A prep — highest-risk judge questions

1. **“Nicaragua ≠ Gulf”** → Physiology universal; magnitude uncertain; sensitivity chart; pilot proposed.
2. **“Why not wearables?”** → Adoption friction; site-level wedge; checkpoints later.
3. **“Does AI override safety?”** → No — show test + live what-if.
4. **“Where's the health data?”** → Published aggregates + mechanistic model; individual records don't exist publicly — we're explicit.
5. **“Who pays?”** → Employer ROI positive; ESG lenders; cost << fine exposure.

---

*Last updated for `dataset-expansion` / hackathon submission.*
