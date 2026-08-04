import { describe, expect, it } from "vitest";
import {
  SCIENCE_NOT_INSTRUCTION,
  conflictAnalysisLabel,
  hasLegalScientificConflict,
} from "../lib/advisoryLane";
import type { Advisory } from "../types";

function cycle(workMin: number): Advisory["cycle"] {
  return {
    work_fraction: workMin / 60,
    work_min_per_hour: workMin,
    rest_min_per_hour: 60 - workMin,
    threshold_wbgt_c: null,
    table: "TLV",
    capped_by_acclimatization: false,
  };
}

describe("hasLegalScientificConflict", () => {
  it("is true when ban is active and science signals WORK", () => {
    expect(
      hasLegalScientificConflict(true, {
        signal: "WORK",
        cycle: cycle(45),
      }),
    ).toBe(true);
  });

  it("is true when ban is active and science allocates work minutes without WORK signal", () => {
    expect(
      hasLegalScientificConflict(true, {
        signal: "REST_IN_SHADE",
        cycle: cycle(20),
      }),
    ).toBe(true);
  });

  it("is false when ban is inactive even if science says WORK", () => {
    expect(
      hasLegalScientificConflict(false, {
        signal: "WORK",
        cycle: cycle(45),
      }),
    ).toBe(false);
  });

  it("is false when ban is active but science allocates no work", () => {
    expect(
      hasLegalScientificConflict(true, {
        signal: "STOP",
        cycle: cycle(0),
      }),
    ).toBe(false);
  });
});

describe("conflictAnalysisLabel", () => {
  it("leads with operational instruction and demotes science as non-instruction", () => {
    const label = conflictAnalysisLabel("14:00", "STOP", "WORK");
    expect(label.startsWith("14:00 — operational instruction: STOP")).toBe(true);
    expect(label).toContain(SCIENCE_NOT_INSTRUCTION);
    expect(label).toContain("Scientific assessment (WORK) is comparison data only");
    expect(label).toContain("legal ban governs permission");
    // Must not present scientific WORK as a peer operational instruction.
    expect(label).not.toMatch(/operational STOP;\s*scientific WORK/i);
  });
});
