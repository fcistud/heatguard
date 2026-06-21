import type { ReactNode } from "react";

interface StatProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: "default" | "work" | "rest" | "drink" | "stop" | "indigo";
  big?: boolean;
}

const ACCENT: Record<NonNullable<StatProps["accent"]>, string> = {
  default: "text-slate-900 dark:text-slate-100",
  work: "text-emerald-600 dark:text-emerald-400",
  rest: "text-amber-600 dark:text-amber-400",
  drink: "text-sky-600 dark:text-sky-400",
  stop: "text-red-600 dark:text-red-400",
  indigo: "text-indigo-600 dark:text-indigo-400",
};

export function Stat({ label, value, hint, accent = "default", big }: StatProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3 dark:border-slate-700 dark:bg-slate-800">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div
        className={`mt-1 font-bold tabular-nums ${ACCENT[accent]} ${
          big ? "text-3xl" : "text-2xl"
        }`}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</div>}
    </div>
  );
}
