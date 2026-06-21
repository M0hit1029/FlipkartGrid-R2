"""
Deployment page - the unified WHERE + WHO + WHEN flow.

Step 1: choose which zones to cover (auto / by station / hand-pick).
Step 2: get the weekly patrol schedule for exactly those zones.

This merges what used to be two pages (Enforcement planner + Patrol scheduler)
into one guided flow, so the relationship is obvious: pick zones -> get their roster.
"""
from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from common import load, section_label
from schedule import DOW_NAMES, roster
from simulate import (allocate_by_station, evaluate_selection, plan,
                      station_summary, with_impact, zones_to_cover)

ZT = Path(__file__).resolve().parents[2] / "data" / "zone_time.parquet"
_, hx = load()
HAS_ROAD = "road_class" in hx.columns
HAS_POI = "poi_category" in hx.columns


@st.cache_data
def load_zt():
    return pd.read_parquet(ZT) if ZT.exists() else None


zt = load_zt()

st.title("Deployment")
st.caption("Plan enforcement in two steps: pick the zones to cover, then get the "
           "weekly patrol schedule for exactly those zones.")

st.html(
    """
    <div style="display:flex;gap:10px;margin:2px 0 14px 0;flex-wrap:wrap;">
      <div style="flex:1;min-width:230px;background:rgba(255,90,95,0.08);
           border:1px solid rgba(255,90,95,0.30);border-radius:12px;padding:10px 14px;">
        <b style="color:#ff7a6e;">Step 1 &middot; WHERE &amp; WHO</b><br>
        <span style="color:#9aa0b4;font-size:0.86rem;">
        Choose which zones to cover and who deploys.</span></div>
      <div style="flex:1;min-width:230px;background:rgba(255,138,76,0.08);
           border:1px solid rgba(255,138,76,0.30);border-radius:12px;padding:10px 14px;">
        <b style="color:#ff8a4c;">Step 2 &middot; WHEN</b><br>
        <span style="color:#9aa0b4;font-size:0.86rem;">
        Get the day-and-time roster for those zones.</span></div>
    </div>
    """
)

# shared setting
with st.sidebar:
    st.markdown("### Deployment settings")
    section_label("Enforcement effectiveness")
    eff = st.slider("Enforcement effectiveness", 0.2, 0.95, 0.6, step=0.05,
                    label_visibility="collapsed",
                    help="Share of a covered zone's violations enforcement deters.")
    st.caption(f"Assuming **{int(eff*100)}%** deterrence per covered zone.")
    st.divider()
    st.metric("Zones holding 50% of impact", f"{zones_to_cover(hx, 0.5)}")


# ---------- shared helpers ----------
def kpi_row(p):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Zones to cover", f"{p['n_zones']}",
              help=f"out of {p['total_zones']:,} hotspots")
    c2.metric("Stations involved", f"{p['n_stations']}")
    c3.metric("Congestion impact addressed", f"{p['impact_share_addressed']*100:.1f}%")
    c4.metric("Violations deterred", f"~{p['viol_deterred']:,}")


def zone_map(selected_h3, height=300):
    d = with_impact(hx).copy()
    d["sel"] = d.h3.isin(set(selected_h3))
    d["r"] = d.sel.map({True: 255, False: 70})
    d["g"] = d.sel.map({True: 70, False: 80})
    d["b"] = d.sel.map({True: 60, False: 95})
    d["a"] = d.sel.map({True: 225, False: 80})
    mx = d.loc[d.sel, "impact"].max() if d.sel.any() else 1
    d["elev"] = (d.impact / (mx or 1) * 4000).where(d.sel, 0)
    layer = pdk.Layer("H3HexagonLayer", d, get_hexagon="h3",
                      get_fill_color="[r, g, b, a]", get_elevation="elev",
                      extruded=True, pickable=True, coverage=0.9, auto_highlight=True)
    tooltip = {"html": "<b>Rank #{rank} - CIS {CIS}</b><br/>{violations} violations"
                       "<br/>{top_station}",
               "style": {"backgroundColor": "#1a1d29", "color": "#fff"}}
    st.pydeck_chart(pdk.Deck(layers=[layer], map_style="dark", tooltip=tooltip,
                    initial_view_state=pdk.ViewState(
                        latitude=12.972, longitude=77.594, zoom=10.8,
                        pitch=50, bearing=12)),
                    use_container_width=True, height=height)
    st.html('<div class="legend">'
            '<span style="background:#ff4640;color:#fff;">covered</span>'
            '<span style="background:#46505f;color:#fff;">not covered</span></div>')


def plan_table(sel):
    cols = ["rank", "CIS", "violations", "top_violation", "top_station", "peak_daypart"]
    if HAS_POI:
        cols.insert(4, "poi_category")
    t = sel[cols].copy()
    return t.rename(columns={"top_violation": "violation", "top_station": "station",
                             "peak_daypart": "peak", "poi_category": "driver"})


# =================================================================== STEP 1 ==
st.header("Step 1 · Choose the zones to cover")
strategy = st.radio(
    "How should the zones be chosen?",
    ["Top priority (auto)", "By police station", "Hand-pick zones"],
    horizontal=True,
    help="Auto = best zones city-wide. By station = jurisdiction-aware. "
         "Hand-pick = full manual control.")

if strategy == "Top priority (auto)":
    st.caption("The model picks the highest-impact zones across the whole city.")
    cap = st.slider("How many zones can you cover?", 5, 300, 40, step=5)
    p = plan(hx, cap, eff)

