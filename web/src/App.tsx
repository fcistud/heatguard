import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { DemoPayload, ImpactReport, Timeline, TimelineRow } from "./types";
import { TopBar } from "./components/TopBar";
import { Card } from "./components/ui/Card";
import { SignalTile } from "./components/SignalTile";
import { WbgtGauge } from "./components/WbgtGauge";
import { BanVsAdaptiveTimeline } from "./components/BanVsAdaptiveTimeline";
import { AcclimatizationTracker } from "./components/AcclimatizationTracker";
import { ComplianceFeed } from "./components/ComplianceFeed";
import { ImpactPanel } from "./components/ImpactPanel";
import { EconomicsPanel } from "./components/EconomicsPanel";
import { WhatIfPanel } from "./components/WhatIfPanel";

type WorkerKey = "veteran" | "newcomer";

function ApiDownBanner({ message }: { message: string }) {
  return (
    <div className="mx-auto mt-24 max-w-xl rounded-2xl border border-red-200 bg-white p-8 text-center shadow-card">
      <div className="text-4xl">🌡️</div>
      <h2 className="mt-3 text-lg font-bold text-slate-900">
        Can't reach the HeatGuard API
      </h2>
      <p className="mt-1 text-sm text-slate-500">{message}</p>
      <div className="mt-4 rounded-lg bg-slate-900 px-4 py-3 text-left font-mono text-xs text-slate-100">
        # from the repo root
        <br />
        pip install -e .
        <br />
        uvicorn heatguard.api:app
      </div>
      <p className="mt-3 text-xs text-slate-400">
        The dashboard reads <code>VITE_API_BASE</code> (default{" "}
        <code>http://localhost:8000</code>).
      </p>
    </div>
  );
}

function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-24 text-slate-400">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      {label}
    </div>
  );
}

