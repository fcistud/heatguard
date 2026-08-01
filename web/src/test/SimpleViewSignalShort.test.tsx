import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SimpleView } from "../components/SimpleView";
import type { Advisory, Timeline, TimelineRow } from "../types";
import { SIGNAL_CONTRACT } from "./fixtures/broadcastContract";
import golden from "./fixtures/golden_broadcast.json";

function timelineAround(row: TimelineRow): Timeline {
  return {
    site: "Dubai",
    country: "AE",
    date: "2025-05-16",
    gap_hours: 1,
    rows: [row],
  };
}

describe("SimpleView signal short form", () => {
  it("uses the contract short label in the ban-gap callout for STOP", () => {
    const row = golden.timeline_rows.STOP as TimelineRow;
    // Force gap + not banned so the short-label sentence renders.
    const gapRow: TimelineRow = { ...row, banned: false, gap: true };
    const advisory = gapRow.veteran as Advisory;

    render(
      <SimpleView
        siteName="Dubai"
        demos={["dubai"]}
        selectedSite="dubai"
        onSelectSite={() => undefined}
        timeline={timelineAround(gapRow)}
        currentRow={gapRow}
        advisory={advisory}
        wbgt={gapRow.wbgt_c}
        source={gapRow.wbgt_source}
        banned={false}
        selectedHour={gapRow.hour}
        onSelectHour={() => undefined}
        worker="veteran"
        onSelectWorker={() => undefined}
        newcomerDays={0}
      />,
    );

    expect(
      screen.getByText(/HeatGuard calls a Stop/),
    ).toBeInTheDocument();
    expect(screen.getAllByText(SIGNAL_CONTRACT.STOP.label).length).toBeGreaterThanOrEqual(1);
  });
});
