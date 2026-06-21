import { useEffect, useRef, useState } from "react";
import type { ScaleResponse } from "../types";

interface Props {
  /** The selected site — the projection follows it. */
  siteKey: string;
  /** Same fetch helper App owns, injected to mirror EconomicsPanel's pattern. */
  fetchScale: (siteKey: string, workforce: number) => Promise<ScaleResponse>;
}

/** Compact big-number formatter: 7_670 -> "7,670", 124_000_000 -> "124M". */
function compact(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000_000)
    return `${trim(n / 1_000_000_000)}B`;
  if (abs >= 1_000_000) return `${trim(n / 1_000_000)}M`;
  if (abs >= 100_000) return `${trim(n / 1_000)}K`;
  return Math.round(n).toLocaleString();
}

/** Trim to at most 1 decimal, dropping a trailing ".0". */
function trim(n: number): string {
  const r = Math.round(n * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
}

/** Compact lo–hi band, e.g. "32–50M", collapsing to one value when equal. */
function compactBand(lo: number, hi: number): string {
  if (Math.round(lo) === Math.round(hi)) return compact(lo);
  const unit = (n: number) =>
    Math.abs(n) >= 1_000_000_000
      ? "B"
      : Math.abs(n) >= 1_000_000
        ? "M"
        : Math.abs(n) >= 100_000
          ? "K"
          : "";
  // Share the unit suffix when both land in the same magnitude bucket.
  if (unit(lo) === unit(hi) && unit(lo) !== "") {
    return `${compact(lo).slice(0, -1)}–${compact(hi)}`;
  }
  return `${compact(lo)}–${compact(hi)}`;
}

/** Compact USD band, e.g. "$32–50M". */
function usdBand(lo: number, hi: number): string {
  if (Math.round(lo) === Math.round(hi)) return `$${compact(lo)}`;
  const unit = (n: number) =>
    Math.abs(n) >= 1_000_000_000
      ? "B"
      : Math.abs(n) >= 1_000_000
        ? "M"
        : Math.abs(n) >= 100_000
          ? "K"
          : "";
  if (unit(lo) === unit(hi) && unit(lo) !== "") {
    return `$${compact(lo).slice(0, -1)}–${compact(hi)}`;
  }
  return `$${compact(lo)}–$${compact(hi)}`;
}

/** Animated count-up to `value`; falls back to the final value if reduced-motion. */
function useCountUp(value: number, ms = 600): number {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const from = fromRef.current;
    const to = value;
    if (prefersReduced || from === to) {
      setDisplay(to);
      fromRef.current = to;
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      // easeOutCubic for a settle-y count-up.
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (to - from) * eased);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      fromRef.current = value;
    };
  }, [value, ms]);

  return display;
}

interface PresetDef {
  key: "contractor" | "megaproject" | "gulf_outdoor";
  label: string;
}

const PRESET_DEFS: PresetDef[] = [
  { key: "contractor", label: "Contractor" },
  { key: "megaproject", label: "Megaproject" },
  { key: "gulf_outdoor", label: "Regional" },
];

// Slider bounds (log-scaled): 1,000 -> 5,000,000.
const MIN_WF = 1_000;
const MAX_WF = 5_000_000;
const LOG_MIN = Math.log10(MIN_WF);
const LOG_MAX = Math.log10(MAX_WF);
const SLIDER_STEPS = 1000; // resolution of the log slider

function sliderToWorkforce(pos: number): number {
  const log = LOG_MIN + (pos / SLIDER_STEPS) * (LOG_MAX - LOG_MIN);
  return Math.round(Math.pow(10, log));
}

function workforceToSlider(wf: number): number {
  const clamped = Math.min(MAX_WF, Math.max(MIN_WF, wf));
  const log = Math.log10(clamped);
  return Math.round(((log - LOG_MIN) / (LOG_MAX - LOG_MIN)) * SLIDER_STEPS);
}

function HeroStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: "rose" | "indigo";
}) {
  const color = accent === "rose" ? "text-rose-600" : "text-indigo-600";
  return (
    <div className="rounded-2xl border border-white/60 bg-white/80 px-5 py-4 shadow-sm backdrop-blur">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-4xl font-extrabold tabular-nums sm:text-5xl ${color}`}>
        {value}
      </div>
    </div>
  );
}

function SupportStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div className="mt-0.5 text-base font-bold tabular-nums text-slate-900">
        {value}
      </div>
    </div>
  );
}

export function ScalePanel({ siteKey, fetchScale }: Props) {
  const [data, setData] = useState<ScaleResponse | null>(null);
  const [workforce, setWorkforce] = useState<number>(100_000);

  // Debounced, cancellation-guarded re-fetch on site or workforce change.
  const timer = useRef<number | null>(null);
  const reqId = useRef(0);
  useEffect(() => {
    if (!siteKey) return;
    if (timer.current) window.clearTimeout(timer.current);
    const id = ++reqId.current;
    timer.current = window.setTimeout(() => {
      fetchScale(siteKey, workforce)
        .then((res) => {
          if (id !== reqId.current) return; // stale — drop it
          setData(res);
        })
        .catch(() => {
          /* keep last good projection */
        });
    }, 300);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [siteKey, workforce, fetchScale]);

  const proj = data?.projection;
  const ctx = data?.context;
  const presets = data?.presets;

  // Count-up on the two emotional headline numbers.
  const livesDisplay = useCountUp(proj?.lives_saved ?? 0);
  const akiDisplay = useCountUp(proj?.aki_cases_averted ?? 0);

  return (
    <div className="space-y-5">
      {/* 1. The danger — context strip (grounded facts). */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-rose-200 bg-rose-50/70 px-4 py-3">
          <div className="text-2xl font-extrabold tabular-nums text-rose-700">
            {ctx ? compact(ctx.arab_states_migrant_workers) : "24M"}
          </div>
          <div className="mt-0.5 text-xs text-slate-600">
            migrant workers in the Arab states —{" "}
            <span className="font-semibold">
              {ctx ? `${ctx.migrant_share_pct}%` : "41.4%"}
            </span>
            , the highest share of any world region
          </div>
        </div>
        <div className="rounded-xl border border-rose-200 bg-rose-50/70 px-4 py-3">
          <div className="text-2xl font-extrabold tabular-nums text-rose-700">
            ~{ctx ? ctx.gulf_summer_peak_c : 50}&nbsp;°C
          </div>
          <div className="mt-0.5 text-xs text-slate-600">
            summer peaks on the sites these workers build
          </div>
        </div>
        <div className="rounded-xl border border-rose-200 bg-rose-50/70 px-4 py-3">
          <div className="text-2xl font-extrabold tabular-nums text-rose-700">
            ~{ctx ? compact(ctx.migrant_deaths_per_year) : "10,000"}/yr
          </div>
          <div className="mt-0.5 text-xs text-slate-600">
            migrant deaths a year — the heat-attributable share stays hidden
          </div>
        </div>
        <div className="rounded-xl border border-rose-200 bg-rose-50/70 px-4 py-3">
          <div className="text-2xl font-extrabold tabular-nums text-rose-700">
            1 of 19
          </div>
          <div className="mt-0.5 text-xs text-slate-600">
            migrant-worker heat studies worldwide came from the Gulf — a
            near-total evidence void
          </div>
        </div>
      </div>

      {ctx && (
        <p className="text-xs italic text-slate-500">{ctx.deaths_caveat}.</p>
      )}

      {/* 2. Workforce selector — presets + log slider. */}
      <div className="rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            role="group"
            aria-label="Workforce preset"
            className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-xs font-semibold"
          >
            {PRESET_DEFS.map((p) => {
              const target = presets?.[p.key];
              const active = target != null && Math.round(workforce) === target;
              return (
                <button
                  key={p.key}
                  type="button"
                  aria-pressed={active}
                  disabled={target == null}
                  onClick={() => target != null && setWorkforce(target)}
                  className={`rounded-md px-3 py-1.5 transition disabled:opacity-40 ${
                    active ? "bg-slate-900 text-white" : "text-slate-600"
                  }`}
                >
                  {p.label}
                  {target != null && (
                    <span className="ml-1 font-normal tabular-nums opacity-80">
                      {compact(target)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="text-right">
            <div className="text-[11px] uppercase tracking-wide text-slate-400">
              Workforce
            </div>
            <div className="text-2xl font-bold tabular-nums text-slate-900">
              {compact(workforce)}
              <span className="ml-1 text-sm font-medium text-slate-400">
                workers
              </span>
            </div>
          </div>
        </div>

        <div className="mt-3">
          <label
            htmlFor="scale-workforce"
            className="flex items-center justify-between text-xs font-medium text-slate-500"
          >
            <span>Projected workforce</span>
            <span className="tabular-nums text-slate-700">
              {Math.round(workforce).toLocaleString()} workers
            </span>
          </label>
          <input
            id="scale-workforce"
            type="range"
            min={0}
            max={SLIDER_STEPS}
            step={1}
            value={workforceToSlider(workforce)}
            onChange={(e) =>
              setWorkforce(sliderToWorkforce(Number(e.target.value)))
            }
            aria-valuetext={`${Math.round(workforce).toLocaleString()} workers`}
            className="mt-1.5 w-full accent-rose-600"
          />
          <div className="mt-1 flex justify-between text-[10px] tabular-nums text-slate-400">
            <span>1K</span>
            <span>10K</span>
            <span>100K</span>
            <span>1M</span>
            <span>5M</span>
          </div>
        </div>
      </div>

      {/* 3. Hero stats — the emotional headline. */}
      <div className="overflow-hidden rounded-2xl border border-rose-200 bg-gradient-to-br from-rose-50 via-white to-amber-50 p-5">
        {proj ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <HeroStat
                label="Lives saved / season"
                value={compact(livesDisplay)}
                accent="rose"
              />
              <HeroStat
                label="AKI cases averted / season"
                value={compact(akiDisplay)}
                accent="indigo"
              />
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <SupportStat
                label="Danger-hours protected"
                value={compact(proj.danger_hours_protected)}
              />
              <SupportStat
                label="Recovered work (worker-h)"
                value={compactBand(
                  proj.productivity_worker_hours_lo,
                  proj.productivity_worker_hours_hi,
                )}
              />
              <SupportStat
                label="Value created"
                value={usdBand(proj.value_usd_lo, proj.value_usd_hi)}
              />
              <SupportStat
                label="Program cost"
                value={`$${compact(proj.program_cost_usd)}`}
              />
            </div>
          </>
        ) : (
          <p className="py-8 text-center text-sm text-slate-400">
            Projecting impact to the workforce…
          </p>
        )}
      </div>

      {/* 4. Footnote — assumptions. */}
      <p className="text-xs text-slate-400">
        {proj?.assumptions.note ??
          "Illustrative; effect sizes transfer with uncertainty (see datasets.md)."}{" "}
        Illustrative and conservative — scaled from the per-crew season result.
      </p>
    </div>
  );
}
