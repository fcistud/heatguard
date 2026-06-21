# Qatar outdoor work ban and WBGT cutoff

## Rule (as applied in HeatGuard)

- **Country code:** QA (Qatar)
- **Season:** 1 June – 15 September
- **Daily prohibited window:** 10:00 – 15:30 (local time)
- **WBGT condition:** Outdoor work must stop when **WBGT exceeds 32.1 °C** (regardless of clock time, when enforced)

Qatar is the **only GCC state** in HeatGuard's model with an explicit WBGT-based trigger alongside the calendar window.

## Why 32.1 °C matters

32.1 °C WBGT is a high threshold relative to ACGIH screening tables for heavy work (often 27–28 °C for acclimatized workers at 100% allocation). A worker can face physiologically unsafe conditions **below** the legal WBGT cutoff while the calendar still permits work.

## HeatGuard comparison

HeatGuard applies ISO 7243 / ACGIH step tables and ISO 7933 physiology **continuously**, not only above 32.1 °C. The Doha weather archive in `data/cache/` supports season-level gap analysis similar to Dubai and Riyadh demos.

## References

- Qatar Ministry of Labour summer working hours regulations
- HeatGuard: `calendar_ban.GCC_BANS["QA"]`
