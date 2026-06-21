# GCC midday outdoor work bans — comparison

Summary of calendar-based midday work bans across Gulf Cooperation Council states, as encoded in HeatGuard's `calendar_ban` module for gap analysis against WBGT-driven scheduling.

| State | Daily window (local) | Season | WBGT rule | Enforcement notes |
|---|---|---|---|---|
| **Saudi Arabia (SA)** | 12:00–15:00 | 15 Jun – 15 Sep | None | MHRSD / National Council for OSH |
| **UAE (AE)** | 12:30–15:00 | 15 Jun – 15 Sep | None | Fines AED 5,000/worker (max AED 50,000); 8 h/day cap |
| **Kuwait (KW)** | 11:00–16:00 | 1 Jun – 31 Aug | None | Widest daily window in the GCC |
| **Oman (OM)** | 12:30–15:30 | 1 Jun – 31 Aug | None | |
| **Bahrain (BH)** | 12:00–16:00 | 15 Jun – 31 Aug | None | |
| **Qatar (QA)** | 10:00–15:30 | 1 Jun – 15 Sep | **WBGT > 32.1 °C** | Only GCC state with a condition-based WBGT trigger in law |

## Design limitations (documented failure modes)

1. **Season start too late** — Bans typically begin in June; extreme heat can arrive in May (e.g. Dubai May 2025 before UAE ban).
2. **Fixed clock window** — Humid mornings and evenings outside the ban can exceed safe WBGT while work is permitted.
3. **No acclimatization** — New arrivals receive the same calendar protection as 10-year veterans.
4. **Direct-sun framing** — Shaded high-humidity work is largely unaddressed.
5. **Over-restriction** — Safe workable hours inside the ban window are still prohibited.

## HeatGuard comparison

HeatGuard replaces the calendar with **hourly WBGT** (ISO 7243 work-rest cycles), **worker acclimatization** (NIOSH ramp), and a **tamper-evident compliance log**. The demo quantifies *gap hours* — dangerous conditions HeatGuard flags that the calendar ban misses.

**Source:** Published GCC occupational health regulations; see per-country notes in sibling files in this directory.
