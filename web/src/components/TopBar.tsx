interface Props {
  demos: string[];
  selected: string;
  onSelect: (key: string) => void;
  crew: number;
  onCrew: (n: number) => void;
}

function pretty(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

export function TopBar({ demos, selected, onSelect, crew, onCrew }: Props) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-5 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-red-500 text-lg shadow-sm">
            <span role="img" aria-label="sun">
              ☀️
            </span>
          </div>
          <div>
            <div className="text-lg font-extrabold tracking-tight text-slate-900">
              Heat<span className="text-red-500">Guard</span>
            </div>
            <div className="-mt-0.5 text-[11px] text-slate-400">
              Adaptive heat-safety scheduling for outdoor crews
            </div>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500">Site</span>
            <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-sm font-semibold">
              {demos.map((d) => (
                <button
                  key={d}
                  onClick={() => onSelect(d)}
                  className={`rounded-md px-3 py-1 transition ${
                    selected === d
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {pretty(d)}
                </button>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500">Crew size</span>
            <input
              type="number"
              min={1}
              max={100000}
              value={crew}
              onChange={(e) => onCrew(Math.max(1, Number(e.target.value) || 1))}
              className="w-24 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm font-medium text-slate-700 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
            />
          </label>
        </div>
      </div>
    </header>
  );
}
