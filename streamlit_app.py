"""HeatGuard — pure-Python interactive demo (no build step).

Run:  streamlit run streamlit_app.py
Requires the demo weather cache:  heatguard fetch-demo
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from heatguard import service
from heatguard.types import MetabolicCategory, Signal

SIGNAL_COLOR = {
    "WORK": "#16a34a",
    "REST_IN_SHADE": "#f59e0b",
    "DRINK_NOW": "#0ea5e9",
    "STOP": "#dc2626",
}

st.set_page_config(page_title="HeatGuard", layout="wide", page_icon="🌡️")


@st.cache_data(show_spinner=False)
def get_demo(site_key: str, crew: int) -> dict:
    return service.build_demo(site_key, crew)


@st.cache_data(show_spinner=False)
def get_timeline(site_key: str, day: str, intensity: str, newcomer_days: int) -> dict:
    return service.timeline_for_day(site_key, date.fromisoformat(day), intensity, newcomer_days)


@st.cache_data(show_spinner=False)
def get_backtest() -> dict:
    return service.backtest()


def signal_badge(sig: str) -> str:
    return f"<span style='background:{SIGNAL_COLOR[sig]};color:white;padding:2px 8px;border-radius:6px;font-weight:600'>{sig}</span>"


# ---- sidebar ---------------------------------------------------------------
st.sidebar.title("🌡️ HeatGuard")
st.sidebar.caption("Adaptive WBGT work-rest-hydration scheduling for Gulf outdoor crews")
site_key = st.sidebar.selectbox("Demo site", list(service.DEMOS), format_func=str.title)
crew = st.sidebar.slider("Crew size", 10, 1000, 100, 10)
worker_view = st.sidebar.radio("Worker", ["Veteran (acclimatized)", "New worker"])
worker_key = "veteran" if worker_view.startswith("Veteran") else "newcomer"
# per-worker individualization (not one crew-wide setting)
intensity = st.sidebar.selectbox(
    "Work intensity", [m.value for m in MetabolicCategory if m.value != "rest"], index=2,
    format_func=lambda s: s.replace("_", " ").title(),
)
newcomer_days = st.sidebar.slider("New worker: days on job", 0, 14, 0,
                                  help="NIOSH acclimatization ramp", disabled=worker_key != "newcomer")

try:
    demo = get_demo(site_key, crew)
except FileNotFoundError:
    st.error("Demo weather not cached. Run `heatguard fetch-demo` in a terminal first.")
    st.stop()

# ---- header ----------------------------------------------------------------
st.title("HeatGuard")
st.markdown(f"**{demo['headline']}**")
c1, c2, c3 = st.columns(3)
c1.metric("Peak air temp (season)", f"{demo['peak']['tdb_c']:.1f} °C", demo["peak"]["when"])
c2.metric("Calendar ban", demo["ban"]["description"].split(":", 1)[0])
c3.caption(f"_{demo['ban']['description']}_")

# ---- day scrubber + timeline -----------------------------------------------
st.subheader("Calendar ban vs. HeatGuard — hour by hour")
st.caption(f"Individualised to **{intensity.replace('_',' ')}** work"
           + (f" · new worker on **day {newcomer_days}**" if worker_key == "newcomer" else ""))
days = demo["available_days"]
day = st.select_slider("Day", options=days, value=demo["focus_day"])
tl = get_timeline(site_key, day, intensity, newcomer_days)
rows = tl["rows"]

table = []
for r in rows:
    adv = r[worker_key]
    table.append({
        "Time": r["time"],
        "Air °C": r["tdb_c"],
        "RH %": r["rh_pct"],
        "WBGT °C": r["wbgt_c"],
        "HeatGuard": adv["signal"],
        "Work min": adv["cycle"]["work_min_per_hour"],
        "Cups/h": round(adv["hydration"]["cups_250ml_per_h"], 1),
        "Calendar ban": "BANNED" if r["banned"] else "permitted",
        "Gap": "⚠️ MISSED" if r["gap"] else "",
    })
df = pd.DataFrame(table)


def _color_signal(val):
    return f"background-color:{SIGNAL_COLOR.get(val, '')};color:white;font-weight:600" if val in SIGNAL_COLOR else ""


def _color_ban(val):
    return "background-color:#1f2937;color:white" if val == "BANNED" else "color:#6b7280"


styled = (
    df.style
    .applymap(_color_signal, subset=["HeatGuard"])
    .applymap(_color_ban, subset=["Calendar ban"])
)
left, right = st.columns([3, 2])
with left:
    st.dataframe(styled, hide_index=True, width="stretch", height=560)
with right:
    st.line_chart(df.set_index("Time")[["Air °C", "WBGT °C"]], height=260)
    gap = tl["gap_hours"]
    st.info(f"**{gap} hour(s)** on {day}: HeatGuard protected workers the calendar ban did **not** cover "
            f"— including the unacclimatized newcomer in the morning.")
    # live signal preview for the hottest hour
    hot = max(rows, key=lambda r: r["wbgt_c"])
    adv = hot[worker_key]
    st.markdown(f"**Peak hour {hot['time']}** ({worker_view}): {signal_badge(adv['signal'])}", unsafe_allow_html=True)
    st.caption(adv["rationale"])

    # on-site meter (measured WBGT) — sensor vs estimate
    with st.expander("🔧 On-site WBGT meter (sensor vs estimate)"):
        st.caption("Estimation is approximate without a black-globe sensor. In production a "
                   "~$300 meter feeds the SAME engine — enter a reading to see it override the estimate.")
        meas = st.slider("Meter reading °C", 20.0, 45.0, float(round(adv["wbgt_c"], 1)), 0.1, key="meter")
        res = service.hour_advisory(site_key, date.fromisoformat(day), hot["hour"],
                                    worker_kind=worker_key, newcomer_days=newcomer_days,
                                    intensity=intensity, measured_wbgt=meas)
        a2 = res["advisory"]
        st.markdown(f"Model estimate **{res['estimated_wbgt_c']}°C** ({res['estimated_source']}) → "
                    f"meter **{meas:.1f}°C** (measured): {signal_badge(a2['signal'])}", unsafe_allow_html=True)
        if a2["signal"] != adv["signal"]:
            st.warning(f"The signal changes from {adv['signal']} to {a2['signal']} with the measured value.")

# ---- impact ----------------------------------------------------------------
st.subheader(f"Season impact — {demo['site']['name']}, crew {crew}")
imp = demo["impact"]
m = st.columns(4)
m[0].metric("Danger hours the ban MISSED", f"{imp['danger_hours_caught_vs_ban']:,}",
            help=f"Ban covered only {imp['ban_coverage_pct']:.0f}% of dangerous hours")
m[1].metric("Hours ban needlessly stopped safe work", f"{imp['ban_only_safe_hours']:,}")
m[2].metric("AKI cases averted vs ban", f"{imp['aki_cases_averted_vs_ban']:.1f}",
            help=f"of {imp['aki_cases_baseline']:.0f} baseline; HeatGuard averts {imp['aki_cases_averted_heatguard']:.1f}")
m[3].metric("Cost per worker", f"${imp['cost_per_worker_usd']:.0f}", help="mostly one-time capital")
st.caption(f"Productivity maintained/raised **{int(imp['productivity_gain_lo']*100)}–{int(imp['productivity_gain_hi']*100)}%** "
           f"(~{imp['productivity_worker_hours_lo']:,.0f}–{imp['productivity_worker_hours_hi']:,.0f} worker-hours). "
           f"Mechanistic AKI model: reduction × baseline × (1 − ban_coverage).")

bt = get_backtest()
st.success(f"✅ Validity backbone — back-test reproduces the Nicaragua (La Isla / Adelante) outcomes: "
           f"AKI reduction {bt['reproduced_aki_reduction']:.0%} (expected {bt['expected_aki_reduction']:.0%}), "
           f"productivity band {bt['productivity_band']}. Passed: {bt['passed']}.")

# ---- business case ---------------------------------------------------------
st.subheader("Business case — why a contractor says yes")
eco = demo["economics"]
e = st.columns(4)
e[0].metric("ROI (headline)", f"{eco['roi_multiple_lo']:.1f}×–{eco['roi_multiple_hi']:.1f}×",
            help="Conservative subset: productivity + recovered safe work + AKI + fines avoided")
e[1].metric("Payback", f"~{eco['payback_days']:.0f} days")
e[2].metric("Program cost", f"${eco['program_cost_usd']:,.0f}")
e[3].metric("Net benefit", f"${eco['net_benefit_lo']:,.0f}–${eco['net_benefit_hi']:,.0f}")
bcol, scol = st.columns(2)
with bcol:
    bd = pd.DataFrame({
        "Benefit": ["Productivity", "Recovered safe work", "AKI averted", "Fines avoided"],
        "USD": [eco["productivity_value_lo"], eco["recovered_safe_work_value"], eco["aki_value"], eco["fines_avoided_value"]],
    }).set_index("Benefit")
    st.bar_chart(bd, height=240)
    st.caption(f"Additional upside **excluded** from the headline: ${eco['death_averted_value']:,.0f} death-risk "
               f"averted + ${eco['turnover_value']:,.0f} turnover. _{eco['assumptions']['note']}_")
with scol:
    sens = pd.DataFrame(demo["sensitivity"])
    sens["Baseline AKI incidence %"] = sens["baseline_aki_incidence"] * 100
    st.line_chart(sens.set_index("Baseline AKI incidence %")[["aki_cases_averted_vs_ban"]], height=240)
    st.caption("AKI cases averted vs the ban across the (uncertain) baseline-incidence assumption — "
               "shown as a range, not a point. Default 10%.")

# ---- compliance ------------------------------------------------------------
st.subheader("Worker protection record")
st.caption("Tamper-evident proof of protection — for the **worker** (their own heat-safety history) "
           "and the **employer** (a fines/liability shield).")
comp = demo["compliance"]["summary"]
cc = st.columns(3)
cc[0].metric("Records", comp["records"])
cc[1].metric("Chain verified", "✓ YES" if comp["verified"] else "✗ NO")
cc[2].caption(f"head hash `{comp['head_hash'][:24]}…`")
priv = comp.get("privacy")
if priv:
    st.caption(f"🔒 **Privacy by design** — {priv['does_not_record']}. Records {priv['records']}.")
with st.expander("View audit records / download CSV"):
    recs = []
    for rec in demo["compliance"]["records"]:
        p = rec["payload"]
        recs.append({
            "seq": rec["seq"], "time": rec["timestamp"][11:16], "signal": p.get("signal"),
            "WBGT": p.get("wbgt_c"), "work_min": p.get("cycle", {}).get("work_min_per_hour"),
            "water": p.get("water_available"), "hash": rec["record_hash"][:12],
        })
    st.dataframe(pd.DataFrame(recs), hide_index=True, width="stretch")
    st.download_button("Download compliance CSV", demo["compliance"]["csv"],
                       file_name=f"{site_key}_compliance.csv", mime="text/csv")

# ---- what-if ---------------------------------------------------------------
st.sidebar.divider()
st.sidebar.subheader("What-if: live decision")
with st.sidebar.form("whatif"):
    tdb = st.slider("Air temp °C", 25, 52, 42)
    rh = st.slider("Humidity %", 5, 90, 25)
    solar = st.slider("Solar W/m²", 0, 1000, 800, 50)
    hour = st.slider("Hour", 0, 23, 12)
    intensity = st.selectbox("Work intensity", [m.value for m in MetabolicCategory], index=3)
    new_worker = st.checkbox("New worker (unacclimatized, day 0)")
    submitted = st.form_submit_button("Decide")
if submitted:
    res = service.decide_one(
        site_key, tdb, rh, solar=solar, hour=hour, intensity=intensity,
        days_on_job=0 if new_worker else 120, acclimatized=not new_worker,
    )
    adv = res["advisory"]
    st.sidebar.markdown(signal_badge(adv["signal"]), unsafe_allow_html=True)
    st.sidebar.write(f"WBGT **{adv['wbgt_c']:.1f}°C** ({adv['wbgt_source']})")
    st.sidebar.write(f"Work {adv['cycle']['work_min_per_hour']} / rest {adv['cycle']['rest_min_per_hour']} min · "
                     f"{adv['hydration']['cups_250ml_per_h']:.1f} cups/h")
    st.sidebar.write(f"Calendar ban: **{'BANNED' if res['banned'] else 'permitted'}**")
    st.sidebar.caption(adv["rationale"])
