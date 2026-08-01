/**
 * Expected broadcast contract for WO-004.
 *
 * Deliberately NOT imported from `lib/signals.ts` — if labels/colours drift in
 * the module under test, these fixtures must fail the suite.
 */
export const SIGNAL_CONTRACT = {
  WORK: {
    label: "WORK",
    short: "Work",
    color: "#16a34a",
  },
  REST_IN_SHADE: {
    label: "REST IN SHADE",
    short: "Rest",
    color: "#f59e0b",
  },
  DRINK_NOW: {
    label: "DRINK NOW",
    short: "Drink",
    color: "#0ea5e9",
  },
  STOP: {
    label: "STOP",
    short: "Stop",
    color: "#dc2626",
  },
} as const;

export const WBGT_SOURCE_CONTRACT = {
  liljegren: "Liljegren-estimated",
  measured: "Measured (sensor)",
  fallback: "Fallback estimate",
} as const;

export const UNKNOWN_PROVENANCE_FALLBACK = "Provenance unavailable";
