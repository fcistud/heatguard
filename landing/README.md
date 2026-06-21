# HeatGuard — landing page

A polished, self-contained marketing landing page for HeatGuard. It condenses the
project's story and showcases the danger, the scale, lives saved, productivity, and ROI.

## What's here

```
landing/
  index.html      the entire page — inline <style> + one tiny inline <script>
  img/            committed screenshots referenced by index.html
    02_top.png            live signal tile + WBGT gauge
    03_timeline.png       calendar-ban-vs-HeatGuard centerpiece
    04_impact.png         season impact / ROI panel
    09_riyadh_newcomer.png  the unacclimatized-newcomer danger
    10_measured.png       estimated vs on-site-meter reading
  README.md       this file
```

No build step, no external CSS/JS frameworks. The only network dependency is a Google
Fonts `<link>`; if it's blocked, the page degrades gracefully to system fonts. The
count-up animation and the impact-at-scale tabs are plain vanilla JS with no dependencies.

## View it locally

Just open the file in any browser — it works over `file://`:

```bash
open landing/index.html          # macOS
xdg-open landing/index.html      # Linux
```

Or serve it (so relative image paths behave exactly as on a host):

```bash
python3 -m http.server -d landing 8080
# then visit http://localhost:8080
```

The hero's "Live dashboard" buttons point at `http://localhost:5173` (the React
dashboard from the main project) and "GitHub" at the repo.

## Deploy to GitHub Pages

The page is fully static and relative-path safe, so it deploys as-is.

- **Option A — `/docs` or a `gh-pages` branch:** copy the contents of `landing/`
  (`index.html` + `img/`) to the published folder/branch and enable Pages in the repo
  settings.
- **Option B — GitHub Actions:** upload `landing/` as the Pages artifact. Because all
  asset paths are relative (`img/...`), it works under a project subpath
  (`https://<user>.github.io/<repo>/`) with no base-href changes.

## Notes

- Scale figures (5,000 / 100,000 / 5,000,000 workers) are labelled illustrative and
  conservative on the page. The per-100-worker crew numbers and the Nicaragua back-test
  are the verifiable backbone.
- This is marketing material for a prototype, not certified safety equipment.