elif strategy == "By police station":
    st.caption("Allocate patrols per station; each station gets its own worst zones.")
    ss = station_summary(hx)
    with st.expander("Station leaderboard (impact in each jurisdiction)", expanded=False):
        lead = ss[["station", "zones", "critical_zones", "violations", "impact",
                   "impact_share"]].copy()
        lead["impact"] = lead["impact"].round(0).astype(int)
        lead["violations"] = lead["violations"].astype(int)
        st.dataframe(lead, hide_index=True, use_container_width=True, height=260,
                     column_config={"impact_share": st.column_config.ProgressColumn(
                         "share of city impact", min_value=0.0,
                         max_value=float(lead.impact_share.max()), format="%.1f%%")})
    cc1, cc2 = st.columns(2)
    chosen = cc1.multiselect("Stations to mobilise", ss.station.tolist(),
                             default=ss.station.head(5).tolist())
    per = cc2.slider("Patrols (zones) per station", 1, 20, 5)
    p = allocate_by_station(hx, {s: per for s in chosen}, eff)

else:  # hand-pick
    st.caption("Hand-pick the exact zones - e.g. for an event or VIP route.")
    d = with_impact(hx).sort_values("impact", ascending=False).reset_index(drop=True)
    sf = st.multiselect("Filter the picker by station (optional)",
                        sorted(d.top_station.unique()))
    pool = (d[d.top_station.isin(sf)] if sf else d).copy()
    pool["label"] = ("#" + pool["rank"].astype(str) + " - CIS " + pool.CIS.astype(str)
                     + " - " + pool.top_station + " - " + pool.top_violation)
    l2h = dict(zip(pool.label, pool.h3))
    picks = st.multiselect("Zones to cover", pool.label.tolist(),
                           default=pool.label.head(10).tolist())
    p = evaluate_selection(hx, [l2h[l] for l in picks], eff) if picks else None

if not p or p["n_zones"] == 0:
    st.warning("Select at least one zone to continue.")
    st.stop()

sel = p["selected"]
selected_h3 = sel.h3.tolist()

kpi_row(p)
msg = (f"Covering **{p['n_zones']} zones** across **{p['n_stations']} stations** "
       f"targets **{p['impact_share_addressed']*100:.0f}%** of city congestion "
       f"impact (~{p['viol_deterred']:,} violations deterred).")
if "efficiency_vs_optimal" in p:
    msg += (f" That's **{p['efficiency_vs_optimal']*100:.0f}%** of the best possible "
            f"{p['n_zones']}-zone plan.")
st.success(msg)

m1, m2 = st.columns([2, 3], gap="large")
with m1:
    zone_map(selected_h3)
with m2:
    st.dataframe(plan_table(sel), hide_index=True, use_container_width=True, height=330)

# =================================================================== STEP 2 ==
st.divider()
st.header("Step 2 · When to patrol these zones")

if zt is None:
    st.warning("Run `python src/schedule.py` to build the demand model, then reload.")
    st.stop()

schedulable = [h for h in selected_h3 if h in set(zt.h3.unique())]
if not schedulable:
    st.warning("None of the chosen zones have enough history for a time forecast. "
               "Pick higher-ranked zones (the forecast covers the top 300 by CIS).")
    st.stop()
if len(schedulable) < len(selected_h3):
    st.caption(f"Note: {len(selected_h3) - len(schedulable)} of your "
               f"{len(selected_h3)} zones lack enough history to forecast; "
               f"scheduling the remaining {len(schedulable)}.")

st.caption("The schedule below is built ONLY from the zones you chose in Step 1.")

zt_sel = zt[zt.h3.isin(schedulable)]
s1, s2 = st.columns([2, 3], gap="large")
with s1:
    ppd = st.slider("Patrols per day", 1, 15, min(5, len(schedulable)))
    st.caption("When your chosen zones are hot:")
    city = zt_sel.groupby(["dow_name", "hour"])["expected"].sum().reset_index()
    heat = alt.Chart(city).mark_rect().encode(
        x=alt.X("hour:O", title="Hour (IST)"),
        y=alt.Y("dow_name:N", sort=DOW_NAMES, title=None),
        color=alt.Color("expected:Q", title="Exp.", scale=alt.Scale(scheme="inferno")),
        tooltip=["dow_name", "hour", alt.Tooltip("expected:Q", format=".1f")],
    ).properties(height=210)
    st.altair_chart(heat, use_container_width=True)

r = roster(zt, hx, patrols_per_day=ppd, zones=schedulable)
with s2:
    st.caption("Roster grid - zone ranks to patrol each day & window:")
    grid = (r.assign(cell=r["rank"].apply(lambda x: f"#{x}"))
            .groupby(["day", "window"])["cell"]
            .apply(lambda s: ", ".join(s)).reset_index())
    pivot = grid.pivot(index="day", columns="window", values="cell").reindex(DOW_NAMES)
    order = [c for c in ["Morning peak", "Midday", "Evening peak", "Night"]
             if c in pivot.columns]
    st.dataframe(pivot[order].fillna("-"), use_container_width=True, height=300)

st.success(f"**{len(r)} patrol assignments** this week ({ppd}/day), targeting "
           f"~**{r.exp_violations.sum():.0f} expected violations** in your chosen zones.")
st.caption("Full roster (priority order within each day):")
st.dataframe(r, hide_index=True, use_container_width=True, height=300)
st.download_button("Download deployment roster (CSV)",
                   r.to_csv(index=False).encode("utf-8"),
                   file_name=f"deployment_roster_{ppd}per_day.csv", mime="text/csv")
