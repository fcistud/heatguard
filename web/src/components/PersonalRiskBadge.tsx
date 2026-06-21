export function PersonalRiskBadge({
  score,
  elevated,
  compact = false,
}: {
  score: number;
  elevated: boolean;
  compact?: boolean;
}) {
  if (!elevated && score < 0.25) {
    return null;
  }
  const pct = Math.round(score * 100);
  return (
    <span
      className={`inline-flex items-center rounded-full font-semibold ${
        elevated
          ? "bg-orange-100 text-orange-800 ring-1 ring-orange-200"
          : "bg-slate-100 text-slate-600 ring-1 ring-slate-200"
      } ${compact ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-xs"}`}
      title={`Personal ML risk ${pct}%`}
    >
      {elevated ? "ELEVATED" : "watch"} {pct}%
    </span>
  );
}
