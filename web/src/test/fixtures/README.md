Fixtures derived from `tests/golden/dubai/hourly.json` for WO-004 frontend parity tests.
DRINK_NOW and measured provenance are synthetic overlays on golden advisories.

`legal_lanes_banned.json` is the canonical banned-hour four-lane payload (WO-014)
from the committed Riyadh 2024-07-15 cache, hour 12. Regenerate with:

```
uv run python -c "
from datetime import date
from heatguard import canonical
from heatguard._paths import _REPO_ROOT
from heatguard.service import timeline_for_day
tl = timeline_for_day('riyadh', date(2024, 7, 15))
row = next(r for r in tl['rows'] if r['hour'] == 12)
payload = {
    'site': tl['site'],
    'date': tl['date'],
    'hour': row['hour'],
    'veteran': row['veteran'],
    'newcomer': row['newcomer'],
    'veteran_effective': row['veteran_effective'],
    'newcomer_effective': row['newcomer_effective'],
    'legal': row['legal'],
}
canonical.dump(payload, _REPO_ROOT / 'web' / 'src' / 'test' / 'fixtures' / 'legal_lanes_banned.json')
"
```
