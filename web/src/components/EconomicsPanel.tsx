import { useEffect, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BusinessCase, SensitivityRow } from "../types";

interface Props {
  /** Initial business case from the demo payload. */
  economics: BusinessCase;
  /** Initial sensitivity rows from the demo payload. */
  sensitivity?: SensitivityRow[];
  /** For re-fetching when the crew control changes. */
  siteKey: string;
  crew: number;
  /** Same fetch helpers App already owns, injected to mirror ImpactPanel's pattern. */
  fetchEconomics: (siteKey: string, crew: number) => Promise<BusinessCase>;
  fetchSensitivity: (siteKey: string, crew: number) => Promise<SensitivityRow[]>;
}

const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;

// Signal-neutral palette for the four headline benefit components.
const BENEFIT_SEGMENTS = [
  { key: "productivity", label: "Productivity", color: "#16a34a" },
  { key: "recovered", label: "Recovered safe work", color: "#0ea5e9" },
  { key: "aki", label: "AKI averted", color: "#6366f1" },
  { key: "fines", label: "Fines avoided", color: "#f59e0b" },
] as const;

export function EconomicsPanel({
  economics,
  sensitivity,
  siteKey,
  crew,
  fetchEconomics,
  fetchSensitivity,
}: Props) {
  const [bc, setBc] = useState<BusinessCase>(economics);
  const [rows, setRows] = useState<SensitivityRow[] | undefined>(sensitivity);

  // Adopt fresh props when the site changes (App re-fetches the whole demo).
  useEffect(() => {
    setBc(economics);
    setRows(sensitivity);
  }, [economics, sensitivity]);

  // Re-fetch (debounced) when crew changes — mirrors ImpactPanel/App's crew effect.
  const crewTimer = useRef<number | null>(null);
  useEffect(() => {
    if (!siteKey) return;
    if (crewTimer.current) window.clearTimeout(crewTimer.current);
    crewTimer.current = window.setTimeout(() => {
      fetchEconomics(siteKey, crew)
        .then(setBc)
        .catch(() => {
          /* keep last good economics */
        });
      fetchSensitivity(siteKey, crew)
        .then(setRows)
        .catch(() => {
          /* keep last good sensitivity */
        });
    }, 350);
    return () => {
      if (crewTimer.current) window.clearTimeout(crewTimer.current);
    };
  }, [crew, siteKey, fetchEconomics, fetchSensitivity]);

  // Cost vs. benefit bar geometry — scale both bars to the larger benefit (hi).
  const segValues: Record<(typeof BENEFIT_SEGMENTS)[number]["key"], number> = {
    productivity: bc.productivity_value_lo,
    recovered: bc.recovered_safe_work_value,
    aki: bc.aki_value,
    fines: bc.fines_avoided_value,
  };
  const benefitTotal =
    segValues.productivity +
    segValues.recovered +
    segValues.aki +
    segValues.fines;
  const scaleMax = Math.max(benefitTotal, bc.program_cost_usd) || 1;

  const note = bc.assumptions?.note;

  // Sensitivity chart data: x = baseline AKI incidence (%), y = cases averted vs ban.
  const sensData = (rows ?? []).map((r) => ({
    incidence: r.baseline_aki_incidence,
    incidencePct: Math.round(r.baseline_aki_incidence * 1000) / 10,
    averted: r.aki_cases_averted_vs_ban,
  }));
  const defaultPoint = sensData.find((d) => Math.abs(d.incidence - 0.1) < 1e-6);

  return (
    <div className="space-y-5">
      {/* 1. ROI hero — the money slide. */}
      <div className="overflow-hidden rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 via-white to-sky-50 p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
              Headline return on investment
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-5xl font-extrabold tabular-nums text-emerald-600">
                {bc.roi_multiple_lo}×–{bc.roi_multiple_hi}×
              </span>
              <span className="text-sm font-medium text-slate-500">ROI</span>
            </div>
            <p className="mt-1.5 text-sm text-slate-600">
              Productivity-positive + a compliance shield — not just a safety cost.
            </p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white px-4 py-2.5 text-center shadow-sm">
            <div className="text-[11px] uppercase tracking-wide text-slate-400">
              Payback
            </div>
            <div className="text-3xl font-bold tabular-nums text-slate-900">
              ~{Math.round(bc.payback_days)}d
            </div>
            <div className="text-[11px] text-slate-400">
              ~{Math.round(bc.payback_days)}-day payback
            </div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-slate-200 bg-white/70 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">
              Headline benefit
            </div>
            <div className="text-base font-bold tabular-nums text-slate-900">
              {usd(bc.headline_benefit_lo)}–{usd(bc.headline_benefit_hi)}
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white/70 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">
              Program cost
            </div>
            <div className="text-base font-bold tabular-nums text-slate-900">
              {usd(bc.program_cost_usd)}
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white/70 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">
              Net benefit
            </div>
            <div className="text-base font-bold tabular-nums text-emerald-600">
              {usd(bc.net_benefit_lo)}–{usd(bc.net_benefit_hi)}
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white/70 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">
              Crew · season
            </div>
            <div className="text-base font-bold tabular-nums text-slate-900">
              {bc.crew_size.toLocaleString()} · {bc.season_days}d
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* 2. Cost vs. benefit comparison. */}
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Cost vs. benefit (crew · season)
          </h3>
          <div className="mt-3 space-y-3">
            {/* Program cost bar */}
            <div>
              <div className="mb-1 flex items-baseline justify-between text-xs">
                <span className="font-medium text-slate-600">Program cost</span>
                <span className="font-semibold tabular-nums text-slate-700">
                  {usd(bc.program_cost_usd)}
                </span>
              </div>
              <div className="h-7 w-full overflow-hidden rounded-md bg-slate-100">
                <div
                  className="h-full rounded-md bg-slate-400"
                  style={{
                    width: `${Math.max(
                      2,
                      (bc.program_cost_usd / scaleMax) * 100,
                    )}%`,
                  }}
                />
              </div>
            </div>

            {/* Stacked benefit bar */}
            <div>
              <div className="mb-1 flex items-baseline justify-between text-xs">
                <span className="font-medium text-slate-600">
                  Headline benefit
                </span>
                <span className="font-semibold tabular-nums text-emerald-600">
                  {usd(benefitTotal)}
                </span>
              </div>
              <div className="flex h-7 w-full overflow-hidden rounded-md bg-slate-100">
                {BENEFIT_SEGMENTS.map((seg) => {
                  const v = segValues[seg.key];
                  if (v <= 0) return null;
                  return (
                    <div
                      key={seg.key}
                      title={`${seg.label}: ${usd(v)}`}
                      className="h-full"
                      style={{
                        width: `${(v / scaleMax) * 100}%`,
                        backgroundColor: seg.color,
                      }}
                    />
                  );
                })}
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[11px] text-slate-500">
            {BENEFIT_SEGMENTS.map((seg) => (
              <span key={seg.key} className="inline-flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ backgroundColor: seg.color }}
                />
                {seg.label} · {usd(segValues[seg.key])}
              </span>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-slate-400">
            Productivity shown at the conservative low value (
            {usd(bc.productivity_value_lo)}–{usd(bc.productivity_value_hi)} band).
          </p>

          {/* 3. Additional upside (excluded from headline). */}
          <div className="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50/60 px-3 py-2.5">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Additional upside
            </div>
            <div className="mt-1 space-y-0.5 text-sm text-slate-500">
              <div>
                + {usd(bc.death_averted_value)} death-risk averted
              </div>
              <div>+ {usd(bc.turnover_value)} turnover</div>
            </div>
            <div className="mt-1 text-[11px] italic text-slate-400">
              (not counted in headline ROI)
            </div>
          </div>
        </div>

        {/* 4. AKI sensitivity chart. */}
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            AKI cases averted vs ban — sensitivity
          </h3>
          {sensData.length === 0 ? (
            <p className="mt-2 text-sm text-slate-400">
              Sensitivity data unavailable.
            </p>
          ) : (
            <div className="mt-2 h-44">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={sensData}
                  margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
                >
                  <defs>
                    <linearGradient id="akiFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#6366f1" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#f1f5f9" vertical={false} />
                  <XAxis
                    dataKey="incidencePct"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v) => `${v}%`}
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    axisLine={false}
                    tickLine={false}
                    width={32}
                  />
                  <Tooltip
                    formatter={(v) => [
                      `${Number(v).toFixed(1)} cases`,
                      "Averted vs ban",
                    ]}
                    labelFormatter={(l) => `Baseline AKI ${l}%`}
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 8,
                      border: "1px solid #e2e8f0",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="averted"
                    stroke="#6366f1"
                    strokeWidth={2}
                    fill="url(#akiFill)"
                  />
                  {defaultPoint && (
                    <ReferenceDot
                      x={defaultPoint.incidencePct}
                      y={defaultPoint.averted}
                      r={5}
                      fill="#6366f1"
                      stroke="#fff"
                      strokeWidth={2}
                      label={{
                        value: "default 10%",
                        position: "top",
                        fontSize: 10,
                        fill: "#6366f1",
                      }}
                    />
                  )}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-2 text-[11px] text-slate-400">
            The baseline AKI incidence is the biggest assumption — shown as a
            range, not a point.
          </p>
        </div>
      </div>

      <p className="text-xs text-slate-400">
        {note ?? "Illustrative, conservative, tunable assumptions (data/economics.json)."}
      </p>
    </div>
  );
}
