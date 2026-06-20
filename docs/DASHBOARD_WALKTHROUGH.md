# HeatGuard — Dashboard Walkthrough (top → bottom)

A presenter's guide to the supervisor dashboard. Each section has **On screen** (what
the audience sees), **Say** (the pitch line), **Under the hood** (the science/data so you
can field questions), and **Interact** (what to click). Numbers below are the live
Dubai-crew-100 demo values; they update as you change site / crew.

> **Launch:** `uvicorn heatguard.api:app` then `cd web && npm run dev` → open
> `http://localhost:5173`. Or one command: `scripts/run_demo.sh --setup`.
> The dashboard defaults to **Dubai**. Keep that for the opening; switch to **Riyadh**
> for the newcomer beat.

---

## 0. The one-sentence frame (say this first)

> "Every Gulf state bans midday outdoor work on a fixed **calendar**. That calendar is
> wrong in *both* directions — it misses real danger, and it needlessly stops safe work.
> HeatGuard replaces it with a schedule that responds to *actual* conditions, and proves
> it happened. Let me show you."

---

## 1. Top bar — controls

**On screen:** "HeatGuard" wordmark + tagline; a **Site** toggle (Dubai / Riyadh); a
**Crew size** input (default 100).

**Say:** "One sensor per site drives this — it's the supervisor's screen, not a wearable
on every worker. Crew size just scales the season economics."

**Under the hood:** Site picks the locale (lat/lon/timezone) and which GCC ban rule
applies. Crew size re-runs the impact + ROI (debounced) — the per-worker physics don't
change, only the totals.

**Interact:** Leave on **Dubai, 100** to start.

---

## 2. Headline banner

**On screen:** *"Dubai, May 2025 — extreme heat arrived before the calendar ban started."*
plus the **season peak: 46.5 °C** and the ban rule (*UAE: 12:30–15:00, 15 Jun – 15 Sep*).

**Say:** "This is a real May day from reanalysis data. Hold that date — **16 May** — in
your head; the ban doesn't start until 15 June."

**Under the hood:** Real hourly weather from the Open-Meteo archive, cached in the repo so
the demo runs offline. The peak is the hottest hour in the replayed season window.

---

## 3. Live signal tile (the hero)

**On screen:** A large colored card — **WORK** (green) / **REST IN SHADE** (amber) /
**DRINK NOW** (blue) / **STOP** (red) — for the currently selected hour and worker. Shows
the **work/rest split** (e.g. 60–0 min), **hydration** (cups/h + mL/h), and **max safe
continuous** minutes, with the plain-English rationale underneath.

**Say:** "This is the only thing the crew ever sees — one signal on a site horn or light.
Right now: work the full hour, two cups of water, with a stated reason."

**Under the hood:** The signal is the **most conservative** of three independent limits:
the ACGIH/ISO 7243 work-rest table, the NIOSH acclimatization ramp, and the ISO 7933
Predicted Heat Strain physiological cap. STOP only fires when no safe work block remains
or WBGT is above the regulatory ceiling.

**Interact:** Click **"▶ simulate the hour"** to animate the intra-hour broadcast ribbon —
Work blocks, Drink pulses, and the Rest break in sequence.

---

## 4. WBGT gauge + conditions

**On screen:** A semicircle dial (green→amber→red) with the **WBGT** value and a **risk %**,
plus air temperature, humidity, and a **provenance badge** — *Liljegren-estimated* /
*measured* / *fallback*.

**Say:** "WBGT — wet-bulb globe temperature — is the standard heat-stress index, not just
air temp. We estimate it with the validated Liljegren model; on a real site you drop in a
$300 meter and the badge flips to *measured*."

**Under the hood:** WBGT = 0.7·natural-wet-bulb + 0.2·globe + 0.1·air. Estimated from
temperature, humidity, wind, and solar radiation via Liljegren (daytime) with a Stull
fallback at night. The badge keeps the approximation honest — provenance is carried all
the way into the audit log.

**Interact — the sensor answer:** flip the **Estimated ⟷ Measured (on-site meter)** toggle
and enter a meter reading. The gauge, the signal, and the rationale recompute on the *same
engine* with `source = measured`, and a caption shows **"estimate X°C → meter Y°C"**. This is
the direct answer to "your WBGT is approximate": in production you drop in a ~$300 meter and
nothing else changes. Show a value that flips REST → STOP for drama.

---

