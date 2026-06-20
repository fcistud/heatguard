# HeatGuard — Supervisor Dashboard

The pitch demo UI for **HeatGuard**, an adaptive heat-safety scheduler for
outdoor labour crews in the Gulf. Vite + React + TypeScript + Tailwind.

It visualizes how WBGT-driven adaptive scheduling beats a blunt calendar ban:
a live work/rest/hydrate signal, a WBGT gauge, an hourly **calendar-ban vs
HeatGuard** timeline (with the dangerous hours the ban misses flagged), an
acclimatization tracker, a tamper-evident compliance log, a season impact panel
(validated against Nicaragua), and a live "what-if" decision engine.

## Prerequisites

- Node 24 / npm 11 (any recent Node 18+ works)
- The HeatGuard FastAPI backend running.

## 1. Start the API first (from the repo root)

```bash
pip install -e .
uvicorn heatguard.api:app
```

This serves on `http://localhost:8000` with permissive CORS. If the demo
weather isn't cached yet, run `heatguard fetch-demo` once.

## 2. Run the dashboard

```bash
cd web
npm install
npm run dev
```

Then open the printed local URL (Vite defaults to `http://localhost:5173`).

## Configuration

The frontend reads the backend base URL from `VITE_API_BASE`, defaulting to
`http://localhost:8000`. To point at a different host, copy `.env.example` to
`.env` and edit it:

```bash
cp .env.example .env
# VITE_API_BASE=http://my-host:8000
```

## Build

```bash
npm run build      # type-checks (tsc -b) then bundles to dist/
npm run preview    # serve the production build locally
```

## Project layout

```
web/
  src/
    api.ts                 # fetch helpers + configurable base URL
    types.ts               # TypeScript mirrors of the API JSON shapes
    App.tsx                # page orchestration, data fetching, state
    lib/signals.ts         # signal colors, risk-color ramp, labels
    components/
      TopBar.tsx
      SignalTile.tsx               # hero live signal + intra-hour simulation
      WbgtGauge.tsx                # semicircle WBGT / risk gauge (SVG)
      BanVsAdaptiveTimeline.tsx    # the centerpiece two-lane timeline
      AcclimatizationTracker.tsx   # NIOSH staged re-entry ramp
      ComplianceFeed.tsx           # hash-chained log table + CSV export
      ImpactPanel.tsx              # impact stat cards + backtest
      WhatIfPanel.tsx              # live POST /decide
      ui/Card.tsx, ui/Stat.tsx     # small primitives
```

## Signal colors

WORK `#16a34a` · REST_IN_SHADE `#f59e0b` · DRINK_NOW `#0ea5e9` · STOP `#dc2626`.
