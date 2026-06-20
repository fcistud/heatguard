import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { Backtest, ImpactReport } from "../types";
import { Stat } from "./ui/Stat";
import { api } from "../api";

interface Props {
  impact: ImpactReport;
}

export function ImpactPanel({ impact }: Props) {
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [btError, setBtError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .backtest()
      .then((b) => !cancelled && setBacktest(b))
      .catch(() => !cancelled && setBtError(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const prodLoPct = Math.round(impact.productivity_gain_lo * 100);
  const prodHiPct = Math.round(impact.productivity_gain_hi * 100);

  const barData = [
    {
      name: "Calendar ban",
      hours: impact.calendar_work_hours_per_worker,
      fill: "#94a3b8",
    },
    {
      name: "HeatGuard",
      hours: impact.heatguard_work_hours_per_worker,
      fill: "#16a34a",
    },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat
          label="Danger hours caught vs ban"
          value={impact.danger_hours_caught_vs_ban}
          accent="stop"
          hint="HeatGuard protected, the ban missed"
          big
        />
        <Stat
          label="Hours ban needlessly stopped"
          value={impact.ban_only_safe_hours}
          accent="rest"
          hint="Safe work the blunt ban blocked"
        />
        <Stat
          label="AKI cases averted vs ban"
          value={impact.aki_cases_averted_vs_ban.toFixed(1)}
          accent="indigo"
          hint={`of ${impact.aki_cases_baseline.toFixed(1)} baseline`}
        />
        <Stat
          label="Productivity gain"
          value={`${prodLoPct}–${prodHiPct}%`}
          accent="work"
          hint="recovered work capacity"
        />
        <Stat
          label="Cost / worker"
          value={`$${impact.cost_per_worker_usd.toFixed(0)}`}
          hint={`crew of ${impact.crew_size}`}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Work hours per worker / season
          </h3>
          <div className="mt-2 h-40">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={barData}
                layout="vertical"
                margin={{ top: 4, right: 36, left: 8, bottom: 4 }}
              >
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 12, fill: "#475569" }}
                  axisLine={false}
                  tickLine={false}
                  width={92}
                />
                <Bar dataKey="hours" radius={[4, 4, 4, 4]} barSize={28}>
                  {barData.map((d, i) => (
                    <Cell key={i} fill={d.fill} />
                  ))}
                  <LabelList
                    dataKey="hours"
                    position="right"
                    formatter={(v) => `${Number(v).toFixed(0)} h`}
                    style={{ fontSize: 12, fontWeight: 600, fill: "#334155" }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-400">
            HeatGuard keeps crews working through safe windows the calendar ban
            shuts down — and stops them when it's actually dangerous.
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Validated against Nicaragua
          </h3>
          {btError && (
            <p className="mt-2 text-sm text-slate-400">
              Backtest unavailable (API offline).
            </p>
          )}
          {!btError && !backtest && (
            <p className="mt-2 text-sm text-slate-400">Running backtest…</p>
          )}
          {backtest && (
            <div className="mt-2">
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold tabular-nums text-emerald-600">
                  {Math.round(backtest.reproduced_aki_reduction * 100)}%
                </span>
                <span className="text-sm text-slate-500">
                  AKI reduction reproduced
                </span>
                {backtest.passed ? (
                  <span className="ml-auto rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                    ✓ passed
                  </span>
                ) : (
                  <span className="ml-auto rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-semibold text-red-700">
                    ✗ failed
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm text-slate-600">
                The model reproduces the La Isla / Adelante intervention outcome
                (expected{" "}
                {Math.round(backtest.expected_aki_reduction * 100)}%) and a{" "}
                {Math.round(backtest.productivity_band[0] * 100)}–
                {Math.round(backtest.productivity_band[1] * 100)}% productivity
                band — the effect sizes that power these projections.
              </p>
            </div>
          )}
        </div>
      </div>

      <p className="text-xs text-slate-400">
        Season: {impact.season_days} days · {impact.worker_days.toLocaleString()}{" "}
        worker-days · ban coverage {impact.ban_coverage_pct}% of danger hours.
      </p>
    </div>
  );
}
