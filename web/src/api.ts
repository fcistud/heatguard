// Thin fetch layer for the HeatGuard FastAPI backend.
import type {
  Backtest,
  BusinessCase,
  DecideRequest,
  DecideResponse,
  DemoPayload,
  ImpactReport,
  SensitivityRow,
  SiteSummary,
  Timeline,
} from "./types";

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
  timeline: (siteKey: string, day: string) =>
    getJSON<Timeline>(`/timeline/${siteKey}/${day}`),
  impact: (siteKey: string, crew = 100) =>
    getJSON<ImpactReport>(`/impact/${siteKey}?crew=${crew}`),
  economics: (siteKey: string, crew = 100) =>
    getJSON<BusinessCase>(`/economics/${siteKey}?crew=${crew}`),
  sensitivity: (siteKey: string, crew = 100) =>
    getJSON<SensitivityRow[]>(`/sensitivity/${siteKey}?crew=${crew}`),
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
