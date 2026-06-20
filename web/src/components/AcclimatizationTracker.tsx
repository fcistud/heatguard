import type { Advisory } from "../types";

interface Props {
  worker: "veteran" | "newcomer";
  newcomerAdvisory?: Advisory;
}

const RAMP = [
  { day: 0, pct: 20 },
  { day: 1, pct: 40 },
  { day: 2, pct: 60 },
  { day: 3, pct: 80 },
  { day: 4, pct: 100 },
];

export function AcclimatizationTracker({ worker, newcomerAdvisory }: Props) {
  // Veteran is fully acclimatized (day 4+); newcomer is day 0.
  const activeDay = worker === "newcomer" ? 0 : 4;
  const capped = newcomerAdvisory?.cycle.capped_by_acclimatization;
  const acclimFrac = newcomerAdvisory?.acclim_fraction;

  return (
    <div>
      <p className="text-sm text-slate-600">
        NIOSH staged re-entry: new workers ramp exposure over their first days on
        site. HeatGuard caps the work cycle to this fraction.
      </p>

      <div className="mt-4 flex items-end justify-between gap-2">
        {RAMP.map((r) => {
          const active = r.day === activeDay;
          return (
            <div key={r.day} className="flex flex-1 flex-col items-center gap-1">
              <div
                className={`flex w-full flex-col justify-end overflow-hidden rounded-t-md ${
                  active ? "ring-2 ring-indigo-500 ring-offset-1" : ""
                }`}
                style={{ height: 96 }}
              >
                <div
                  className={`w-full transition-all ${
                    active ? "bg-indigo-500" : "bg-slate-300"
                  }`}
                  style={{ height: `${r.pct}%` }}
                />
              </div>
              <div className="text-[11px] font-semibold tabular-nums text-slate-700">
                {r.pct}%
              </div>
              <div className="text-[10px] text-slate-400">
                Day {r.day}
                {r.day === 4 ? "+" : ""}
              </div>
            </div>
          );
        })}
      </div>

      {worker === "newcomer" ? (
        <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm">
          <div className="font-semibold text-indigo-800">
            New worker (day 0) selected
          </div>
          <p className="mt-1 text-indigo-700">
            Exposure capped at{" "}
            <span className="font-semibold tabular-nums">
              {acclimFrac != null ? `${Math.round(acclimFrac * 100)}%` : "20%"}
            </span>{" "}
            of the acclimatized cycle.
            {capped
              ? " The current hour's cycle is limited by acclimatization."
              : " The current hour is not the binding constraint."}
          </p>
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          <span className="font-semibold text-emerald-800">Veteran selected</span>{" "}
          — fully acclimatized (day 4+), no exposure cap. Toggle to{" "}
          <span className="font-semibold">New worker</span> on the timeline to see
          the protection kick in.
        </div>
      )}
    </div>
  );
}
