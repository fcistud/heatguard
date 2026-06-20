import { useEffect, useMemo, useRef, useState } from "react";
import type { Advisory, Signal } from "../types";
import { SIGNAL_COLOR, SIGNAL_LABEL } from "../lib/signals";

interface SignalTileProps {
  advisory: Advisory;
  time: string; // "09:00"
  workerLabel: string; // "Veteran" | "New worker (day 0)"
}

/**
 * Build a 60-minute intra-hour broadcast from the cycle:
 *  - work minutes, with a DRINK_NOW pulse at the hydration cadence,
 *  - then a DRINK_NOW pulse opening the rest break,
 *  - then shaded rest.
 * STOP overrides the whole hour. Matches the engine's live_signal() logic so a
 * full-work hour still shows periodic drink prompts (otherwise the "simulate"
 * playback would look static).
 */
function minuteSignals(adv: Advisory): Signal[] {
  if (adv.signal === "STOP") return Array.from({ length: 60 }, () => "STOP" as Signal);

  const work = Math.max(0, Math.min(60, Math.round(adv.cycle.work_min_per_hour)));
  const cups = Math.max(1, adv.hydration.cups_250ml_per_h);
  // drink at least every 20 min during work, tighter when the target is higher
  const drinkEvery = Math.min(20, Math.max(10, Math.round(60 / cups)));

  const out: Signal[] = [];
  for (let i = 0; i < 60; i++) {
    if (i < work) {
      out.push(i > 0 && i % drinkEvery < 2 ? "DRINK_NOW" : "WORK");
    } else if (work < 60 && i < work + 3) {
      out.push("DRINK_NOW");
    } else {
      out.push("REST_IN_SHADE");
    }
  }
  return out;
}

const STEP_MS = 110; // ~6.5s for the full hour

export function SignalTile({ advisory, time, workerLabel }: SignalTileProps) {
  const minutes = useMemo(() => minuteSignals(advisory), [advisory]);
  const [playing, setPlaying] = useState(false);
  const [minute, setMinute] = useState(0);
  const timer = useRef<number | null>(null);

  // reset playback whenever the conditions (advisory) change
  useEffect(() => {
    setPlaying(false);
    setMinute(0);
  }, [advisory]);

  useEffect(() => {
    if (!playing) return;
    timer.current = window.setInterval(() => setMinute((m) => (m + 1) % 60), STEP_MS);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [playing]);

  const toggle = () => {
    setPlaying((p) => {
      const next = !p;
      if (next) setMinute(0); // always restart from :00
      return next;
    });
  };

  const liveSignal: Signal = playing ? minutes[minute] : advisory.signal;
  const color = SIGNAL_COLOR[liveSignal];
  const cyc = advisory.cycle;
  const hyd = advisory.hydration;
  const clock = `:${String(minute).padStart(2, "0")}`;

  return (
    <div
      className="relative overflow-hidden rounded-2xl p-6 text-white shadow-card transition-colors duration-200"
      style={{ backgroundColor: color }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-white/80">
          <span>Live signal · {workerLabel} · {time}</span>
          {playing && (
            <span className="flex items-center gap-1 rounded-full bg-white/25 px-2 py-0.5 tabular-nums">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
              {clock}
            </span>
          )}
        </div>
        <button
          onClick={toggle}
          className="rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur transition hover:bg-white/30"
        >
          {playing ? "❚❚ pause" : "▶ simulate the hour"}
        </button>
      </div>

      <div className="mt-3 flex items-end gap-3">
        <div
          className={`text-5xl font-extrabold leading-none tracking-tight transition-transform duration-150 ${
            liveSignal === "DRINK_NOW" && playing ? "scale-105 animate-pulse" : ""
          }`}
        >
          {SIGNAL_LABEL[liveSignal]}
        </div>
        {playing && (
          <div className="pb-1 text-sm font-medium text-white/80 tabular-nums">
            minute {minute + 1} / 60
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div className="rounded-xl bg-white/15 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-white/70">Work / Rest</div>
          <div className="mt-0.5 font-semibold tabular-nums">
            {cyc.work_min_per_hour} min · {cyc.rest_min_per_hour} min
          </div>
        </div>
        <div className="rounded-xl bg-white/15 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-white/70">Hydration</div>
          <div className="mt-0.5 font-semibold tabular-nums">
            {hyd.cups_250ml_per_h.toFixed(1)} cups / h
          </div>
        </div>
        <div className="rounded-xl bg-white/15 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-white/70">Max continuous</div>
          <div className="mt-0.5 font-semibold tabular-nums">
            {Math.round(hyd.max_exposure_min)} min
          </div>
        </div>
      </div>

      {/* 60-minute broadcast ribbon with a moving play-head */}
      <div className="mt-4">
        <div className="relative flex h-3.5 w-full overflow-hidden rounded-full bg-white/20">
          {minutes.map((s, i) => (
            <div
              key={i}
              className="h-full flex-1 transition-opacity"
              style={{
                backgroundColor: SIGNAL_COLOR[s],
                opacity: playing && i > minute ? 0.3 : 1,
              }}
            />
          ))}
          {playing && (
            <div
              className="absolute top-0 h-full w-[2px] bg-white shadow-[0_0_4px_rgba(255,255,255,0.9)]"
              style={{ left: `${(minute / 59) * 100}%` }}
            />
          )}
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-white/70">
          <span>:00</span>
          <span>{playing ? `now ${clock}` : "intra-hour broadcast — press ▶"}</span>
          <span>:59</span>
        </div>
      </div>

      <p className="mt-4 text-sm leading-relaxed text-white/90">{advisory.rationale}</p>
    </div>
  );
}
