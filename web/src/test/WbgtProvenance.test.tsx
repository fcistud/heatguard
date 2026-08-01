import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WbgtGauge } from "../components/WbgtGauge";
import type { WbgtSource } from "../types";
import {
  UNKNOWN_PROVENANCE_FALLBACK,
  WBGT_SOURCE_CONTRACT,
} from "./fixtures/broadcastContract";

const SOURCES = Object.keys(WBGT_SOURCE_CONTRACT) as WbgtSource[];

describe("WBGT provenance labels", () => {
  it.each(SOURCES)("renders exact label for %s", (source) => {
    render(
      <WbgtGauge
        wbgt={28}
        riskScore={0.4}
        airTemp={40}
        rh={20}
        source={source}
      />,
    );
    expect(
      screen.getByText(WBGT_SOURCE_CONTRACT[source]),
    ).toBeInTheDocument();
  });

  it("renders safe fallback for missing provenance", () => {
    render(
      <WbgtGauge
        wbgt={28}
        riskScore={0.4}
        airTemp={40}
        rh={20}
        source={"" as WbgtSource}
      />,
    );
    expect(screen.getByText(UNKNOWN_PROVENANCE_FALLBACK)).toBeInTheDocument();
  });

  it("renders explicit unverified fallback for unknown provenance", () => {
    render(
      <WbgtGauge
        wbgt={28}
        riskScore={0.4}
        airTemp={40}
        rh={20}
        source={"made_up" as WbgtSource}
      />,
    );
    expect(screen.getByText("Unverified source (made_up)")).toBeInTheDocument();
  });
});
