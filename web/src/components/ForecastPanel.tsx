import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import type { ForecastTimeline, Signal } from "../types";
import { effectiveLane } from "../lib/advisoryLane";
import { Stat } from "./ui/Stat";

type WorkerKey = "veteran" | "newcomer";

function signalFor(row: ForecastTimeline["rows"][0], worker: WorkerKey): Signal {
  return effectiveLane(row, worker).signal;
}

function groupByDate(rows: ForecastTimeline["rows"]) {
  const out: { date: string; rows: ForecastTimeline["rows"] }[] = [];
  let cur: string | null = null;
  for (const r of rows) {
    if (r.date !== cur) {
      cur = r.date;
      out.push({ date: r.date, rows: [] });
    }
    out[out.length - 1].rows.push(r);
  }
  return out;
}

function formatDay(dateStr: string): string {
  const d = new Date(`${dateStr}T12:00:00`);
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function ForecastPanel({ siteKey }: { siteKey: string }) {
  const [data, setData] = useState<ForecastTimeline | null>(null);
  const [worker, setWorker] = useState<WorkerKey>("veteran");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .forecast(siteKey)
      .then(setData)
      .catch((e) => {
        setData(null);
        setError(e instanceof ApiError ? e.message : "Forecast unavailable");
      })
      .finally(() => setLoading(false));
  }, [siteKey]);

  useEffect(() => {
    load();
  }, [load]);

  const days = useMemo(() => (data ? groupByDate(data.rows) : []), [data]);

  const shiftStart = data?.summary.recommended_shift_start ?? null;
  const shiftEnd = data?.summary.recommended_shift_end ?? null;

  if (loading) {
    return (
      <p className="py-8 text-center text-sm text-slate-400">
        Loading Open-Meteo forecast…
      </p>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <p>{error}</p>
        <p className="mt-2 text-xs text-amber-800">
          Run <code className="rounded bg-white/80 px-1">heatguard fetch-datasets</code> to
          cache forecast data for this site.
        </p>
        <button
          type="button"
          onClick={load}
          className="mt-3 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const { summary } = data;

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-sky-200 bg-gradient-to-r from-sky-50 to-indigo-50 px-4 py-3">
        <p className="text-sm font-medium text-slate-800">{summary.headline}</p>
        <p className="mt-1 text-xs text-slate-500">
          Open-Meteo forecast · {data.forecast_days} day(s) ahead + {data.past_days} past ·{" "}
          {data.intensity.replace("_", " ")} work · veteran shift window uses full{" "}
          <span className="font-semibold text-emerald-700">WORK</span> hours only
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label="Danger hours"
          value={summary.danger_hours}
          accent="stop"
          hint="STOP or REST in forecast window"
        />
        <Stat
          label="Safe WORK hours"
          value={summary.work_hours_permitted}
          accent="work"
          hint="Veteran · full-work signal"
        />
        <Stat
          label="Shift start"
          value={shiftStart ?? "—"}
          accent="work"
          hint="Earliest full-work hour"
        />
        <Stat
          label="Shift end"
          value={shiftEnd ?? "—"}
          accent="rest"
          hint="Latest full-work hour"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-medium text-slate-600">
          <span>Worker lane</span>
          <button
            type="button"
            onClick={() => setWorker("veteran")}
            className={`rounded-full px-3 py-1 ${
              worker === "veteran"
                ? "bg-slate-900 text-white"
                : "border border-slate-200 bg-white text-slate-600"
            }`}
          >
            Veteran
          </button>
          <button
            type="button"
            onClick={() => setWorker("newcomer")}
            className={`rounded-full px-3 py-1 ${
              worker === "newcomer"
                ? "bg-slate-900 text-white"
                : "border border-slate-200 bg-white text-slate-600"
            }`}
          >
            New worker
          </button>
        </div>
        <button
          type="button"
          onClick={load}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm hover:border-slate-300"
        >
          Refresh
        </button>
      </div>

      <div className="space-y-4">
        {days.map(({ date, rows }) => (
          <div key={date}>
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <span className="text-sm font-semibold text-slate-800">{formatDay(date)}</span>
              <span className="text-xs text-slate-400">{date}</span>
            </div>
            <div className="flex gap-1">
              {rows.map((r) => {
                const sig = signalFor(r, worker);
                const inShift =
                  shiftStart &&
                  shiftEnd &&
                  r.time >= shiftStart &&
                  r.time <= shiftEnd &&
                  worker === "veteran" &&
                  r.veteran.signal === "WORK";
                return (
                  <div
                    key={`${r.date}-${r.time}`}
                    className="flex min-w-0 flex-1 flex-col items-center gap-1"
                    title={`${r.time} · WBGT ${r.wbgt_c}°C · ${SIGNAL_SHORT[sig]}${r.banned ? " · calendar ban" : ""}`}
                  >
                    <div
                      className={`h-8 w-full rounded-md transition ${
                        inShift ? "ring-2 ring-emerald-400 ring-offset-1" : ""
                      } ${r.banned ? "opacity-50" : ""}`}
                      style={{ backgroundColor: SIGNAL_COLOR[sig] }}
                    />
                    <span className="text-[9px] font-medium tabular-nums text-slate-500">
                      {r.time.slice(0, 5)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-slate-500">
        {(["WORK", "REST_IN_SHADE", "DRINK_NOW", "STOP"] as Signal[]).map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: SIGNAL_COLOR[s] }}
            />
            {SIGNAL_SHORT[s]}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm ring-2 ring-emerald-400" />
          Recommended shift (veteran WORK)
        </span>
      </div>
    </div>
  );
}
