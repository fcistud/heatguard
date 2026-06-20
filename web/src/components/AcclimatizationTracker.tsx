import type { Advisory } from "../types";

interface Props {
  worker: "veteran" | "newcomer";
  newcomerAdvisory?: Advisory;
  newcomerDays?: number;
  time?: string; // selected hour, e.g. "07:00"
  onSelectDay?: (day: number) => void;
  onSelectWorker?: (w: "veteran" | "newcomer") => void;
}

const RAMP = [
  { day: 0, pct: 20 },
  { day: 1, pct: 40 },
  { day: 2, pct: 60 },
  { day: 3, pct: 80 },
  { day: 4, pct: 100 },
];

export function AcclimatizationTracker({
  worker,
  newcomerAdvisory,
  newcomerDays = 0,
  time,
  onSelectDay,
  onSelectWorker,
}: Props) {
  // Veteran is fully acclimatized (day 4+); newcomer is at the chosen tenure.
  const activeDay = worker === "newcomer" ? Math.min(newcomerDays, 4) : 4;
  const capped = newcomerAdvisory?.cycle.capped_by_acclimatization;
  const acclimFrac = newcomerAdvisory?.acclim_fraction;
  const capPct = acclimFrac != null ? Math.round(acclimFrac * 100) : RAMP[activeDay].pct;
  const fullyAcclimatized = capPct >= 100; // day 4+ — the ramp is done, no cap can bind
  const interactive = !!onSelectDay;

  const pick = (day: number) => {
    if (!interactive) return;
    onSelectWorker?.("newcomer"); // exploring the ramp implies the new-worker view
    onSelectDay?.(day);
  };

  return (
    <div>
      <p className="text-sm text-slate-600">
        NIOSH staged re-entry: a new worker ramps exposure over their first days on site, so
        HeatGuard caps the work cycle to a fraction of normal.{" "}
        {interactive && (
          <span className="font-medium text-indigo-700">Click a day to see the cap change.</span>
        )}
      </p>

      <div className="mt-4 flex items-end justify-between gap-2">
        {RAMP.map((r) => {
          const active = worker === "newcomer" && r.day === activeDay;
          const reached = worker === "newcomer" && r.day <= activeDay; // progress fill
          const allDone = worker === "veteran"; // veteran = fully ramped
          const barColor = active
            ? "bg-indigo-600"
            : reached || allDone
              ? "bg-indigo-300"
              : "bg-slate-200";
          const Tag: any = interactive ? "button" : "div";
          return (
            <Tag
              key={r.day}
              {...(interactive
                ? {
                    type: "button",
                    onClick: () => pick(r.day),
                    "aria-label": `New worker, day ${r.day}${r.day === 4 ? "+" : ""}: ${r.pct}% of normal exposure`,
                    "aria-pressed": active,
                  }
                : {})}
              className={`flex flex-1 flex-col items-center gap-1 ${
                interactive ? "cursor-pointer rounded-md p-1 transition hover:bg-slate-50" : ""
              }`}
            >
              <div
                className={`flex w-full flex-col justify-end overflow-hidden rounded-t-md ${
                  active ? "ring-2 ring-indigo-500 ring-offset-1" : ""
                }`}
                style={{ height: 96 }}
              >
                <div
                  className={`w-full transition-all ${barColor}`}
                  style={{ height: `${r.pct}%` }}
                />
              </div>
              <div
                className={`text-[11px] font-semibold tabular-nums ${
                  active ? "text-indigo-700" : "text-slate-600"
                }`}
              >
                {r.pct}%
              </div>
              <div className="text-[10px] text-slate-400">
                Day {r.day}
                {r.day === 4 ? "+" : ""}
              </div>
            </Tag>
          );
        })}
      </div>

      {worker === "newcomer" ? (
        <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm">
          {fullyAcclimatized ? (
            <>
              <div className="font-semibold text-indigo-800">
                New worker · day {newcomerDays} — fully acclimatized, no exposure cap
              </div>
              <p className="mt-1 text-indigo-700">
                After ~4 days of graded exposure the ramp is complete — the schedule is now driven
                entirely by the heat, exactly like a veteran. (Pick day 0–3 to see the cap bite.)
              </p>
            </>
          ) : (
            <>
              <div className="font-semibold text-indigo-800">
                New worker · day {newcomerDays} — exposure capped at{" "}
                <span className="tabular-nums">{capPct}%</span> of normal
              </div>
              <p className="mt-1 text-indigo-700">
                {time ? `At ${time}, ` : ""}
                {capped
                  ? `this ${capPct}% acclimatization cap is the binding limit — it holds work below what the heat alone would allow.`
                  : "the heat is the stricter limit here, so the cap isn't the binding one. Pick a cooler morning hour on the timeline to see the cap take over."}
              </p>
            </>
          )}
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          <span className="font-semibold text-emerald-800">Veteran — fully acclimatized (day 4+)</span>{" "}
          — no exposure cap.{" "}
          {interactive ? (
            <span>Click a day above to see how a new arrival is protected.</span>
          ) : (
            <span>
              Toggle to <span className="font-semibold">New worker</span> on the timeline to see the
              protection kick in.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
