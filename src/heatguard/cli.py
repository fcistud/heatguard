"""``heatguard`` command-line interface.

Subcommands:
  sites      list demo sites
  decide     one decision from explicit conditions
  fetch      cache Open-Meteo data for a site/date-range
  fetch-demo pre-fetch + cache the two committed demo datasets
  demo       run the narrative (signal timeline, calendar-vs-adaptive gap, impact)
  backtest   reproduce the Nicaragua effect sizes
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from . import calendar_ban, economics, impact
from .compliance import ComplianceLog
from .scheduler import build_conditions, decide, schedule
from .service import DEMOS
from .sites import get_site, load_sites
from .types import MetabolicCategory, Posture, Signal, Weather, Worker
from .weather import daytime, fetch_archive, replay_worker

_COLOR = {
    Signal.WORK: "\033[32m", Signal.REST_IN_SHADE: "\033[33m",
    Signal.DRINK_NOW: "\033[36m", Signal.STOP: "\033[31m",
}
_RESET = "\033[0m"


def _c(signal: Signal) -> str:
    if not sys.stdout.isatty():
        return signal.value
    return f"{_COLOR[signal]}{signal.value:>13}{_RESET}"


def _intensity(name: str) -> MetabolicCategory:
    return MetabolicCategory(name)


# ---- subcommands ------------------------------------------------------------
def cmd_sites(args) -> int:
    for key, s in load_sites().items():
        print(f"  {key:12s} {s.name:12s} ({s.lat:.3f},{s.lon:.3f})  {s.country}  {calendar_ban.describe(s.country)}")
    return 0


def cmd_decide(args) -> int:
    site = get_site(args.site)
    ts = datetime.now().astimezone()
    w = Weather(ts.replace(hour=args.hour, minute=0, second=0, microsecond=0),
                args.tdb, args.rh, args.wind, args.solar, args.solar * 0.85, args.tdb - 15, 1013.0)
    worker = Worker("cli", days_on_job=args.days_on_job, acclimatized=not args.unacclimatized,
                    experienced_elsewhere=args.experienced)
    av = schedule(w, site, worker, _intensity(args.intensity),
                  measured_wbgt_c=args.measured_wbgt)
    print(f"\n  Site: {site.name}   Intensity: {args.intensity}   Worker: "
          f"{'new day '+str(args.days_on_job) if not worker.acclimatized else 'acclimatized'}")
    print(f"  WBGT: {av.wbgt_c:.1f} degC ({av.wbgt_source})")
    print(f"  SIGNAL: {_c(av.signal)}    work {av.cycle.work_min_per_hour} min / rest {av.cycle.rest_min_per_hour} min")
    print(f"  Hydration: {av.hydration.cups_250ml_per_h:.1f} cups/h ({av.hydration.water_ml_per_h:.0f} mL/h);"
          f" max safe continuous {av.hydration.max_exposure_min:.0f} min")
    print(f"  Calendar ban now: {'BANNED' if calendar_ban.is_banned(site.country, w.timestamp, av.wbgt_c) else 'permitted'}")
    print(f"  Why: {av.rationale}\n")
    return 0


def cmd_fetch(args) -> int:
    site = get_site(args.site)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    print(f"Fetching {site.name} {start}..{end} from Open-Meteo ...")
    rows = fetch_archive(site, start, end, refresh=args.refresh)
    print(f"  cached {len(rows)} hourly rows.")
    return 0


def cmd_fetch_demo(args) -> int:
    for key, cfg in DEMOS.items():
        site = get_site(cfg["site"])
        print(f"Fetching {site.name} {cfg['season_start']}..{cfg['season_end']} ...")
        rows = fetch_archive(site, cfg["season_start"], cfg["season_end"], refresh=args.refresh)
        print(f"  cached {len(rows)} rows.")
    return 0


def _hottest_row(rows: list[Weather]) -> Weather:
    return max(rows, key=lambda w: w.tdb_c)


def cmd_demo(args) -> int:
    cfg = DEMOS[args.site]
    site = get_site(cfg["site"])
    cat = cfg["intensity"]
    print(f"\n=== HeatGuard demo: {site.name} ===\n{cfg['headline']}\n")

    try:
        season = fetch_archive(site, cfg["season_start"], cfg["season_end"])
    except Exception as e:  # offline + no cache
        print(f"!! could not load weather ({e}). Run `heatguard fetch-demo` first.", file=sys.stderr)
        return 2

    focus = [w for w in season if w.timestamp.date() == cfg["focus_day"]]
    if not focus:
        focus = [w for w in season if w.timestamp.date() == _hottest_row(season).timestamp.date()]
    focus = [w for w in focus if 5 <= w.timestamp.hour <= 19]  # working window
    peak = _hottest_row(season)
    print(f"Peak air temperature in window: {peak.tdb_c:.1f} degC on {peak.timestamp:%Y-%m-%d %H:%M}\n")

    veteran = Worker("veteran", days_on_job=120, acclimatized=True)
    newcomer = Worker("newcomer-day0", days_on_job=0, acclimatized=False)

    print(f"{'time':>5} {'air':>5} {'WBGT':>5} | {'HeatGuard (veteran)':>20} {'wk':>3} | "
          f"{'HeatGuard (new)':>16} | {'calendar ban':>12} | gap")
    log = ComplianceLog(f"{site.name} demo site")
    gap_hours = 0
    protective = (Signal.STOP, Signal.REST_IN_SHADE)
    for w in focus:
        av = schedule(w, site, veteran, cat)
        an = schedule(w, site, newcomer, cat)
        banned = calendar_ban.is_banned(site.country, w.timestamp, av.wbgt_c)
        # a gap = either worker needed protection but the calendar ban didn't cover it
        gap = (av.signal in protective or an.signal in protective) and not banned
        gap_hours += int(gap)
        log.append(av, water_available=True)
        print(f"{w.timestamp:%H:%M} {w.tdb_c:5.1f} {av.wbgt_c:5.1f} | {_c(av.signal)} {av.cycle.work_min_per_hour:>3} | "
              f"{_c(an.signal)} | {'BANNED' if banned else 'permitted':>12} | {'<-- MISSED' if gap else ''}")

    print(f"\nGap: HeatGuard protected workers in {gap_hours} hour(s) on {cfg['focus_day']} that the calendar ban did not "
          f"cover — including the unacclimatized newcomer in the morning.")

    print(f"\nCompliance log: {len(log.records)} records, chain verified = {log.verify_chain()}")
    print(f"  head hash {log.head_hash[:24]}...  (tamper-evident audit trail)")

    # season impact
    work_rows = daytime(season, 5, 19)
    advs = replay_worker(work_rows, site, veteran, cat)
    hourly = impact.pair_with_ban(advs, site.country)
    season_days = len({w.timestamp.date() for w in work_rows})
    rep = impact.estimate_impact(hourly, crew_size=args.crew, season_days=season_days)
    print(f"\n=== Season impact ({site.name}, {season_days} days, crew {args.crew}) ===")
    print(f"  Dangerous work-hours HeatGuard caught that the ban MISSED: {rep.danger_hours_caught_vs_ban} "
          f"(ban covered only {rep.ban_coverage_pct:.0f}% of danger hours)")
    print(f"  Hours the blunt ban needlessly stopped SAFE work: {rep.ban_only_safe_hours}")
    print(f"  AKI cases averted vs the calendar ban: {rep.aki_cases_averted_vs_ban:.1f} "
          f"(of {rep.aki_cases_baseline:.0f} baseline; HeatGuard averts {rep.aki_cases_averted_heatguard:.1f})")
    print(f"  Productivity: maintained/raised by {int(rep.productivity_gain_lo*100)}-{int(rep.productivity_gain_hi*100)}% "
          f"(~{rep.productivity_worker_hours_lo:.0f}-{rep.productivity_worker_hours_hi:.0f} worker-hours)")
    print(f"  Cost: ~${rep.cost_per_worker_usd:.0f}/worker (mostly one-time capital)")

    bc = economics.business_case(rep)
    print(f"\n=== Business case (crew {args.crew}, season) ===")
    print(f"  Program cost:        ${bc.program_cost_usd:>12,.0f}")
    print(f"  Headline benefit:    ${bc.headline_benefit_lo:>12,.0f} - ${bc.headline_benefit_hi:,.0f} "
          f"(productivity + recovered safe work + AKI + fines avoided)")
    print(f"  Net benefit:         ${bc.net_benefit_lo:>12,.0f} - ${bc.net_benefit_hi:,.0f}")
    print(f"  ROI:                 {bc.roi_multiple_lo:>12.1f}x - {bc.roi_multiple_hi:.1f}x   "
          f"payback ~{bc.payback_days:.0f} days")
    print(f"  (excluded from headline: ${bc.death_averted_value:,.0f} death-averted + "
          f"${bc.turnover_value:,.0f} turnover)\n")
    return 0


def cmd_roi(args) -> int:
    from .service import season_impact_report
    report = season_impact_report(args.site, args.crew)
    bc = economics.business_case(report)
    print(f"\n=== HeatGuard business case: {args.site.title()} (crew {args.crew}) ===")
    for label, val in [
        ("Productivity gain", f"${bc.productivity_value_lo:,.0f} - ${bc.productivity_value_hi:,.0f}"),
        ("Recovered safe work", f"${bc.recovered_safe_work_value:,.0f}"),
        ("AKI cases averted", f"${bc.aki_value:,.0f}"),
        ("Fines avoided", f"${bc.fines_avoided_value:,.0f}"),
        ("— death averted (excl.)", f"${bc.death_averted_value:,.0f}"),
        ("— turnover (excl.)", f"${bc.turnover_value:,.0f}"),
    ]:
        print(f"  {label:26s} {val}")
    print(f"  {'Program cost':26s} ${bc.program_cost_usd:,.0f}")
    print(f"  {'ROI (headline)':26s} {bc.roi_multiple_lo:.1f}x - {bc.roi_multiple_hi:.1f}x, payback ~{bc.payback_days:.0f} days\n")
    return 0


def cmd_backtest(args) -> int:
    bt = impact.backtest_nicaragua()
    print("\n=== Nicaragua back-test (La Isla / Adelante, 2024 ILO report) ===")
    print(f"  reference crew: {bt['crew_reference']} workers")
    print(f"  reproduced AKI reduction: {bt['reproduced_aki_reduction']:.2%} (expected {bt['expected_aki_reduction']:.0%})")
    print(f"  productivity band: {bt['productivity_band']} (expected {bt['expected_productivity_band']})")
    print(f"  PASSED: {bt['passed']}\n")
    return 0 if bt["passed"] else 1


# ---- parser -----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="heatguard", description="Adaptive heat-safety scheduler for Gulf outdoor crews.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sites", help="list demo sites").set_defaults(func=cmd_sites)

    d = sub.add_parser("decide", help="one decision from explicit conditions")
    d.add_argument("--site", default="riyadh")
    d.add_argument("--tdb", type=float, required=True, help="air temperature degC")
    d.add_argument("--rh", type=float, required=True, help="relative humidity %%")
    d.add_argument("--wind", type=float, default=2.0)
    d.add_argument("--solar", type=float, default=800.0, help="shortwave radiation W/m2")
    d.add_argument("--hour", type=int, default=12)
    d.add_argument("--intensity", default="heavy", choices=[m.value for m in MetabolicCategory])
    d.add_argument("--measured-wbgt", type=float, default=None, dest="measured_wbgt")
    d.add_argument("--days-on-job", type=int, default=120, dest="days_on_job")
    d.add_argument("--unacclimatized", action="store_true")
    d.add_argument("--experienced", action="store_true", help="heat-experienced but new to this job")
    d.set_defaults(func=cmd_decide)

    f = sub.add_parser("fetch", help="cache Open-Meteo data")
    f.add_argument("--site", required=True)
    f.add_argument("--start", required=True)
    f.add_argument("--end", required=True)
    f.add_argument("--refresh", action="store_true")
    f.set_defaults(func=cmd_fetch)

    fd = sub.add_parser("fetch-demo", help="pre-fetch the committed demo datasets")
    fd.add_argument("--refresh", action="store_true")
    fd.set_defaults(func=cmd_fetch_demo)

    dm = sub.add_parser("demo", help="run the narrative demo")
    dm.add_argument("site", choices=list(DEMOS))
    dm.add_argument("--crew", type=int, default=100)
    dm.set_defaults(func=cmd_demo)

    ro = sub.add_parser("roi", help="business case / ROI for a demo site")
    ro.add_argument("site", choices=list(DEMOS))
    ro.add_argument("--crew", type=int, default=100)
    ro.set_defaults(func=cmd_roi)

    sub.add_parser("backtest", help="reproduce the Nicaragua effect sizes").set_defaults(func=cmd_backtest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