export default function App() {
  const [demos, setDemos] = useState<string[]>([]);
  const [siteKey, setSiteKey] = useState<string>("");
  const [crew, setCrew] = useState<number>(100);

  const [demo, setDemo] = useState<DemoPayload | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [impact, setImpact] = useState<ImpactReport | null>(null);

  const [worker, setWorker] = useState<WorkerKey>("veteran");
  const [selectedHour, setSelectedHour] = useState<number | null>(null);
  const [activeDay, setActiveDay] = useState<string>("");

  const [loading, setLoading] = useState(true);
  const [loadingDay, setLoadingDay] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 1) Discover demos on mount.
  useEffect(() => {
    let cancelled = false;
    api
      .demos()
      .then((d) => {
        if (cancelled) return;
        setDemos(d);
        setSiteKey((cur) => cur || d[0] || "");
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "Failed to load demos");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 2) Load the full demo payload whenever the site changes.
  useEffect(() => {
    if (!siteKey) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .demo(siteKey, crew)
      .then((d) => {
        if (cancelled) return;
        setDemo(d);
        setTimeline(d.timeline);
        setImpact(d.impact);
        setActiveDay(d.focus_day);
        // default selected hour: first gap, else noon-ish, else first row
        const gap = d.timeline.rows.find((r) => r.gap);
        const noon = d.timeline.rows.find((r) => r.hour === 12);
        setSelectedHour(
          gap?.hour ?? noon?.hour ?? d.timeline.rows[0]?.hour ?? null,
        );
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "Failed to load demo");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // crew intentionally excluded — handled by the debounced effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteKey]);

  // 3) Re-fetch impact (debounced) when crew changes.
  const crewTimer = useRef<number | null>(null);
  useEffect(() => {
    if (!siteKey) return;
    if (crewTimer.current) window.clearTimeout(crewTimer.current);
    crewTimer.current = window.setTimeout(() => {
      api
        .impact(siteKey, crew)
        .then(setImpact)
        .catch(() => {
          /* keep last good impact */
        });
    }, 350);
    return () => {
      if (crewTimer.current) window.clearTimeout(crewTimer.current);
    };
  }, [crew, siteKey]);

  // 4) Day scrubbing -> /timeline/{site}/{day}
  const selectDay = useCallback(
    (day: string) => {
      if (!siteKey || day === activeDay) {
        setActiveDay(day);
        return;
      }
      setActiveDay(day);
      setLoadingDay(true);
      api
        .timeline(siteKey, day)
        .then((tl) => {
          setTimeline(tl);
          const gap = tl.rows.find((r) => r.gap);
          const noon = tl.rows.find((r) => r.hour === 12);
          setSelectedHour(gap?.hour ?? noon?.hour ?? tl.rows[0]?.hour ?? null);
        })
        .catch(() => {
          /* keep last good timeline */
        })
        .finally(() => setLoadingDay(false));
    },
    [siteKey, activeDay],
  );

  const currentRow: TimelineRow | null = useMemo(() => {
    if (!timeline || selectedHour == null) return null;
    return timeline.rows.find((r) => r.hour === selectedHour) ?? null;
  }, [timeline, selectedHour]);

  const currentAdvisory = currentRow
    ? worker === "veteran"
      ? currentRow.veteran
      : currentRow.newcomer
    : null;

  // The newcomer advisory for the acclimatization note.
  const newcomerAdvisory = currentRow?.newcomer;

  if (error && !demo) {
    return (
      <div className="min-h-screen">
        <TopBar
          demos={demos}
          selected={siteKey}
          onSelect={setSiteKey}
          crew={crew}
          onCrew={setCrew}
        />
        <ApiDownBanner message={error} />
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-16">
      <TopBar
        demos={demos}
        selected={siteKey}
        onSelect={setSiteKey}
        crew={crew}
        onCrew={setCrew}
      />

      <main className="mx-auto max-w-7xl space-y-6 px-5 pt-6">
        {loading || !demo || !timeline || !impact ? (
          <Spinner label="Loading demo…" />
        ) : (
          <>
            {/* 1. Headline banner */}
            <div className="rounded-2xl border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50 p-5 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h1 className="text-xl font-bold text-slate-900">
                    {demo.headline}
                  </h1>
                  <p className="mt-1 text-sm text-slate-600">
                    {demo.ban.description}
                  </p>
                </div>
                <div className="rounded-xl border border-amber-300 bg-white px-4 py-2 text-center">
                  <div className="text-[11px] uppercase tracking-wide text-slate-400">
                    Season peak
                  </div>
                  <div className="text-2xl font-bold tabular-nums text-red-600">
                    {demo.peak.tdb_c.toFixed(1)}°C
                  </div>
                  <div className="text-[11px] text-slate-400">
                    {demo.peak.when}
                  </div>
                </div>
              </div>
            </div>

            {/* 2-3. Hero row: signal tile + gauge */}
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                {currentAdvisory && currentRow ? (
                  <SignalTile
                    key={`${worker}-${currentRow.hour}-${activeDay}`}
                    advisory={currentAdvisory}
                    time={currentRow.time}
                    workerLabel={
                      worker === "veteran" ? "Veteran" : "New worker (day 0)"
                    }
                  />
                ) : (
                  <Card title="Live signal">
                    <p className="text-sm text-slate-400">
                      Select an hour on the timeline below.
                    </p>
                  </Card>
                )}
              </div>
              <Card title="WBGT & conditions" subtitle="current selected hour">
                {currentRow && currentAdvisory ? (
                  <WbgtGauge
                    wbgt={currentRow.wbgt_c}
                    riskScore={currentAdvisory.risk_score}
                    airTemp={currentRow.tdb_c}
                    rh={currentRow.rh_pct}
                    source={currentRow.wbgt_source}
                  />
                ) : (
                  <p className="text-sm text-slate-400">No hour selected.</p>
                )}
              </Card>
            </div>

            {/* 4. The centerpiece timeline */}
            <Card
              title="Calendar ban vs HeatGuard"
              subtitle="hourly · click an hour to inspect it"
              right={
                <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-xs font-semibold">
                  <button
                    onClick={() => setWorker("veteran")}
                    className={`rounded-md px-2.5 py-1 transition ${
                      worker === "veteran"
                        ? "bg-emerald-500 text-white"
                        : "text-slate-600"
                    }`}
                  >
                    Veteran
                  </button>
                  <button
                    onClick={() => setWorker("newcomer")}
                    className={`rounded-md px-2.5 py-1 transition ${
                      worker === "newcomer"
                        ? "bg-indigo-500 text-white"
                        : "text-slate-600"
                    }`}
                  >
                    New worker (day 0)
                  </button>
                </div>
              }
            >
              <BanVsAdaptiveTimeline
                timeline={timeline}
                worker={worker}
                selectedHour={selectedHour}
                onSelectHour={setSelectedHour}
                availableDays={demo.available_days}
                focusDay={activeDay}
                onSelectDay={selectDay}
                loadingDay={loadingDay}
              />
            </Card>

            {/* 5. Acclimatization tracker */}
            <Card title="Acclimatization tracker" subtitle="NIOSH staged re-entry">
              <AcclimatizationTracker
                worker={worker}
                newcomerAdvisory={newcomerAdvisory}
              />
            </Card>

            {/* 7. Impact panel */}
            <Card
              title="Season impact"
              subtitle={`crew of ${impact.crew_size} · vs the calendar ban`}
            >
              <ImpactPanel impact={impact} />
            </Card>

            {/* 7b. Business case / ROI panel */}
            {demo.economics && (
              <Card
                title="Business case & ROI"
                subtitle={`crew of ${demo.economics.crew_size} · conservative, tunable assumptions`}
              >
                <EconomicsPanel
                  economics={demo.economics}
                  sensitivity={demo.sensitivity}
                  siteKey={siteKey}
                  crew={crew}
                  fetchEconomics={api.economics}
                  fetchSensitivity={api.sensitivity}
                />
              </Card>
            )}

            {/* 6. Compliance feed */}
            <Card
              title="Compliance log"
              subtitle={`${demo.site.name} · focus day ${demo.focus_day}`}
            >
              <ComplianceFeed
                compliance={demo.compliance}
                siteKey={demo.site.key}
              />
            </Card>

            {/* 8. What-if */}
            <Card
              title="What-if — live engine"
              subtitle="POST /decide · proves the engine is live, not canned"
            >
              <WhatIfPanel siteKey={siteKey} />
            </Card>

            <footer className="pt-2 text-center text-xs text-slate-400">
              HeatGuard · WBGT-driven work-rest-hydration scheduler · demo data for{" "}
              {demo.site.name}, {demo.site.country}
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