## 5. Calendar ban vs HeatGuard — the timeline (centerpiece)

**On screen:** The WBGT curve over the day, above **two lanes**:
- **Calendar ban** — grey = permitted, dark = ban active.
- **HeatGuard (adaptive)** — each hour colored by the signal, with **"!" badges on the
  gap hours** the ban missed.
A **day scrubber**, a **Veteran ⟷ New worker** toggle, and a **"Gap hours (missed by
ban)"** counter.

**Say (Dubai):** "Look at the Calendar-ban lane — it's **empty all day**. The 16 May heat
arrived a month before the ban season. HeatGuard, meanwhile, is cycling rest and stops —
**12 hours** of protection the calendar gave zero of."

**Under the hood:** `is_banned(country, time, wbgt)` evaluates the real GCC rule (season +
daily window, plus Qatar's WBGT cutoff). A **gap** = either worker needed protection
(STOP/REST) and the ban did not cover that hour. The all-grey lane is correct, not a bug —
it *is* the argument.

**Interact:**
1. Drag the **day scrubber** past 15 June → dark **BAN** cells appear (the ban "switches
   on" for the season) — proving the lane renders.
2. Change the **work-intensity** selector (Light → Very heavy): the HeatGuard lane tightens as
   the job gets harder — it's *individualised to the work*, not one crew-wide rule.
3. With **New worker** selected, drag the **"day N"** control 0 → 5: watch the morning protection
   relax as the worker acclimatises (the NIOSH ramp, live).
4. **The money move:** switch **Site → Riyadh**, then toggle **New worker (day 0)**.

---

## 6. The Riyadh / newcomer beat (do this live)

**On screen (Riyadh, New worker):** The ban shows **4 dark cells at 12:00–15:00**, but the
day-0 newcomer's lane is **red STOP from ~09:00 to 16:00** — **9 gap hours**.

**Say:** "Now we're *in* the ban season. The calendar protects three hours at noon. But an
unacclimatized new arrival — the people who actually die — is in danger from 9am. The
calendar can't see the worker, the humidity, or the morning. HeatGuard does."

**Under the hood:** New workers get the stricter **Action-Limit** table *and* a NIOSH
exposure ramp (20% of normal on day 0, rising over 5 days). See it on the next panel.

---

## 7. Acclimatization tracker

**On screen:** The NIOSH ramp 20 → 40 → 60 → 80 → 100% across days 0–4, with the active
worker's day highlighted, and a caption ("Exposure capped at 20%…" for a day-0 newcomer).

**Say:** "Acclimatization is pure scheduling — zero cost — and it targets the deadliest,
cheapest-to-protect group. No screening people out; just ramping them in safely."

**Under the hood:** The ramp caps the work fraction; the cap only binds when heat stress is
actually present (a newcomer still works normally in cool dawn hours).

---

## 8. Season impact

**On screen (Dubai, crew 100):** Stat cards —
- **Danger hours caught vs ban: 1,237**
- **Hours ban needlessly stopped: 0** (Dubai is out of season; in Riyadh this is large)
- **AKI cases averted vs ban: 7.7** (of 10 baseline)
- **Productivity gain: 10–20%**, **Cost / worker: $95**
- A bar: **work hours/worker** (Calendar 1,791 h vs HeatGuard 493 h) + a
  **"Validated against Nicaragua: 94% AKI reduction reproduced ✓"** card.

**Say:** "Across the season this is 1,237 dangerous hours the ban missed. The work-hours
bar looks like *less* work under HeatGuard — but those are the **safe, productive** hours;
the calendar's extra hours are dangerous unprotected exposure. And the green check matters:
our impact model reproduces the **real** Nicaragua intervention — 94% fewer kidney-injury
cases — so these aren't invented numbers."

**Under the hood:** The AKI estimate is **mechanistic**: `reduction × baseline ×
(danger the ban missed / total danger)` — it collapses to zero when the ban already covers
the danger, and gates to zero when there's no danger at all. The Nicaragua back-test is a
unit test that fails loudly if anyone changes an effect size.

---

## 9. Business case / ROI (the money slide)

**On screen (Dubai, crew 100):** **Headline ROI 3.3× – 5.3×**, **payback ~41 days**,
headline benefit **$31,765–$50,243**, program cost **$9,500**, net **$22,265–$40,743**.
(Riyadh runs **7–10×**, ~15-day payback, because it also *recovers* the safe work the ban
blocks.)

**Say:** "This is the part that gets it switched on. It's not a safety cost — it's
**productivity-positive with a ~6-week payback**. We deliberately compute the headline on a
*conservative* subset and exclude the dramatic stuff."

**Under the hood:** Headline benefit = productivity gain + recovered safe work + AKI cases
averted + fines avoided. The **death-risk-averted and turnover** terms are computed but
shown *separately, excluded from the headline*, so the ROI can't be accused of inflation.
All assumptions live in `data/economics.json` and are tunable.

---

## 10. Cost-vs-benefit + sensitivity

**On screen:** A **cost bar vs a stacked benefit bar** (Productivity $18,478 · Recovered
safe work $0 (Dubai) · AKI averted $9,204 · Fines avoided $4,083), an **"additional upside
(excluded)"** line (+$5,752 death-risk, +$1,500 turnover), and an **AKI sensitivity
chart** — cases averted rising from ~4 to ~16 as the baseline incidence goes 5%→20%, with
the 10% default marked.

**Say:** "Here's the honesty slide. The biggest assumption is the baseline kidney-injury
rate — so we show it as a **range, not a point**. Even at the low end the case is strong."

**Under the hood:** Recovered-safe-work is **fraction-weighted** (it credits the actual
productive hours, accounting for breaks — that's why it's not over-claimed).

---

## 11. Worker protection record (dual-purpose, privacy by design)

**On screen:** An hour-by-hour table (time · signal · WBGT · work/rest · water), a
**"✓ chain verified — tamper-evident"** badge with the head hash, a **"Privacy by design"**
note, and a **Download CSV** button.

**Say:** "Every reading and break is hash-chained, like a mini-ledger — edit one row and the
whole chain breaks. It works **both ways**: it's the *worker's* own proof they were protected
— their heat-safety history for a health or grievance claim — *and* the employer's shield
against fines (AED 5,000/worker in the UAE) and liability. And it's **privacy by design**: it
records site conditions and protective actions, **not** location, biometrics, or worker
tracking — which defuses the surveillance objection a labour-rights reviewer would raise."

**Under the hood:** SHA-256, each record commits to the previous (`prev_hash`); a single
mutation or deletion fails `verify_chain()`. Exports to CSV/JSONL for the audit binder.

---

## 12. What-if — live engine

**On screen:** Sliders for air temp / humidity / solar / hour, an intensity dropdown, an
**Acclimatized ⟷ New (day 0)** toggle, and **Run the engine →**. The result renders the
signal + cycle + hydration + whether the ban would apply (e.g. **44 °C, heavy → STOP,
WBGT 38.2 °C, 2.5 cups/h**).

**Say:** "And to prove none of this is canned — change anything and run it. That's a live
`POST /decide` to the same engine."

**Under the hood:** Identical code path as every other number on the page; the dashboard is
a thin client over the Python engine.

---

## 90-second demo script (if you only have a minute and a half)

1. **Frame** (§0) — "the calendar is wrong in both directions."
2. **Dubai timeline** (§5) — point at the empty ban lane: "16 May, heat's here, ban starts
   15 June — **12 hours, zero protection**."
3. **Switch to Riyadh + New worker** (§6) — "in season now; ban covers noon, but the new
   arrival is in danger from 9am — **9 hours the calendar can't see**."
4. **Season impact + Nicaragua check** (§8) — "1,237 missed danger-hours; validated against
   a real 94% intervention."
5. **ROI** (§9) — "and it pays for itself — **3–5×, six-week payback**, productivity-positive."
6. **Compliance** (§11) — "with a tamper-evident audit trail that doubles as a fines shield."
7. **What-if** (§12) — "live, not canned — change anything, run it."

---

## Anticipated questions

- **"Why is the Dubai ban lane all grey?"** It's out of season — 16 May is before the
  15 June ban. That's the point: the calendar misses whole shoulder-seasons of heat.
- **"Is the WBGT real?"** Estimated via the validated Liljegren model from real reanalysis
  weather; production measures directly with a cheap meter (the *measured* badge).
- **"Aren't the ROI numbers optimistic?"** The headline excludes the death and turnover
  terms and uses conservative, tunable assumptions; recovered work is fraction-weighted.
- **"Does it work without the internet?"** Yes — the demo weather is cached in the repo.
- **"Why site-level, not a wearable?"** Cost, friction, and surveillance kill per-worker
  hardware; one sensor + the supervisor's screen is what actually gets adopted.
