import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api";
import { ForecastPanel } from "../components/ForecastPanel";
import { SIGNAL_CONTRACT } from "./fixtures/broadcastContract";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    api: {
      ...actual.api,
      forecast: vi.fn(),
    },
  };
});

import { api } from "../api";

describe("ForecastPanel unavailable state", () => {
  beforeEach(() => {
    vi.mocked(api.forecast).mockReset();
  });

  it("renders zero hours, no signal labels, and a retry affordance", async () => {
    vi.mocked(api.forecast).mockRejectedValue(
      new ApiError("Could not reach the HeatGuard API. Is it running?", 0),
    );

    render(<ForecastPanel siteKey="dubai" />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });

    for (const signal of Object.keys(SIGNAL_CONTRACT) as (keyof typeof SIGNAL_CONTRACT)[]) {
      expect(screen.queryByText(SIGNAL_CONTRACT[signal].label)).not.toBeInTheDocument();
      expect(screen.queryByText(SIGNAL_CONTRACT[signal].short)).not.toBeInTheDocument();
    }

    // No hourly band cells (those use SIGNAL_SHORT in the ribbon when data loads).
    expect(document.querySelectorAll("[data-forecast-hour]").length).toBe(0);

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(api.forecast).toHaveBeenCalledTimes(2);
  });
});
