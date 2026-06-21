import type { Advisory, Timeline, TimelineRow, WbgtSource } from "../types";
import {
  SIGNAL_COLOR,
  SIGNAL_LABEL,
  SIGNAL_SHORT,
  WBGT_SOURCE_LABEL,
} from "../lib/signals";
import { Logo } from "./ui/Brand";

type WorkerKey = "veteran" | "newcomer";

interface Props {
  siteName: string;
  demos: string[];
  selectedSite: string;
  onSelectSite: (key: string) => void;

  timeline: Timeline;
  currentRow: TimelineRow;
  advisory: Advisory;
  wbgt: number;
  source: WbgtSource;
  banned: boolean;

  selectedHour: number;
  onSelectHour: (hour: number) => void;

  worker: WorkerKey;
  onSelectWorker: (w: WorkerKey) => void;
  newcomerDays: number;
}

function pretty(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/** One plain-English instruction line for the current signal. */
function plainInstruction(adv: Advisory): string {
  const work = Math.round(adv.cycle.work_min_per_hour);
  const rest = Math.round(adv.cycle.rest_min_per_hour);
  const cups = Math.max(1, Math.round(adv.hydration.cups_250ml_per_h));
  switch (adv.signal) {
    case "STOP":
      return `Too hot to work safely. Stop outdoor work and move the crew to shade or indoors. Keep drinking water — about ${cups} cups this hour.`;
    case "DRINK_NOW":
      return `Drink now, then keep going. Work ${work} min, rest ${rest} min in shade. Drink ~${cups} cups this hour.`;
    case "REST_IN_SHADE":
      return `Take it easy. Work ${work} min, then rest ${rest} min in the shade. Drink ~${cups} cups this hour.`;
    case "WORK":
    default:
      return `Safe to work. Work ${work} min, rest ${rest} min in shade. Drink ~${cups} cups this hour.`;
  }
}

/** One-sentence "why" behind the call. */
function plainWhy(adv: Advisory, wbgt: number): string {
  if (adv.signal === "STOP") {
    return `The heat index (WBGT) is ${wbgt.toFixed(0)}°C — high enough to risk heat illness, so work pauses.`;
  }
  if (adv.signal === "WORK") {
    return `The heat index (WBGT) is ${wbgt.toFixed(0)}°C — manageable with normal breaks and water.`;
  }
  return `The heat index (WBGT) is ${wbgt.toFixed(0)}°C — workable, but only with shorter work bursts, shade breaks and steady water.`;
}

/** Plain-language WBGT band. */
function wbgtMeaning(wbgt: number): string {
  if (wbgt >= 32) return "extreme heat stress — dangerous for hard outdoor work";
  if (wbgt >= 30) return "high heat stress — work must be paced with rest and water";
  if (wbgt >= 28) return "moderate heat stress — take regular shade breaks";
  if (wbgt >= 25) return "some heat stress — stay hydrated";
  return "low heat stress — comfortable working conditions";
}

export function SimpleView({
  siteName,
  demos,
  selectedSite,
  onSelectSite,
  timeline,
  currentRow,
  advisory,
  wbgt,
  source,
  banned,
  selectedHour,
  onSelectHour,
  worker,
  onSelectWorker,
  newcomerDays,
}: Props) {
  const color = SIGNAL_COLOR[advisory.signal];
  const hours = timeline.rows.map((r) => r.hour);
  const idx = hours.indexOf(selectedHour);
  const prevHour = idx > 0 ? hours[idx - 1] : null;
  const nextHour = idx >= 0 && idx < hours.length - 1 ? hours[idx + 1] : null;

  const banSays = banned ? "BANNED" : "PERMITTED";
  const hgSays = SIGNAL_LABEL[advisory.signal];
  // Where ban and HeatGuard disagree, call it out plainly.
  const banMissesDanger = !banned && advisory.signal === "STOP";
  const banOverCautious = banned && advisory.signal === "WORK";

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-1">
      {/* Header line: site + worker */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Logo />
          <div>
            <div className="text-lg font-display font-bold text-slate-900 dark:text-slate-50">
              {siteName}
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              {currentRow.time} · {worker === "veteran" ? "Experienced worker" : `New worker (day ${newcomerDays})`}
            </div>
          </div>
        </div>

        {/* Site + worker toggles */}
        <div className="flex flex-wrap items-center gap-2">
          {demos.length > 1 && (
            <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-sm font-semibold dark:border-slate-700 dark:bg-slate-800">
              {demos.map((d) => (
                <button
                  key={d}
                  onClick={() => onSelectSite(d)}
                  className={`rounded-md px-3 py-1 transition ${
                    selectedSite === d
                      ? "bg-slate-900 text-white dark:bg-slate-200 dark:text-slate-900"
                      : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
                  }`}
                >
                  {pretty(d)}
                </button>
              ))}
            </div>
          )}
          <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-sm font-semibold dark:border-slate-700 dark:bg-slate-800">
            <button
              onClick={() => onSelectWorker("veteran")}
              className={`rounded-md px-3 py-1 transition ${
                worker === "veteran"
                  ? "bg-emerald-500 text-white"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              Experienced
            </button>
            <button
              onClick={() => onSelectWorker("newcomer")}
              className={`rounded-md px-3 py-1 transition ${
                worker === "newcomer"
                  ? "bg-heat-orange text-white"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              New worker
            </button>
          </div>
        </div>
      </div>

      {/* Hour picker */}
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <button
          type="button"
          disabled={prevHour == null}
          onClick={() => prevHour != null && onSelectHour(prevHour)}
          className="grid h-10 w-10 place-items-center rounded-xl border border-slate-300 text-lg text-slate-600 transition hover:bg-slate-100 disabled:opacity-30 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          aria-label="Previous hour"
        >
          ‹
        </button>
        <div className="text-center">
          <div className="text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
            Showing the hour
          </div>
          <div className="font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-50">
            {currentRow.time}
          </div>
        </div>
        <button
          type="button"
          disabled={nextHour == null}
          onClick={() => nextHour != null && onSelectHour(nextHour)}
          className="grid h-10 w-10 place-items-center rounded-xl border border-slate-300 text-lg text-slate-600 transition hover:bg-slate-100 disabled:opacity-30 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          aria-label="Next hour"
        >
          ›
        </button>
      </div>

      {/* The big signal */}
      <div
        className="rounded-3xl p-8 text-white shadow-card"
        style={{ backgroundColor: color }}
      >
        <div className="text-xs font-semibold uppercase tracking-widest text-white/80">
          Right now the crew should
        </div>
        <div className="mt-2 font-display text-5xl font-bold leading-none tracking-tight sm:text-6xl">
          {SIGNAL_LABEL[advisory.signal]}
        </div>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-white/95">
          {plainInstruction(advisory)}
        </p>
      </div>

      {/* Right now: ban vs HeatGuard */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <div className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Right now
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800">
            <div className="text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
              The calendar ban would say
            </div>
            <div
              className={`mt-1 font-display text-xl font-bold ${
                banned ? "text-heat-red" : "text-emerald-600 dark:text-emerald-400"
              }`}
            >
              {banSays}
            </div>
          </div>
          <div
            className="rounded-xl border px-4 py-3"
            style={{ borderColor: color, backgroundColor: `${color}14` }}
          >
            <div className="text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
              HeatGuard says
            </div>
            <div
              className="mt-1 font-display text-xl font-bold"
              style={{ color }}
            >
              {hgSays}
            </div>
          </div>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          {banMissesDanger
            ? `The fixed calendar ban would let work continue — but the real conditions are dangerous, so HeatGuard calls a ${SIGNAL_SHORT[advisory.signal]}.`
            : banOverCautious
              ? `The fixed calendar ban would halt all work — but conditions are actually safe, so HeatGuard allows normal work.`
              : `${plainWhy(advisory, wbgt)}`}
        </p>
      </div>

      {/* Conditions */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Conditions
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            <span className="h-1.5 w-1.5 rounded-full bg-heat-orange" />
            {WBGT_SOURCE_LABEL[source] ?? source}
          </span>
        </div>

        <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-display text-4xl font-bold tabular-nums text-slate-900 dark:text-slate-50">
            {wbgt.toFixed(0)}°C
          </span>
          <span className="text-sm font-semibold text-slate-500 dark:text-slate-400">
            heat index (WBGT)
          </span>
        </div>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          What it means: {wbgtMeaning(wbgt)}. WBGT blends temperature, humidity,
          sun and wind, so it reflects real heat stress far better than air
          temperature alone.
        </p>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 px-4 py-3 text-center dark:bg-slate-800">
            <div className="text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Air temperature
            </div>
            <div className="mt-0.5 font-display text-2xl font-bold tabular-nums text-slate-800 dark:text-slate-100">
              {currentRow.tdb_c.toFixed(0)}°C
            </div>
          </div>
          <div className="rounded-xl bg-slate-50 px-4 py-3 text-center dark:bg-slate-800">
            <div className="text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Humidity
            </div>
            <div className="mt-0.5 font-display text-2xl font-bold tabular-nums text-slate-800 dark:text-slate-100">
              {Math.round(currentRow.rh_pct)}%
            </div>
          </div>
        </div>
      </div>

      {/* Acclimatization note — only for a new worker */}
      {worker === "newcomer" && (
        <div className="rounded-2xl border border-heat-orange/40 bg-orange-50 px-5 py-4 text-sm text-orange-900 dark:border-heat-orange/40 dark:bg-orange-950/40 dark:text-orange-200">
          <span className="font-semibold">New worker (day {newcomerDays}):</span>{" "}
          {advisory.cycle.capped_by_acclimatization
            ? "they aren't fully used to the heat yet, so HeatGuard keeps their work time shorter than usual until they build up over their first days on site."
            : "they're still building up to the heat, but right now the conditions — not the new-worker limit — set their schedule."}
        </div>
      )}

      <p className="pt-2 text-center text-xs text-slate-400 dark:text-slate-500">
        Simple view · one safety call per hour for {siteName}. Switch to Full for
        the analytics.
      </p>
    </div>
  );
}
