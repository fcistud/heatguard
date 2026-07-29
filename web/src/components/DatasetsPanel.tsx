import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { DatasetInventory } from "../types";
import { DEMO_SITE_KEYS, prettySiteKey } from "../lib/siteLabels";
import { Stat } from "./ui/Stat";

function CacheBadge({ cached }: { cached: boolean }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        cached ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"
      }`}
    >
      {cached ? "Cached" : "Missing"}
    </span>
  );
}

function MonoPath({ path }: { path: string }) {
  return (
    <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
      {path}
    </code>
  );
}

export function DatasetsPanel() {
  const [data, setData] = useState<DatasetInventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .datasets()
      .then(setData)
      .catch((e) => {
        setData(null);
        setError(e instanceof ApiError ? e.message : "Could not load dataset manifest");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <p className="py-8 text-center text-sm text-slate-400">Loading data manifest…</p>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <p>{error ?? "Manifest unavailable"}</p>
        <button
          type="button"
          onClick={load}
          className="mt-3 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
        >
          Retry
        </button>
      </div>
    );
  }

  const { weather, policy, epidemiology, intervention, economics } = data;
  const archivesReady = weather.archive_cached === weather.archive_total;
  const forecastsReady = weather.forecast_cached === weather.forecast_total;

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        <p>
          Manifest v{data.manifest_version} · {data.sites_registered} Gulf sites registered ·
          weather from{" "}
          <a
            href={weather.source_url}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-indigo-600 hover:text-indigo-800"
          >
            Open-Meteo
          </a>{" "}
          (ERA5-class archive + forecast API). Caches are committed under{" "}
          <MonoPath path="data/cache/" /> so demos run offline.
        </p>
        <p className="mt-2 text-xs text-slate-500">
          Refresh live caches:{" "}
          <code className="rounded bg-white px-1">heatguard fetch-datasets --refresh</code>
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label="Archive caches"
          value={`${weather.archive_cached}/${weather.archive_total}`}
          accent={archivesReady ? "work" : "rest"}
          hint={archivesReady ? "All season archives present" : "Some archives missing"}
        />
        <Stat
          label="Forecast caches"
          value={`${weather.forecast_cached}/${weather.forecast_total}`}
          accent={forecastsReady ? "work" : "rest"}
          hint="Near-live shift planning"
        />
        <Stat
          label="Policy corpus"
          value={policy.file_count}
          accent="indigo"
          hint="GCC bans + ILO WRS excerpts"
        />
        <Stat
          label="Epidemiology sources"
          value={epidemiology.source_count}
          accent="default"
          hint="Published aggregate stats"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Weather archives
          </h3>
          <div className="mt-2 overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full min-w-[28rem] border-collapse text-left text-sm">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2 font-medium">Site</th>
                  <th className="px-3 py-2 font-medium">Season</th>
                  <th className="px-3 py-2 font-medium">Cache</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {weather.archive.map((row) => (
                  <tr key={`${row.site_key}-${row.start}`} className="text-slate-700">
                    <td className="px-3 py-2">
                      <div className="font-medium">{prettySiteKey(row.site_key)}</div>
                      {row.note && (
                        <div className="mt-0.5 text-xs text-slate-400">{row.note}</div>
                      )}
                      {DEMO_SITE_KEYS.has(row.site_key) && (
                        <span className="mt-1 inline-block rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-indigo-700">
                          Demo
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 tabular-nums text-xs text-slate-600">
                      {row.start}
                      <br />
                      → {row.end}
                    </td>
                    <td className="px-3 py-2">
                      <CacheBadge cached={row.cached} />
                      <div className="mt-1">
                        <MonoPath path={row.cache_file.replace(/^data\//, "")} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Near-live forecasts
            </h3>
            <div className="mt-2 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full border-collapse text-left text-sm">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">Site</th>
                    <th className="px-3 py-2 font-medium">Window</th>
                    <th className="px-3 py-2 font-medium">Cache</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {weather.forecast.map((row) => (
                    <tr key={row.site_key} className="text-slate-700">
                      <td className="px-3 py-2 font-medium">{prettySiteKey(row.site_key)}</td>
                      <td className="px-3 py-2 text-xs text-slate-600">
                        {row.past_days}d past + {row.forecast_days}d ahead
                      </td>
                      <td className="px-3 py-2">
                        <CacheBadge cached={row.cached} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Policy & evidence files
            </h3>
            <ul className="mt-2 space-y-2 rounded-xl border border-slate-200 divide-y divide-slate-100">
              {policy.files.map((f) => (
                <li key={f.id} className="px-3 py-2 text-sm">
                  <div className="font-medium text-slate-800">{f.title}</div>
                  <div className="mt-0.5 text-xs text-slate-500">
                    <MonoPath path={f.path} />
                  </div>
                </li>
              ))}
              <li className="px-3 py-2 text-sm text-slate-600">
                <div className="font-medium text-slate-800">Gulf epidemiology aggregates</div>
                <div className="mt-0.5 text-xs text-slate-500">
                  <MonoPath path={epidemiology.path.replace(/^data\//, "")} /> ·{" "}
                  {epidemiology.source_count} sources
                </div>
              </li>
              <li className="px-3 py-2 text-sm text-slate-600">
                <div className="font-medium text-slate-800">Nicaragua WRS intervention (backtest)</div>
                <div className="mt-0.5 text-xs text-slate-500">
                  <MonoPath path={intervention.path.replace(/^data\//, "")} />
                </div>
              </li>
              <li className="px-3 py-2 text-sm text-slate-600">
                <div className="font-medium text-slate-800">ROI economics assumptions</div>
                <div className="mt-0.5 text-xs text-slate-500">
                  <MonoPath path={economics.path.replace(/^data\//, "")} /> · {economics.type}
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
