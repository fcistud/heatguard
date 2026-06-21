import { Brand } from "./ui/Brand";
import type { Theme } from "../lib/theme";

export type ViewMode = "simple" | "full";

interface Props {
  demos: string[];
  selected: string;
  onSelect: (key: string) => void;
  crew: number;
  onCrew: (n: number) => void;
  theme: Theme;
  onToggleTheme: () => void;
  view: ViewMode;
  onView: (v: ViewMode) => void;
}

function pretty(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

export function TopBar({
  demos,
  selected,
  onSelect,
  crew,
  onCrew,
  theme,
  onToggleTheme,
  view,
  onView,
}: Props) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur dark:border-slate-800 dark:bg-slate-900/85">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-5 py-3">
        <Brand subtitle="Adaptive heat-safety scheduling for outdoor crews" />

        <div className="ml-auto flex flex-wrap items-center gap-4">
          {/* Simple ⟷ Full view toggle */}
          <div
            role="group"
            aria-label="View mode"
            className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-xs font-semibold dark:border-slate-700 dark:bg-slate-800"
          >
            <button
              type="button"
              aria-pressed={view === "simple"}
              onClick={() => onView("simple")}
              className={`rounded-md px-3 py-1 transition ${
                view === "simple"
                  ? "bg-heat-orange text-white"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              Simple
            </button>
            <button
              type="button"
              aria-pressed={view === "full"}
              onClick={() => onView("full")}
              className={`rounded-md px-3 py-1 transition ${
                view === "full"
                  ? "bg-slate-900 text-white dark:bg-slate-200 dark:text-slate-900"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              Full
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
              Site
            </span>
            <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-sm font-semibold dark:border-slate-700 dark:bg-slate-800">
              {demos.map((d) => (
                <button
                  key={d}
                  onClick={() => onSelect(d)}
                  className={`rounded-md px-3 py-1 transition ${
                    selected === d
                      ? "bg-slate-900 text-white dark:bg-slate-200 dark:text-slate-900"
                      : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
                  }`}
                >
                  {pretty(d)}
                </button>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
              Crew size
            </span>
            <input
              type="number"
              min={1}
              max={100000}
              value={crew}
              onChange={(e) => onCrew(Math.max(1, Number(e.target.value) || 1))}
              className="w-24 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm font-medium text-slate-700 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            />
          </label>

          {/* Theme toggle */}
          <button
            type="button"
            onClick={onToggleTheme}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            className="grid h-9 w-9 place-items-center rounded-lg border border-slate-300 bg-white text-base text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
      </div>
    </header>
  );
}
