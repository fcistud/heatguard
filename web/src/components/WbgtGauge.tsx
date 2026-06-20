import { riskColor, WBGT_SOURCE_LABEL } from "../lib/signals";
import type { WbgtSource } from "../types";

interface WbgtGaugeProps {
  wbgt: number;
  riskScore: number; // 0..1
  airTemp: number;
  rh: number;
  source: WbgtSource;
}

const R = 90;
const CX = 110;
const CY = 110;
const START = 180; // degrees
const SWEEP = 180;

function polar(angleDeg: number): [number, number] {
  const a = (angleDeg * Math.PI) / 180;
  return [CX + R * Math.cos(a), CY - R * Math.sin(a)];
}

function arcPath(fromDeg: number, toDeg: number): string {
  const [x1, y1] = polar(fromDeg);
  const [x2, y2] = polar(toDeg);
  const large = Math.abs(toDeg - fromDeg) > 180 ? 1 : 0;
  // sweep flag 0 because angles decrease left->right in this coordinate frame
  return `M ${x1} ${y1} A ${R} ${R} 0 ${large} 0 ${x2} ${y2}`;
}

export function WbgtGauge({ wbgt, riskScore, airTemp, rh, source }: WbgtGaugeProps) {
  const score = Math.max(0, Math.min(1, riskScore));
  // 180deg (left) = low risk, 0deg (right) = high risk.
  const needleDeg = START - SWEEP * score;
  const valueColor = riskColor(score);

  // Coloured segments green -> amber -> red.
  const segs = [
    { from: 180, to: 120, color: "#16a34a" },
    { from: 120, to: 60, color: "#f59e0b" },
    { from: 60, to: 0, color: "#dc2626" },
  ];

  const [nx, ny] = polar(needleDeg);

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 220 140" className="w-full max-w-[260px]">
        {/* track */}
        <path
          d={arcPath(180, 0)}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={16}
          strokeLinecap="round"
        />
        {segs.map((s, i) => (
          <path
            key={i}
            d={arcPath(s.from, s.to)}
            fill="none"
            stroke={s.color}
            strokeWidth={16}
            strokeLinecap="butt"
            opacity={0.9}
          />
        ))}
        {/* needle */}
        <line
          x1={CX}
          y1={CY}
          x2={nx}
          y2={ny}
          stroke="#0f172a"
          strokeWidth={3}
          strokeLinecap="round"
        />
        <circle cx={CX} cy={CY} r={6} fill="#0f172a" />
        {/* value */}
        <text
          x={CX}
          y={CY - 22}
          textAnchor="middle"
          className="font-bold"
          fontSize="30"
          fill={valueColor}
        >
          {wbgt.toFixed(1)}
        </text>
        <text
          x={CX}
          y={CY - 4}
          textAnchor="middle"
          fontSize="11"
          fill="#64748b"
        >
          WBGT °C
        </text>
      </svg>

      <div className="mt-1 flex items-center gap-2 text-xs">
        <span className="font-medium text-slate-500">Risk</span>
        <span
          className="rounded-full px-2 py-0.5 text-xs font-semibold text-white"
          style={{ backgroundColor: valueColor }}
        >
          {Math.round(score * 100)}%
        </span>
      </div>

      <div className="mt-3 grid w-full grid-cols-2 gap-2 text-center">
        <div className="rounded-lg bg-slate-50 px-2 py-2">
          <div className="text-[11px] uppercase tracking-wide text-slate-400">
            Air temp
          </div>
          <div className="font-semibold tabular-nums text-slate-800">
            {airTemp.toFixed(1)}°C
          </div>
        </div>
        <div className="rounded-lg bg-slate-50 px-2 py-2">
          <div className="text-[11px] uppercase tracking-wide text-slate-400">
            Humidity
          </div>
          <div className="font-semibold tabular-nums text-slate-800">
            {Math.round(rh)}%
          </div>
        </div>
      </div>

      <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600">
        <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />
        {WBGT_SOURCE_LABEL[source] ?? source}
      </div>
    </div>
  );
}
