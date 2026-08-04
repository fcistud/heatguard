# HeatGuard scope guardrail (business / legal / compliance)

**Status:** Normative for current-stage deployments (public demo, pilot, production without regulator authorization).  
**Audience:** Product, engineering, docs, demos, compliance review.  
**Related:** [ROI_AND_CLAIMS.md](ROI_AND_CLAIMS.md) (evidence tags), [calendar_ban.py](../src/heatguard/calendar_ban.py) (legal rules).

---

## 1. Purpose

HeatGuard is a **decision-support and evidence system** for Work–Rest–Shade (WRS) heat safety. It helps supervisors plan safer work under real conditions and produce auditable records of protective actions.

At this stage HeatGuard must **strengthen compliance posture**. It must not create legal exposure by appearing to authorize work that local law prohibits.

---

## 2. Core principle

> **Law governs permission to work. Science governs how to work safely when work is permitted.**

The engine may compute physiological safety independently. **User-facing operational advice must never conflict with binding legal prohibitions** in the current deployment stage.

---

## 3. Decision precedence (normative)

1. **Legal/regulatory hard constraints** (non-overridable)
2. **Safety-science constraints** (WBGT, PHS, acclimatization, personal-risk advisories)
3. **Optimization/analytics** (shift design, productivity recovery, season comparisons)

When levels conflict:

- Legal constraint wins for **permission to work**
- Safety science may still inform **protective actions** (hydration, shade, rest) but must not be framed as work authorization during an active ban

Implementation: [`legal_precedence.py`](../src/heatguard/legal_precedence.py).

---

## 4. In scope (current stage)

- WRS guidance from conditions, intensity, acclimatization, and worker profile
- Jurisdiction rules applied as **binding constraints** on operational advice
- Qatar-style condition-based legal logic where encoded
- Tamper-evident compliance logging
- Policy retrieval (cited excerpts; not legal advice)
- **Analytic comparison:** where calendar bans miss danger, and where science indicates safer conditions during banned windows — **without authorizing work**

---

## 5. Out of scope (current stage)

- **Ban-override operations** — instructing or enabling work during calendar-ban windows
- **Regulatory substitution** — replacing statutory obligations or inspector authority
- **Unauthorized pilots** — treating HeatGuard output as legal permission without labor/enforcement participation
- **Legal advice claims** — guaranteed compliance, fine immunity, automatic regulatory approval
- **Employer screening** — hiring/termination use of personal-risk scores

---

## 6. Required user-facing behavior

When `legal.banned = true`:

1. **Effective signal must be non-work-authorizing** (`STOP` when science would permit work).
2. **Scientific assessment may be shown separately** with explicit “legal ban governs” wording.
3. **Analytics** (`ban_only_safe_hours`, “recovered hours”) are scenario/comparison metrics — not actionable shift plans.
4. **Forecast shift recommendations** exclude legally prohibited hours as actionable work time.
5. **Compliance logs** reflect legal constraint application; they do not imply unauthorized work.

---

## 7. Long-term pathway (not current scope)

Authority-partnered modernization pilots may evaluate controlled recovery of working hours under formal legal frameworks. Gates before any override pilot:

1. Written participation from enforcement/regulatory bodies  
2. Jurisdiction-specific legal review and pilot charter  
3. Controlled site scope and audit protocol  
4. Independent monitoring and rollback criteria  

Until gates are met, ban-override behavior remains roadmap-only.

---

## 8. API contract

Operational endpoints expose:

| Field | Meaning |
|-------|---------|
| `scientific_advisory` | Raw scheduler output |
| `effective_advisory` | After legal precedence |
| `advisory` | **Operational default** (= effective) |
| `legal.banned` | Legal prohibition active |
| `legal.precedence_applied` | Science would authorize work but law prohibits |
| `live` | Minute-by-minute **operational** signals |

Timeline rows include `veteran` / `newcomer` (scientific) plus `veteran_effective` / `newcomer_effective` (operational).

---

## 9. Acceptance criteria

- [ ] Operational surfaces never emit work-authorizing advice when `legal.banned=true`
- [ ] Forecast shift recommendations exclude banned intervals as actionable work
- [ ] Comparison views include non-authorizing disclaimers
- [ ] Docs and demo scripts use approved claims only
- [ ] Tests cover ban precedence across API and UI contract

---

## Appendix A — Language dictionary

### Global rules

- **Operational language** — anything a supervisor could treat as permission or instruction (`[OP]`)
- **Analytic language** — comparison/scenario only (`[AN]`)
- Never say “safe to work” without **legally permitted** vs **scientifically permissible**

### Core terms

| Term | Definition |
|------|------------|
| **Operational advice** | Final instruction shown to users |
| **Scientific assessment** | Engine output before legal gating |
| **Effective signal** | User-facing signal after legal precedence |
| **Legal prohibition** | Jurisdiction rule forbids outdoor work |
| **Binding constraint** | Non-overridable rule (law first) |

### Signal labels (`[OP]`)

| Signal | Crew instruction | During active ban |
|--------|------------------|-------------------|
| `WORK` | Work permitted (within cycle) | **Never show as operational instruction** |
| `REST_IN_SHADE` | Rest in shade | Allowed (protective) |
| `STOP` | Stop work | Allowed; use when law blocks work |
| `DRINK_NOW` | Hydrate now | Allowed (not work authorization) |

**Ban-active operational primary label:** “Do not work — legal prohibition in effect.”

### Comparison terms (`[AN]` only)

| Term | Required disclaimer |
|------|---------------------|
| **Gap hour** | “Operational decisions still follow legal rules.” |
| **Ban blind spot** | “Shows regulatory gap, not permission to violate law.” |
| **Ban over-cautious hour** | “Not permission to work during legal ban.” |
| **Recovered / needlessly stopped hours** | “Scenario analysis only.” |

### Approved phrasebook

- “Do not work — legal prohibition in effect.”
- “Scientific assessment indicates some work may be possible; legal ban governs operational permission.”
- “Comparison view for analysis. Legal prohibition always governs operational permission.”
- “This tool supports compliance; it does not provide legal advice.”

### Prohibited phrasebook

- “Safe to work now” (without legal qualifier)
- “Override the midday ban”
- “HeatGuard permits work during banned hours”
- “Legally compliant by default”
- “Zero legal risk”

### Demo guardrail line (required)

> HeatGuard never tells crews to work when local law prohibits it. We show where fixed calendar bans miss danger, and where science suggests safer scheduling — but legal rules always govern permission.

---

## One-line executive summary

**HeatGuard advises safer WRS execution and proves protective action — but at this stage it never tells users to work when local law says they cannot.**
