import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SignalTile } from "../components/SignalTile";
import { WbgtGauge } from "../components/WbgtGauge";
import type { Advisory } from "../types";
import { SIGNAL_CONTRACT, WBGT_SOURCE_CONTRACT } from "./fixtures/broadcastContract";
import golden from "./fixtures/golden_broadcast.json";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    api: {
      ...actual.api,
      forecast: vi.fn().mockRejectedValue(
        Object.assign(new Error("offline"), { status: 0, name: "ApiError" }),
      ),
    },
  };
});

import { ForecastPanel } from "../components/ForecastPanel";
import { ApiError, api } from "../api";

describe("broadcast shell (stubbed API)", () => {
  it("surfaces the STOP instruction through SignalTile with golden fixtures", async () => {
    vi.mocked(api.forecast).mockRejectedValue(
      new ApiError("Forecast unavailable", 0),
    );

    const stop = golden.advisories.STOP as Advisory;
    render(
      <div>
        <SignalTile advisory={stop} time="13:00" workerLabel="Veteran" />
        <WbgtGauge
          wbgt={stop.wbgt_c}
          riskScore={stop.risk_score}
          airTemp={40}
          rh={18}
          source={stop.wbgt_source}
        />
        <ForecastPanel siteKey="dubai" />
      </div>,
    );

    expect(screen.getByText(SIGNAL_CONTRACT.STOP.label)).toBeInTheDocument();
    expect(
      screen.getByText(WBGT_SOURCE_CONTRACT[stop.wbgt_source as keyof typeof WBGT_SOURCE_CONTRACT]),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });
  });
});
