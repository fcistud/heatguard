/**
 * HeatGuard brand mark — kept identical to the landing page:
 *  - a ~34px rounded square with a radial orange→red gradient + orange glow,
 *    centered 🌡️ emoji,
 *  - the wordmark "HeatGuard" in the display font, with "Guard" in heat-orange.
 */

interface BrandProps {
  /** Optional one-line subtitle under the wordmark (TopBar uses it). */
  subtitle?: string;
}

export function Logo({ className = "" }: { className?: string }) {
  return (
    <div
      className={`grid place-items-center text-[1.05rem] leading-none ${className}`}
      style={{
        width: 34,
        height: 34,
        borderRadius: 9,
        background:
          "radial-gradient(circle at 32% 28%, #ffd27a, #ff7a18 45%, #dc2626 92%)",
        boxShadow: "0 0 22px -2px #ff5a1f",
      }}
      aria-hidden="true"
    >
      <span role="img" aria-label="thermometer">
        🌡️
      </span>
    </div>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`font-display text-lg font-bold tracking-tight text-slate-900 dark:text-slate-50 ${className}`}
    >
      Heat<span className="text-heat-orange">Guard</span>
    </span>
  );
}

export function Brand({ subtitle }: BrandProps) {
  return (
    <div className="flex items-center gap-3">
      <Logo />
      <div>
        <Wordmark />
        {subtitle && (
          <div className="-mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
}
