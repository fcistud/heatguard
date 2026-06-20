import { useState } from "react";
import type { DecideResponse, Intensity } from "../types";
import { api, ApiError } from "../api";
import { SIGNAL_COLOR, SIGNAL_LABEL } from "../lib/signals";

interface Props {
  siteKey: string;
}

const INTENSITIES: Intensity[] = ["light", "moderate", "heavy", "very_heavy"];

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  unit,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
}) {
  return (
    <label className="block">
      <div className="mb-1 flex items-center justify-between text-xs font-medium text-slate-500">
        <span>{label}</span>
        <span className="tabular-nums text-slate-700">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-indigo-500"
      />
    </label>
  );
}

export function WhatIfPanel({ siteKey }: Props) {
  const [tdb, setTdb] = useState(44);
  const [rh, setRh] = useState(35);
  const [solar, setSolar] = useState(850);
  const [hour, setHour] = useState(12);
  const [intensity, setIntensity] = useState<Intensity>("heavy");
  const [acclimatized, setAcclimatized] = useState(true);
  const [result, setResult] = useState<DecideResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.decide({
        site_key: siteKey,
        tdb,
        rh,
        wind: 2.0,
        solar,
        hour,
        intensity,
        days_on_job: acclimatized ? 120 : 0,
        acclimatized,
        experienced: false,
        measured_wbgt: null,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Request failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const adv = result?.advisory;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <NumberField label="Air temp" value={tdb} onChange={setTdb} min={20} max={55} unit="°C" />
          <NumberField label="Humidity" value={rh} onChange={setRh} min={5} max={100} unit="%" />
          <NumberField label="Solar" value={solar} onChange={setSolar} min={0} max={1100} step={25} unit=" W/m²" />
          <NumberField label="Hour" value={hour} onChange={setHour} min={5} max={19} unit=":00" />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-medium text-slate-500">Intensity</label>
          <select
            value={intensity}
            onChange={(e) => setIntensity(e.target.value as Intensity)}
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm font-medium text-slate-700 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
          >
            {INTENSITIES.map((i) => (
              <option key={i} value={i}>
                {i.replace("_", " ")}
              </option>
            ))}
          </select>

          <div className="ml-auto inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-xs font-semibold">
            <button
              onClick={() => setAcclimatized(true)}
              className={`rounded-md px-2.5 py-1 transition ${
                acclimatized ? "bg-emerald-500 text-white" : "text-slate-600"
              }`}
            >
              Acclimatized
            </button>
            <button
              onClick={() => setAcclimatized(false)}
              className={`rounded-md px-2.5 py-1 transition ${
                !acclimatized ? "bg-indigo-500 text-white" : "text-slate-600"
              }`}
            >
              New (day 0)
            </button>
          </div>
        </div>

        <button
          onClick={run}
          disabled={loading}
          className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
        >
          {loading ? "Deciding…" : "Run the engine →"}
        </button>
        {error && (
          <p className="text-sm text-red-600">{error}</p>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        {!adv && !error && (
          <div className="flex h-full min-h-[12rem] items-center justify-center text-center text-sm text-slate-400">
            Adjust conditions and run the live engine to see the advisory.
          </div>
        )}
        {adv && result && (
          <div>
            <div className="flex items-center justify-between">
              <span
                className="rounded-lg px-3 py-1 text-lg font-extrabold text-white"
                style={{ backgroundColor: SIGNAL_COLOR[adv.signal] }}
              >
                {SIGNAL_LABEL[adv.signal]}
              </span>
              <span className="text-sm tabular-nums text-slate-500">
                WBGT {adv.wbgt_c.toFixed(1)}°C
              </span>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-white px-3 py-2">
                <div className="text-[11px] uppercase tracking-wide text-slate-400">
                  Work / Rest
                </div>
                <div className="font-semibold tabular-nums text-slate-800">
                  {adv.cycle.work_min_per_hour} / {adv.cycle.rest_min_per_hour} min
                </div>
              </div>
              <div className="rounded-lg bg-white px-3 py-2">
                <div className="text-[11px] uppercase tracking-wide text-slate-400">
                  Hydration
                </div>
                <div className="font-semibold tabular-nums text-slate-800">
                  {adv.hydration.cups_250ml_per_h.toFixed(1)} cups · {Math.round(adv.hydration.water_ml_per_h)} ml/h
                </div>
              </div>
              <div className="rounded-lg bg-white px-3 py-2">
                <div className="text-[11px] uppercase tracking-wide text-slate-400">
                  Table
                </div>
                <div className="font-semibold text-slate-800">
                  {adv.cycle.table}
                  {adv.cycle.capped_by_acclimatization ? " · capped" : ""}
                </div>
              </div>
              <div className="rounded-lg bg-white px-3 py-2">
                <div className="text-[11px] uppercase tracking-wide text-slate-400">
                  Calendar ban
                </div>
                <div
                  className={`font-semibold ${
                    result.banned ? "text-slate-800" : "text-slate-500"
                  }`}
                >
                  {result.banned ? "Would apply" : "Would not apply"}
                </div>
              </div>
            </div>

            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              {adv.rationale}
            </p>
            <p className="mt-2 text-xs text-slate-400">
              {result.ban_description}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
