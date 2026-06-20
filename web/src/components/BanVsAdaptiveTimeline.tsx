import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Timeline, TimelineRow } from "../types";
import { SIGNAL_COLOR, SIGNAL_SHORT } from "../lib/signals";

type WorkerKey = "veteran" | "newcomer";

interface Props {
  timeline: Timeline;
  worker: WorkerKey;
  selectedHour: number | null;
  onSelectHour: (hour: number) => void;
  availableDays: string[];
  focusDay: string;
  onSelectDay: (day: string) => void;
  loadingDay: boolean;
}

function Cell({
  children,
  color,
  selected,
  outline,
  onClick,
  title,
}: {
  children: React.ReactNode;
  color: string;
  selected: boolean;
  outline?: boolean;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`relative flex h-12 flex-1 items-center justify-center rounded-md text-[11px] font-semibold text-white transition ${
        selected ? "ring-2 ring-offset-2 ring-slate-900" : ""
      }`}
      style={{
        backgroundColor: color,
        outline: outline ? "2px solid #dc2626" : undefined,
        outlineOffset: outline ? "-2px" : undefined,
      }}
    >
      {children}
    </button>
  );
}

export function BanVsAdaptiveTimeline({
  timeline,
  worker,
  selectedHour,
  onSelectHour,
  availableDays,
  focusDay,
  onSelectDay,
  loadingDay,
}: Props) {
  const rows = timeline.rows;
  const chartData = rows.map((r) => ({
    time: r.time,
    wbgt: r.wbgt_c,
    hour: r.hour,
  }));

  const adv = (r: TimelineRow) => (worker === "veteran" ? r.veteran : r.newcomer);

  return (
    <div>
      {/* Day scrubber */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-slate-500">Day</label>
          <select
            value={focusDay}
            onChange={(e) => onSelectDay(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm font-medium text-slate-700 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
          >
            {availableDays.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          {availableDays.length > 1 && (
            <input
              type="range"
              min={0}
              max={availableDays.length - 1}
              value={Math.max(0, availableDays.indexOf(focusDay))}
              onChange={(e) => onSelectDay(availableDays[Number(e.target.value)])}
              className="w-40 accent-indigo-500"
            />
          )}
          {loadingDay && (
            <span className="text-xs text-slate-400">loading…</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="font-medium text-slate-500">
            Gap hours (missed by ban):
          </span>
          <span className="rounded-full bg-red-50 px-2.5 py-0.5 font-bold text-red-600">
            {timeline.gap_hours}
          </span>
        </div>
      </div>

      {/* WBGT line over the top */}
      <div className="h-28 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
          >
            <defs>
              <linearGradient id="wbgtFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#dc2626" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              interval={1}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
              width={36}
              domain={["dataMin - 2", "dataMax + 2"]}
              unit="°"
            />
            <Tooltip
              formatter={(v) => [`${v} °C`, "WBGT"]}
              contentStyle={{
                borderRadius: 8,
                border: "1px solid #e2e8f0",
                fontSize: 12,
              }}
            />
            <Area
              type="monotone"
              dataKey="wbgt"
              stroke="#dc2626"
              strokeWidth={2}
              fill="url(#wbgtFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Two lanes */}
      <div className="mt-2 space-y-2">
        <div className="flex items-center gap-3">
          <div className="w-32 shrink-0 text-right text-xs font-semibold text-slate-500">
            Calendar ban
          </div>
          <div className="flex flex-1 gap-1">
            {rows.map((r) => (
              <Cell
                key={r.hour}
                color={r.banned ? "#334155" : "#cbd5e1"}
                selected={selectedHour === r.hour}
                onClick={() => onSelectHour(r.hour)}
                title={`${r.time} — ${r.banned ? "work banned" : "work permitted"}`}
              >
                {r.banned ? "BAN" : ""}
              </Cell>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-32 shrink-0 text-right text-xs font-semibold text-slate-500">
            HeatGuard (adaptive)
          </div>
          <div className="flex flex-1 gap-1">
            {rows.map((r) => {
              const a = adv(r);
              return (
                <Cell
                  key={r.hour}
                  color={SIGNAL_COLOR[a.signal]}
                  selected={selectedHour === r.hour}
                  outline={r.gap}
                  onClick={() => onSelectHour(r.hour)}
                  title={`${r.time} — ${a.signal}${r.gap ? " (MISSED by ban)" : ""}`}
                >
                  {r.gap ? "!" : SIGNAL_SHORT[a.signal][0]}
                </Cell>
              );
            })}
          </div>
        </div>

        {/* hour axis */}
        <div className="flex items-center gap-3">
          <div className="w-32 shrink-0" />
          <div className="flex flex-1 gap-1">
            {rows.map((r) => (
              <div
                key={r.hour}
                className="flex-1 text-center text-[10px] tabular-nums text-slate-400"
              >
                {r.time.slice(0, 2)}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* legend */}
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-600">
        {(["WORK", "REST_IN_SHADE", "DRINK_NOW", "STOP"] as const).map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span
              className="h-3 w-3 rounded-sm"
              style={{ backgroundColor: SIGNAL_COLOR[s] }}
            />
            {SIGNAL_SHORT[s]}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border-2 border-red-600 bg-transparent" />
          MISSED by ban (gap)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-slate-700" />
          Ban active
        </span>
      </div>
    </div>
  );
}
