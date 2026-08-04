import type { Advisory, AdvisoryLaneRow, Signal } from "../types";

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
  "Comparison view: calendar ban vs HeatGuard operational instruction. Legal prohibition always governs permission.";

export const ANALYTIC_METRIC_HINT =
  "Scenario metric — not an operational schedule.";

export const LEGAL_GOVERNS_LINE =
  "Scientific assessment indicates some work may be possible; legal ban governs operational permission.";

/** Inline non-goal: scientific lane is never a work instruction. */
export const SCIENCE_NOT_INSTRUCTION =
  "Analysis only — not an instruction.";

/** True when ban is active and science would still allocate outdoor work. */
export function hasLegalScientificConflict(
  banned: boolean,
  scientific: Pick<Advisory, "signal" | "cycle">,
): boolean {
  return (
    banned &&
    (scientific.signal === "WORK" || scientific.cycle.work_min_per_hour > 0)
  );
}

/**
 * Accessible hover/label copy for timeline cells with a science-vs-law conflict.
 * Puts operational instruction first; demotes scientific signal as non-instruction analysis.
 */
export function conflictAnalysisLabel(
  time: string,
  operational: Signal,
  scientific: Signal,
): string {
  return (
    `${time} — operational instruction: ${operational}. ` +
    `${SCIENCE_NOT_INSTRUCTION} ` +
    `Scientific assessment (${scientific}) is comparison data only; legal ban governs permission.`
  );
}
