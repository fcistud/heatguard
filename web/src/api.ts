// Thin fetch layer for the HeatGuard FastAPI backend.
import type {
  Backtest,
  BusinessCase,
  DecideRequest,
  DecideResponse,
  DemoPayload,
  HourAdvisory,
  ImpactReport,
  ScaleResponse,
  SensitivityRow,
  SiteSummary,
  Timeline,
} from "./types";

type WorkerKey = "veteran" | "newcomer";

/** Build a query string from defined params only (omits undefined/null). */
function qs(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    // Network failure usually means the API isn't running.
    throw new ApiError(
      "Could not reach the HeatGuard API. Is it running?",
      0,
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore parse errors */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  sites: () => getJSON<SiteSummary[]>("/sites"),
  demos: () => getJSON<string[]>("/demos"),
  demo: (siteKey: string, crew = 100) =>
    getJSON<DemoPayload>(`/demo/${siteKey}?crew=${crew}`),
  timeline: (
    siteKey: string,
    day: string,
    opts: { intensity?: string; newcomerDays?: number } = {},
  ) =>
    getJSON<Timeline>(
      `/timeline/${siteKey}/${day}${qs({
        intensity: opts.intensity,
        newcomer_days: opts.newcomerDays,
      })}`,
    ),
  hour: (
    siteKey: string,
    day: string,
    hour: number,
    opts: {
      worker: WorkerKey;
      measuredWbgt?: number;
      intensity?: string;
      newcomerDays?: number;
    },
  ) =>
    getJSON<HourAdvisory>(
      `/hour/${siteKey}/${day}/${hour}${qs({
        worker: opts.worker,
        measured_wbgt: opts.measuredWbgt,
        intensity: opts.intensity,
        newcomer_days: opts.newcomerDays,
      })}`,
    ),
  impact: (siteKey: string, crew = 100) =>
    getJSON<ImpactReport>(`/impact/${siteKey}?crew=${crew}`),
  economics: (siteKey: string, crew = 100) =>
    getJSON<BusinessCase>(`/economics/${siteKey}?crew=${crew}`),
  sensitivity: (siteKey: string, crew = 100) =>
    getJSON<SensitivityRow[]>(`/sensitivity/${siteKey}?crew=${crew}`),
  scale: (siteKey: string, workforce = 5000) =>
    getJSON<ScaleResponse>(`/scale/${siteKey}?workforce=${workforce}`),
  backtest: () => getJSON<Backtest>("/backtest"),
  decide: (req: DecideRequest) =>
    getJSON<DecideResponse>("/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  complianceExportUrl: (siteKey: string, fmt: "csv" | "jsonl" = "csv") =>
    `${API_BASE}/compliance/${siteKey}/export?fmt=${fmt}`,
};
