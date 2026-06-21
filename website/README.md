# HeatGuard documentation website

A self-contained, static documentation site for HeatGuard. Plain HTML + one shared
`styles.css` + a tiny `app.js` (theme toggle + mobile nav). No build step, no framework, no
bundler. The only network dependency is a Google Fonts `<link>`; everything else works over
`file://`.

## Pages

| File | Page |
|---|---|
| `index.html` | Overview — the one-minute pitch, the danger & scale, links to the demo and repo |
| `problem.html` | The problem — the GCC calendar ban (wrong in both directions), the danger, the AKI/heat science |
| `solution.html` | The solution — the four things it does; why site-level, not a wearable |
| `science.html` | How it works — WBGT, ACGIH work-rest, ISO 7933 PHS, NIOSH acclimatization, the decision logic, the compliance log (plain then technical) |
| `data.html` | Data & research — the datasets with access tags, the standards, the Nicaragua evidence, the honest gaps |
| `roi.html` | Impact, ROI & claims — the formulas, the Dubai/Riyadh worked examples, the per-claim confidence table |
| `faq.html` | The full FAQ |
| `roadmap.html` | Roadmap & next steps — cheap wearables, demographic personalisation, heart-rate/sweat integration, and more |
| `glossary.html` | Glossary |

Shared assets: `styles.css` (light + dark themes via CSS variables) and `app.js` (theme
toggle persisted to `localStorage`, mobile nav drawer).

## View locally

Just open the file — no server needed:

```bash
open index.html          # macOS
xdg-open index.html      # Linux
start index.html         # Windows
```

Or, if you prefer to serve it (any static server works):

```bash
python3 -m http.server 8080   # then visit http://localhost:8080
```

The "Live demo" link in the sidebar points at `http://localhost:5173` (the React dashboard);
the "GitHub" link points at `https://github.com/fcistud/heatguard`.

## Theme

The site defaults to **dark**. On the first visit it respects your operating-system
`prefers-color-scheme`; after that your choice (from the sidebar toggle) is remembered in
`localStorage` under the key `heatguard-theme`.

## Deploy to GitHub Pages

All links are **relative**, so the site deploys unchanged. Two common options:

**Option A — publish the `/website` folder from `main`:**

1. Push this repo to GitHub.
2. Repo → **Settings → Pages**.
3. Source: **Deploy from a branch**. Branch: `main`, folder: `/website` (if `/website` is not
   offered, use the `/docs` option below or move the files).
4. Save. The site appears at `https://<user>.github.io/<repo>/`.

**Option B — GitHub Actions (any folder):**

Add `.github/workflows/pages.yml`:

```yaml
name: Deploy docs site
on:
  push:
    branches: [main]
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: website
      - id: deployment
        uses: actions/deploy-pages@v4
```

Then set repo → **Settings → Pages → Source: GitHub Actions**.

Because there is no build step and every internal link is relative, the same files work over
`file://`, from a local static server, and from any GitHub Pages sub-path.
