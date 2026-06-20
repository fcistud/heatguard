import type { Signal } from "../types";

export const SIGNAL_COLOR: Record<Signal, string> = {
  WORK: "#16a34a",
  REST_IN_SHADE: "#f59e0b",
  DRINK_NOW: "#0ea5e9",
  STOP: "#dc2626",
};

export const SIGNAL_LABEL: Record<Signal, string> = {
  WORK: "WORK",
  REST_IN_SHADE: "REST IN SHADE",
  DRINK_NOW: "DRINK NOW",
  STOP: "STOP",
};

export const SIGNAL_SHORT: Record<Signal, string> = {
  WORK: "Work",
  REST_IN_SHADE: "Rest",
  DRINK_NOW: "Drink",
  STOP: "Stop",
};

// Tailwind text/bg helpers keyed by signal (used for chips and tinted surfaces).
export const SIGNAL_BG_SOFT: Record<Signal, string> = {
  WORK: "bg-emerald-50 text-emerald-700 border-emerald-200",
  REST_IN_SHADE: "bg-amber-50 text-amber-700 border-amber-200",
  DRINK_NOW: "bg-sky-50 text-sky-700 border-sky-200",
  STOP: "bg-red-50 text-red-700 border-red-200",
};

/** Map a 0..1 risk score to a color along green -> amber -> red. */
export function riskColor(score: number): string {
  const s = Math.max(0, Math.min(1, score));
  if (s < 0.5) {
    // green -> amber
    return lerpHex("#16a34a", "#f59e0b", s / 0.5);
  }
  // amber -> red
  return lerpHex("#f59e0b", "#dc2626", (s - 0.5) / 0.5);
}

function lerpHex(a: string, b: string, t: number): string {
  const ca = hexToRgb(a);
  const cb = hexToRgb(b);
  const r = Math.round(ca[0] + (cb[0] - ca[0]) * t);
  const g = Math.round(ca[1] + (cb[1] - ca[1]) * t);
  const bl = Math.round(ca[2] + (cb[2] - ca[2]) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

export const WBGT_SOURCE_LABEL: Record<string, string> = {
  liljegren: "Liljegren-estimated",
  measured: "Measured (sensor)",
  fallback: "Fallback estimate",
};
