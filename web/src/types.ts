// TypeScript types mirroring the HeatGuard FastAPI JSON shapes.

export type Signal = "WORK" | "REST_IN_SHADE" | "DRINK_NOW" | "STOP";
export type WbgtSource = "liljegren" | "fallback" | "measured";
export type Intensity = "light" | "moderate" | "heavy" | "very_heavy";

export interface SiteSummary {
  key: string;
  name: string;
  lat: number;
  lon: number;
  country: string;
  ban: string;
  is_demo: boolean;
}

export interface WorkRestCycle {
  work_fraction: number;
  work_min_per_hour: number;
  rest_min_per_hour: number;
  threshold_wbgt_c: number | null;
  table: "TLV" | "AL";
  capped_by_acclimatization: boolean;
}

export interface HydrationTarget {
  sweat_loss_g_per_h: number;
  water_ml_per_h: number;
  cups_250ml_per_h: number;
  max_exposure_min: number;
  core_temp_c: number;
  phs_valid: boolean;
}

export interface Advisory {
  timestamp: string;
  site_name: string;
  worker_id: string;
  wbgt_c: number;
  wbgt_source: WbgtSource;
  signal: Signal;
  cycle: WorkRestCycle;
  hydration: HydrationTarget;
  acclim_fraction: number;
  rationale: string;
  risk_score: number; // 0..1
}

export interface TimelineRow {
  hour: number;
  time: string; // "09:00"
  tdb_c: number;
  rh_pct: number;
  wbgt_c: number;
  wbgt_source: WbgtSource;
  veteran: Advisory;
  newcomer: Advisory;
  banned: boolean;
  gap: boolean;
}

export interface Timeline {
  site: string;
  country: string;
  date: string;
  gap_hours: number;
  rows: TimelineRow[];
}

export interface ComplianceRecord {
  seq: number;
  timestamp: string;
  kind: string;
  payload: {
    signal?: Signal;
    wbgt_c?: number;
    wbgt_source?: WbgtSource;
    cycle?: WorkRestCycle;
    hydration?: HydrationTarget;
    water_available?: boolean;
    [k: string]: unknown;
  };
  prev_hash: string;
  record_hash: string;
}

export interface ComplianceSummary {
  site: string;
  records: number;
  head_hash: string;
  verified: boolean;
  signal_counts: Partial<Record<Signal, number>>;
}

export interface Compliance {
  summary: ComplianceSummary;
  records: ComplianceRecord[];
  csv: string;
}

export interface ImpactReport {
  crew_size: number;
  season_days: number;
  worker_days: number;
  total_hours: number;
  total_danger_hours: number;
  danger_hours_in_ban: number;
  danger_hours_caught_vs_ban: number; // headline
  ban_coverage_pct: number;
  ban_only_safe_hours: number;
  aki_cases_baseline: number;
  aki_cases_averted_heatguard: number;
  aki_cases_averted_vs_ban: number;
  heatguard_work_hours_per_worker: number;
  calendar_work_hours_per_worker: number;
  productivity_gain_lo: number;
  productivity_gain_hi: number;
  productivity_worker_hours_lo: number;
  productivity_worker_hours_hi: number;
  capital_cost_usd: number;
  recurring_cost_usd: number;
  cost_per_worker_usd: number;
  assumptions: Record<string, unknown>;
}

export interface BusinessCase {
  crew_size: number;
  season_days: number;
  // benefit items (USD, crew + season)
  productivity_value_lo: number;
  productivity_value_hi: number;
  recovered_safe_work_value: number;
  aki_value: number;
  fines_avoided_value: number;
  death_averted_value: number;
  turnover_value: number;
  // roll-ups
  headline_benefit_lo: number;
  headline_benefit_hi: number;
  total_benefit_lo: number;
  total_benefit_hi: number;
  program_cost_usd: number;
  net_benefit_lo: number;
  net_benefit_hi: number;
  roi_multiple_lo: number;
  roi_multiple_hi: number;
  payback_days: number;
  assumptions: {
    daily_value_per_worker_usd: number;
    aki_case_cost_usd: number;
    fine_per_worker_usd: number;
    fine_probability_per_season: number;
    deaths_averted_estimate: number;
    headline_excludes: string[];
    note: string;
  };
}

export interface SensitivityRow {
  baseline_aki_incidence: number;
  aki_cases_baseline: number;
  aki_cases_averted_vs_ban: number;
  aki_cases_averted_heatguard: number;
}

export interface DemoPayload {
  site: { key: string; name: string; country: string; lat: number; lon: number };
  headline: string;
  intensity: Intensity;
  ban: { country: string; description: string };
  focus_day: string;
  available_days: string[];
  peak: { tdb_c: number; when: string };
  timeline: Timeline;
  compliance: Compliance;
  impact: ImpactReport;
  economics?: BusinessCase;
  sensitivity?: SensitivityRow[];
}

export interface Backtest {
  crew_reference: unknown;
  aki_cases_baseline: number;
  aki_cases_averted: number;
  reproduced_aki_reduction: number; // 0..1
  expected_aki_reduction: number;
  productivity_band: [number, number];
  expected_productivity_band: [number, number];
  passed: boolean;
}

export interface DecideRequest {
  site_key: string;
  tdb: number;
  rh: number;
  wind: number;
  solar: number;
  hour: number;
  intensity: Intensity;
  days_on_job: number;
  acclimatized: boolean;
  experienced: boolean;
  measured_wbgt: number | null;
}

export interface DecideResponse {
  advisory: Advisory;
  banned: boolean;
  ban_description: string;
  live: Signal[]; // 60 signals
}
