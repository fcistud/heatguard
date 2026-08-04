import type { Advisory, AdvisoryLaneRow } from "../types";

export type WorkerKey = "veteran" | "newcomer";

/** Operational advisory after legal precedence (falls back to scientific lane). */
export function effectiveLane(row: AdvisoryLaneRow, worker: WorkerKey): Advisory {
  if (worker === "veteran") {
    return row.veteran_effective ?? row.veteran;
  }
  return row.newcomer_effective ?? row.newcomer;
}

/** Scientific scheduler output (comparison / analytic pane). */
export function scientificLane(row: AdvisoryLaneRow, worker: WorkerKey): Advisory {
  return worker === "veteran" ? row.veteran : row.newcomer;
}

export const COMPARISON_DISCLAIMER =
  "Comparison view for analysis. Legal prohibition always governs operational permission.";

export const ANALYTIC_METRIC_HINT =
  "Scenario metric — not an operational schedule.";

export const LEGAL_GOVERNS_LINE =
  "Scientific assessment indicates potentially safe conditions; legal ban governs operational permission.";
