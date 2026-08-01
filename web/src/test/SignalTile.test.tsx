import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SignalTile } from "../components/SignalTile";
import type { Advisory, Signal } from "../types";
import { SIGNAL_CONTRACT } from "./fixtures/broadcastContract";
import golden from "./fixtures/golden_broadcast.json";

const SIGNALS = Object.keys(SIGNAL_CONTRACT) as Signal[];

function advisoryFor(signal: Signal): Advisory {
  return golden.advisories[signal] as Advisory;
}

describe("SignalTile broadcast parity", () => {
  it.each(SIGNALS)(
    "renders exact label and colour token for %s",
    (signal) => {
      const contract = SIGNAL_CONTRACT[signal];
      const { container } = render(
        <SignalTile
          advisory={advisoryFor(signal)}
          time="12:00"
          workerLabel="Veteran"
        />,
      );
      expect(screen.getByText(contract.label)).toBeInTheDocument();
      const tile = container.firstElementChild as HTMLElement;
      expect(tile.style.backgroundColor).toBe(hexToRgb(contract.color));
    },
  );
});

/** jsdom normalises hex style colours to rgb(). */
function hexToRgb(hex: string): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgb(${r}, ${g}, ${b})`;
}
