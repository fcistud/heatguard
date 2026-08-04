import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BanVsAdaptiveTimeline } from "../components/BanVsAdaptiveTimeline";
import type { Advisory, Timeline } from "../types";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="chart">{children}</div>
  ),
  AreaChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Area: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
}));

function advisory(
  signal: Advisory["signal"],
  workMin: number,
): Advisory {
  return {
    timestamp: "2024-07-15T12:00:00Z",
    site_name: "Demo",
    worker_id: "veteran",
    wbgt_c: 31,
    wbgt_source: "liljegren",
    signal,
    cycle: {
      work_fraction: workMin / 60,
      work_min_per_hour: workMin,
      rest_min_per_hour: 60 - workMin,
      threshold_wbgt_c: null,
      table: "TLV",
      capped_by_acclimatization: false,
    },
    hydration: {
      sweat_loss_g_per_h: 500,
      water_ml_per_h: 500,
      cups_250ml_per_h: 2,
      max_exposure_min: 60,
      core_temp_c: 37.5,
      phs_valid: true,
    },
    acclim_fraction: 1,
    rationale: "test",
    risk_score: 0.4,
  };
}

const timeline: Timeline = {
  site: "demo",
  country: "QA",
  date: "2024-07-15",
  gap_hours: 1,
  rows: [
    {
      hour: 12,
      time: "12:00",
      tdb_c: 38,
      rh_pct: 45,
      wbgt_c: 31,
      wbgt_source: "liljegren",
      banned: true,
      gap: false,
      veteran: advisory("WORK", 40),
      newcomer: advisory("WORK", 30),
      veteran_effective: advisory("STOP", 0),
      newcomer_effective: advisory("STOP", 0),
    },
  ],
};

describe("BanVsAdaptiveTimeline legal conflict demotion", () => {
  it("marks conflict hours as analysis-only, not an instruction", () => {
    render(
      <BanVsAdaptiveTimeline
        timeline={timeline}
        worker="veteran"
        selectedHour={null}
        onSelectHour={() => undefined}
        availableDays={["2024-07-15"]}
        focusDay="2024-07-15"
        onSelectDay={() => undefined}
        loadingDay={false}
      />,
    );

    expect(screen.getAllByText("≠instr").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText(/Legal conflict — science shown as analysis only/i),
    ).toBeInTheDocument();

    const conflictCell = screen.getByRole("button", {
      name: /operational instruction: STOP/i,
    });
    const aria = conflictCell.getAttribute("aria-label") ?? "";
    expect(aria).toContain("Analysis only — not an instruction");
    expect(aria).not.toMatch(/operational STOP;\s*scientific WORK/i);
  });
});
