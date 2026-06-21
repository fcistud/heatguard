# UAE midday work ban (outdoor labour)

## Rule (as applied in HeatGuard)

- **Country code:** AE (United Arab Emirates)
- **Season:** 15 June – 15 September (each year)
- **Daily prohibited window:** 12:30 – 15:00 (local time)
- **Scope:** Outdoor work in direct sunlight during the prohibited period
- **WBGT condition:** None — the rule is calendar- and clock-based only

## Enforcement (published figures used in ROI model)

- Fine of **AED 5,000 per affected worker**
- Maximum aggregate fine **AED 50,000** per violation event
- Additional requirements often cited: shaded rest areas, maximum 8 working hours per day in summer

## Policy gap vs adaptive scheduling

The UAE ban does **not** activate before 15 June. HeatGuard's Dubai demo (May 2025 Open-Meteo archive) shows dangerous WBGT hours in **May** when the calendar permits work.

The ban also does **not** cover:

- Humid morning hours before 12:30
- Evening hours after 15:00
- Unacclimatized workers needing stricter Action-Limit thresholds

## References

- UAE Ministry of Human Resources and Emiratisation (MOHRE) summer midday work restrictions
- HeatGuard encodes this rule in `src/heatguard/calendar_ban.py` for reproducible gap analysis
