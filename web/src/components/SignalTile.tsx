import { useEffect, useMemo, useRef, useState } from "react";
import type { Advisory, Signal } from "../types";
import { SIGNAL_COLOR, SIGNAL_LABEL } from "../lib/signals";

interface SignalTileProps {
  advisory: Advisory;
  time: string; // "09:00"
  workerLabel: string; // "Veteran" | "New worker (day 0)"
}

/**
 * Build a 60-minute intra-hour broadcast from the cycle: work minutes, then a
 * DRINK_NOW pulse, then rest minutes. STOP overrides the whole hour.
 */
function minuteSignals(adv: Advisory): Signal[] {
  const out: Signal[] = [];
  if (adv.signal === "STOP") {
    for (let i = 0; i < 60; i++) out.push("STOP");
    return out;
  }
  const work = Math.max(0, Math.min(60, adv.cycle.work_min_per_hour));
  const rest = Math.max(0, 60 - work);
  // A short drink pulse at the start of each rest break.
  for (let i = 0; i < 60; i++) {
    if (i < work) {
      out.push("WORK");
    } else if (i < work + 2 && rest > 0) {
      out.push("DRINK_NOW");
    } else {
      out.push("REST_IN_SHADE");
    }
  }
  return out;
}

export function SignalTile({ advisory, time, workerLabel }: SignalTileProps) {
  // The parent remounts this via a `key` tied to the advisory, so local
  // playback state naturally resets when conditions change.
  const minutes = useMemo(() => minuteSignals(advisory), [advisory]);
  const [playing, setPlaying] = useState(false);
  const [minute, setMinute] = useState(0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) {
      if (timer.current) window.clearInterval(timer.current);
      return;
    }
    timer.current = window.setInterval(() => {
      setMinute((m) => (m + 1) % 60);
    }, 120);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [playing]);

  const liveSignal: Signal = playing ? minutes[minute] : advisory.signal;
  const color = SIGNAL_COLOR[liveSignal];
  const cyc = advisory.cycle;
  const hyd = advisory.hydration;

  return (
    <div
      className="relative overflow-hidden rounded-2xl p-6 text-white shadow-card transition-colors duration-300"
      style={{ backgroundColor: color }}
    >
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-widest text-white/80">
          Live signal · {workerLabel} · {time}
        </div>
        <button
          onClick={() => setPlaying((p) => !p)}
          className="rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white backdrop-blur transition hover:bg-white/30"
        >
          {playing ? "❚❚ pause" : "▶ simulate the hour"}
        </button>
      </div>

      <div className="mt-3 flex items-end gap-3">
        <div
          className={`text-5xl font-extrabold leading-none tracking-tight ${
            liveSignal === "DRINK_NOW" && playing ? "animate-pulseSoft" : ""
          }`}
        >
          {SIGNAL_LABEL[liveSignal]}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div className="rounded-xl bg-white/15 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-white/70">
            Work / Rest
          </div>
          <div className="mt-0.5 font-semibold tabular-nums">
            {cyc.work_min_per_hour} min · {cyc.rest_min_per_hour} min
          </div>
        </div>
        <div className="rounded-xl bg-white/15 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-white/70">
            Hydration
          </div>
          <div className="mt-0.5 font-semibold tabular-nums">
            {hyd.cups_250ml_per_h.toFixed(1)} cups / h
          </div>
        </div>
        <div className="rounded-xl bg-white/15 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-white/70">
            Max continuous
          </div>
          <div className="mt-0.5 font-semibold tabular-nums">
            {Math.round(hyd.max_exposure_min)} min
          </div>
        </div>
      </div>

      {/* 60-minute progress ribbon */}
      <div className="mt-4">
        <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-white/20">
          {minutes.map((s, i) => (
            <div
              key={i}
              className="h-full flex-1"
              style={{
                backgroundColor: SIGNAL_COLOR[s],
                opacity: playing && i > minute ? 0.35 : 1,
                outline:
                  playing && i === minute ? "1px solid rgba(255,255,255,0.9)" : "none",
              }}
            />
          ))}
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-white/70">
          <span>:00</span>
          <span>{playing ? `:${String(minute).padStart(2, "0")}` : "intra-hour broadcast"}</span>
          <span>:59</span>
        </div>
      </div>

      <p className="mt-4 text-sm leading-relaxed text-white/90">
        {advisory.rationale}
      </p>
    </div>
  );
}
