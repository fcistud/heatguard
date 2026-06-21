import type { Compliance, Signal } from "../types";
import { SIGNAL_BG_SOFT, SIGNAL_SHORT } from "../lib/signals";
import { api } from "../api";

interface Props {
  compliance: Compliance;
  siteKey: string;
}

function fmtTime(iso: string): string {
  // payload timestamps are ISO; show HH:MM
  const t = iso.includes("T") ? iso.split("T")[1] : iso;
  return t.slice(0, 5);
}

export function ComplianceFeed({ compliance, siteKey }: Props) {
  const { summary, records } = compliance;
  const privacy = summary.privacy;

  return (
    <div>
      {/* Privacy by design — surfaces what the record does and does not capture. */}
      {(privacy || summary.purpose) && (
        <div className="mb-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <span aria-hidden="true">🔒</span>
            Privacy by design
          </div>
          {privacy?.does_not_record && (
            <p className="mt-1 text-slate-600">{privacy.does_not_record}</p>
          )}
          {summary.purpose && (
            <p className="mt-1 text-xs text-slate-500">{summary.purpose}</p>
          )}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {summary.verified ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              ✓ chain verified — tamper-evident
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
              ✗ chain broken
            </span>
          )}
          <span className="font-mono text-[11px] text-slate-400">
            head {summary.head_hash.slice(0, 12)}…
          </span>
        </div>
        <a
          href={api.complianceExportUrl(siteKey, "csv")}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
          download
        >
          ⬇ Download CSV
        </a>
      </div>

      <div className="scroll-thin max-h-72 overflow-y-auto rounded-xl border border-slate-200">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2 font-medium">Time</th>
              <th className="px-3 py-2 font-medium">Signal</th>
              <th className="px-3 py-2 text-right font-medium">WBGT</th>
              <th className="px-3 py-2 text-right font-medium">Work/Rest</th>
              <th className="px-3 py-2 text-center font-medium">Water</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {records.map((r) => {
              const p = r.payload;
              const sig = (p.signal ?? "WORK") as Signal;
              return (
                <tr key={r.seq} className="hover:bg-slate-50/60">
                  <td className="px-3 py-2 tabular-nums text-slate-700">
                    {fmtTime(r.timestamp)}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block rounded-md border px-2 py-0.5 text-[11px] font-semibold ${SIGNAL_BG_SOFT[sig]}`}
                    >
                      {SIGNAL_SHORT[sig]}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                    {p.wbgt_c != null ? `${p.wbgt_c}°` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                    {p.cycle
                      ? `${p.cycle.work_min_per_hour}/${p.cycle.rest_min_per_hour}`
                      : "—"}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {p.water_available ? (
                      <span className="text-emerald-600">✓</span>
                    ) : (
                      <span className="text-red-500">✗</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-400">
        {summary.records} hash-chained records · genesis → head. Each row's hash
        commits to the previous, so any edit breaks the chain.
      </p>
    </div>
  );
}
