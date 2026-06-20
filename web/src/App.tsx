import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type {
  Advisory,
  DemoPayload,
  HourAdvisory,
  ImpactReport,
  Intensity,
  Timeline,
  TimelineRow,
  WbgtSource,
} from "./types";
import { TopBar } from "./components/TopBar";
import { Card } from "./components/ui/Card";
import { SignalTile } from "./components/SignalTile";
import { WbgtGauge } from "./components/WbgtGauge";
import { BanVsAdaptiveTimeline } from "./components/BanVsAdaptiveTimeline";
import { AcclimatizationTracker } from "./components/AcclimatizationTracker";
import { ComplianceFeed } from "./components/ComplianceFeed";
import { ImpactPanel } from "./components/ImpactPanel";
import { ScalePanel } from "./components/ScalePanel";
import { EconomicsPanel } from "./components/EconomicsPanel";
import { WhatIfPanel } from "./components/WhatIfPanel";
import { SIGNAL_SHORT } from "./lib/signals";

type WorkerKey = "veteran" | "newcomer";

const INTENSITY_OPTIONS: { value: Intensity; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "moderate", label: "Moderate" },
  { value: "heavy", label: "Heavy" },
  { value: "very_heavy", label: "Very heavy" },
];

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

  // Feature 1: per-worker job intensity + acclimatization (days on job).
  const [intensity, setIntensity] = useState<Intensity>("heavy");
  const [newcomerDays, setNewcomerDays] = useState<number>(0);

  // Feature 2: measured WBGT (sensor vs estimate).
  const [wbgtMode, setWbgtMode] = useState<"estimated" | "measured">("estimated");
  const [measuredWbgt, setMeasuredWbgt] = useState<number | null>(null);
  const [hourResult, setHourResult] = useState<HourAdvisory | null>(null);

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
        skipParamFetch.current = true; // demo timeline is already current
        setDemo(d);
        setTimeline(d.timeline);
        setImpact(d.impact);
        setActiveDay(d.focus_day);
        // Adopt the demo's job intensity as the default control value.
        setIntensity((d.timeline.intensity as Intensity | undefined) ?? d.intensity);
        setNewcomerDays((d.timeline.newcomer_days as number | undefined) ?? 0);
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

  // Shared cancellation guard for timeline param refetches (day + intensity +
  // tenure). A monotonic request id means a stale response can never clobber a
  // newer one — same idea as the original day-scrub guard.
  const paramTimer = useRef<number | null>(null);
  const paramReqId = useRef(0);
  // When true, the param-effect skips one run (the timeline is already current
  // after a demo load or an explicit day change handled by selectDay).
  const skipParamFetch = useRef(true);

  // 4) Day scrubbing -> /timeline/{site}/{day} (immediate; resets the hour).
  const selectDay = useCallback(
    (day: string) => {
      if (!siteKey || day === activeDay) {
        setActiveDay(day);
        return;
      }
      skipParamFetch.current = true; // selectDay owns this fetch
      setActiveDay(day);
      setLoadingDay(true);
      const reqId = ++paramReqId.current;
      api
        .timeline(siteKey, day, { intensity, newcomerDays })
        .then((tl) => {
          if (reqId !== paramReqId.current) return;
          setTimeline(tl);
          const gap = tl.rows.find((r) => r.gap);
          const noon = tl.rows.find((r) => r.hour === 12);
          setSelectedHour(gap?.hour ?? noon?.hour ?? tl.rows[0]?.hour ?? null);
        })
        .catch(() => {
          /* keep last good timeline */
        })
        .finally(() => {
          if (reqId === paramReqId.current) setLoadingDay(false);
        });
    },
    [siteKey, activeDay, intensity, newcomerDays],
  );

  // 5) Feature 1: re-fetch the timeline (debounced) when the job intensity or
  // the new-worker tenure changes, keeping the selected hour valid.
  useEffect(() => {
    if (!siteKey || !activeDay) return;
    if (skipParamFetch.current) {
      skipParamFetch.current = false;
      return;
    }
    if (paramTimer.current) window.clearTimeout(paramTimer.current);
    const reqId = ++paramReqId.current;
    setLoadingDay(true);
    paramTimer.current = window.setTimeout(() => {
      api
        .timeline(siteKey, activeDay, { intensity, newcomerDays })
        .then((tl) => {
          if (reqId !== paramReqId.current) return; // stale response — drop it
          setTimeline(tl);
          // Keep the selected hour if it still exists, else fall back.
          setSelectedHour((cur) => {
            if (cur != null && tl.rows.some((r) => r.hour === cur)) return cur;
            const gap = tl.rows.find((r) => r.gap);
            const noon = tl.rows.find((r) => r.hour === 12);
            return gap?.hour ?? noon?.hour ?? tl.rows[0]?.hour ?? null;
          });
        })
        .catch(() => {
          /* keep last good timeline */
        })
        .finally(() => {
          if (reqId === paramReqId.current) setLoadingDay(false);
        });
    }, 300);
    return () => {
      if (paramTimer.current) window.clearTimeout(paramTimer.current);
    };
  }, [intensity, newcomerDays, siteKey, activeDay]);

  const currentRow: TimelineRow | null = useMemo(() => {
    if (!timeline || selectedHour == null) return null;
    return timeline.rows.find((r) => r.hour === selectedHour) ?? null;
  }, [timeline, selectedHour]);

  // The estimated advisory straight from the timeline row (model WBGT).
  const estimatedAdvisory: Advisory | null = currentRow
    ? worker === "veteran"
      ? currentRow.veteran
      : currentRow.newcomer
    : null;

  // The newcomer advisory for the acclimatization note.
  const newcomerAdvisory = currentRow?.newcomer;

  // Feature 2: when the user switches to Measured mode, seed the meter input
  // with the current estimated WBGT so the slider opens "on" the estimate, and
  // clear any stale recompute. Re-seeds whenever the selected hour changes.
  const estimatedWbgt = currentRow?.wbgt_c ?? null;
  useEffect(() => {
    if (wbgtMode === "measured") {
      setMeasuredWbgt(estimatedWbgt);
    } else {
      setMeasuredWbgt(null);
      setHourResult(null);
    }
    // Re-seed when the hour/estimate changes too.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wbgtMode, selectedHour]);

  // Feature 2: debounced recompute of ONE hour against the on-site meter value.
  const hourTimer = useRef<number | null>(null);
  const hourReqId = useRef(0);
  useEffect(() => {
    if (
      wbgtMode !== "measured" ||
      !siteKey ||
      !activeDay ||
      selectedHour == null ||
      measuredWbgt == null
    ) {
      return;
    }
    if (hourTimer.current) window.clearTimeout(hourTimer.current);
    const reqId = ++hourReqId.current;
    const hour = selectedHour;
    hourTimer.current = window.setTimeout(() => {
      api
        .hour(siteKey, activeDay, hour, {
          worker,
          measuredWbgt,
          intensity,
          newcomerDays,
        })
        .then((res) => {
          if (reqId !== hourReqId.current) return; // stale response — drop it
          setHourResult(res);
        })
        .catch(() => {
          /* keep last good recompute */
        });
    }, 300);
    return () => {
      if (hourTimer.current) window.clearTimeout(hourTimer.current);
    };
  }, [
    wbgtMode,
    measuredWbgt,
    selectedHour,
    worker,
    intensity,
    newcomerDays,
    siteKey,
    activeDay,
  ]);

  // The advisory the hero row actually renders: measured recompute when in
  // Measured mode (and a recompute exists), else the timeline estimate.
  const measuredActive = wbgtMode === "measured" && hourResult != null;
  const effectiveAdvisory: Advisory | null = measuredActive
    ? hourResult!.advisory
    : estimatedAdvisory;
  const effectiveWbgt: number | null = measuredActive
    ? hourResult!.advisory.wbgt_c
    : estimatedWbgt;
  const effectiveSource: WbgtSource | null = measuredActive
    ? hourResult!.advisory.wbgt_source
    : (currentRow?.wbgt_source ?? null);
  // Did flipping to the meter change the recommended signal?
  const signalChanged =
    measuredActive &&
    estimatedAdvisory != null &&
    hourResult!.advisory.signal !== estimatedAdvisory.signal;

  const workerLabel =
    worker === "veteran" ? "Veteran" : `New worker (day ${newcomerDays})`;

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

            {/* 1b. Danger & scale — why this matters beyond one crew. */}
            <Card
              title="The danger & the scale"
              subtitle="what this prevents, projected to a workforce"
              className="border-rose-200"
            >
              <ScalePanel siteKey={siteKey} fetchScale={api.scale} />
            </Card>

            {/* 2-3. Hero row: signal tile + gauge */}
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                {effectiveAdvisory && currentRow ? (
                  <SignalTile
                    key={`${worker}-${currentRow.hour}-${activeDay}-${wbgtMode}-${measuredActive ? effectiveAdvisory.wbgt_c : "est"}`}
                    advisory={effectiveAdvisory}
                    time={currentRow.time}
                    workerLabel={workerLabel}
                  />
                ) : (
                  <Card title="Live signal">
                    <p className="text-sm text-slate-400">
                      Select an hour on the timeline below.
                    </p>
                  </Card>
                )}
              </div>
              <Card
                title="WBGT & conditions"
                subtitle="current selected hour"
                right={
                  <div
                    role="group"
                    aria-label="WBGT source"
                    className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-xs font-semibold"
                  >
                    <button
                      type="button"
                      aria-pressed={wbgtMode === "estimated"}
                      onClick={() => setWbgtMode("estimated")}
                      className={`rounded-md px-2.5 py-1 transition ${
                        wbgtMode === "estimated"
                          ? "bg-indigo-500 text-white"
                          : "text-slate-600"
                      }`}
                    >
                      Estimated
                    </button>
                    <button
                      type="button"
                      aria-pressed={wbgtMode === "measured"}
                      onClick={() => setWbgtMode("measured")}
                      className={`rounded-md px-2.5 py-1 transition ${
                        wbgtMode === "measured"
                          ? "bg-slate-900 text-white"
                          : "text-slate-600"
                      }`}
                    >
                      Measured
                    </button>
                  </div>
                }
              >
                {currentRow && effectiveAdvisory && effectiveWbgt != null ? (
                  <>
                    <WbgtGauge
                      wbgt={effectiveWbgt}
                      riskScore={effectiveAdvisory.risk_score}
                      airTemp={currentRow.tdb_c}
                      rh={currentRow.rh_pct}
                      source={effectiveSource ?? currentRow.wbgt_source}
                    />
                    {wbgtMode === "measured" && (
                      <div className="mt-4 border-t border-slate-100 pt-4">
                        <label
                          htmlFor="measured-wbgt"
                          className="flex items-center justify-between text-xs font-medium text-slate-500"
                        >
                          <span>On-site meter (WBGT °C)</span>
                          <span className="tabular-nums text-slate-700">
                            {(measuredWbgt ?? estimatedWbgt ?? 0).toFixed(1)}°C
                          </span>
                        </label>
                        <input
                          id="measured-wbgt"
                          type="range"
                          min={20}
                          max={45}
                          step={0.1}
                          value={measuredWbgt ?? estimatedWbgt ?? 30}
                          onChange={(e) =>
                            setMeasuredWbgt(Number(e.target.value))
                          }
                          className="mt-1 w-full accent-slate-900"
                        />
                        <p className="mt-2 text-xs text-slate-500">
                          Model estimate{" "}
                          <span className="font-semibold tabular-nums text-slate-700">
                            {estimatedWbgt?.toFixed(1)}°C
                          </span>{" "}
                          → meter{" "}
                          <span className="font-semibold tabular-nums text-slate-900">
                            {(measuredWbgt ?? estimatedWbgt ?? 0).toFixed(1)}°C
                          </span>
                        </p>
                        {signalChanged && (
                          <p className="mt-1.5 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-800">
                            ⚠ Signal changed on the meter reading:{" "}
                            <span className="font-semibold">
                              {SIGNAL_SHORT[estimatedAdvisory!.signal]}
                            </span>{" "}
                            →{" "}
                            <span className="font-semibold">
                              {SIGNAL_SHORT[hourResult!.advisory.signal]}
                            </span>
                          </p>
                        )}
                        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">
                          Drop in a ~$300 on-site WBGT meter and the same engine
                          runs on the measured value instead of the estimate.
                        </p>
                      </div>
                    )}
                  </>
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
                <div className="flex flex-wrap items-center justify-end gap-3">
                  <label className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                    <span>Job intensity</span>
                    <select
                      value={intensity}
                      onChange={(e) =>
                        setIntensity(e.target.value as Intensity)
                      }
                      className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-700 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                    >
                      {INTENSITY_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {worker === "newcomer" && (
                    <label className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
                      <span className="whitespace-nowrap tabular-nums">
                        new worker: day {newcomerDays}
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={14}
                        step={1}
                        value={newcomerDays}
                        onChange={(e) =>
                          setNewcomerDays(Number(e.target.value))
                        }
                        aria-label={`New worker days on job: ${newcomerDays}`}
                        className="w-28 accent-indigo-500"
                      />
                    </label>
                  )}

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
                      {worker === "newcomer"
                        ? `New worker (day ${newcomerDays})`
                        : "New worker"}
                    </button>
                  </div>
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
                newcomerDays={newcomerDays}
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

            {/* 6. Worker protection record (tamper-evident compliance log) */}
            <Card
              title="Worker protection record"
              subtitle="tamper-evident proof of protection — for the worker and the employer"
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
