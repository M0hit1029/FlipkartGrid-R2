"""Dashboard page - map, KPIs, ranked zones, drill-down, charts (with explanations)."""
import pandas as pd
import pydeck as pdk
import streamlit as st

from common import DAYPARTS, load, section_label

df, hx = load()
HAS_ROAD = "road_class" in hx.columns
HAS_POI = "poi_category" in hx.columns

st.title("Parking Congestion Intelligence - Bengaluru")
st.caption(
    "Detecting illegal-parking hotspots and scoring their impact on traffic flow, "
    "to shift enforcement from reactive patrols to targeted zones. "
    "Source: traffic-police parking violations, Nov 2023 - Apr 2024."
)

# ---- onboarding / how to read it ----
with st.expander("New here? How to read this dashboard", expanded=False):
    st.markdown(
        """
**The goal:** find *where* illegal parking hurts traffic the most, so police can
prioritise those spots instead of patrolling blindly.

- **The 3D map** splits the city into ~150 m hexagons. **Taller, redder hexagons
  = worse congestion impact.** Drag to rotate, scroll to zoom, hover for details.
- **CIS (Congestion Impact Score, 0-100)** ranks every hexagon. It blends *how many*
  violations, *how severe* they are, *how often they recur*, *whether they sit at
  a junction*, and *how important the road is*. Higher = a more urgent zone.
- **Top enforcement zones** (right) lists the worst hexagons. Pick one in the
  drill-down to see what's happening there and the best time to send a patrol.
- **Filters** (left sidebar) slice everything by violation type, vehicle, time of
  day and weekday/weekend.

See the **"How it works"** page (sidebar) for the full methodology.
        """
    )

# ---------------- sidebar filters ----------------
vtypes = sorted(df.primary_violation.unique())
veh = sorted(df.vehicle_type.dropna().unique())

with st.sidebar:
    st.markdown("### Filters")
    st.caption("Slice the map, KPIs and charts below.")

    section_label("Violation type")
    sel_v = st.multiselect("Violation type", vtypes, default=vtypes,
                           label_visibility="collapsed",
                           placeholder="All violation types")

    section_label("Vehicle type")
    sel_veh = st.multiselect("Vehicle type", veh, default=veh,
                             label_visibility="collapsed",
                             placeholder="All vehicle types")

    section_label("Time of day (IST)")
    sel_dp = st.pills("Time of day", DAYPARTS, default=DAYPARTS,
                      selection_mode="multi", label_visibility="collapsed")
    sel_dp = sel_dp or DAYPARTS  # empty = no filter

    section_label("Days")
    wk = st.segmented_control("Days", ["All", "Weekday", "Weekend"],
                              default="All", label_visibility="collapsed")
    wk = wk or "All"

    section_label("Hotspots on map")
    topn = st.slider("Hotspots to show on map", 10, 300, 75, step=5,
                     label_visibility="collapsed",
                     help="How many of the highest-CIS hexagons to render and rank.")
    st.caption(f"Showing top **{topn}** zones.")

f = df[
    df.primary_violation.isin(sel_v)
    & df.vehicle_type.isin(sel_veh)
    & df.daypart.isin(sel_dp)
]
if wk == "Weekday":
    f = f[~f.is_weekend]
elif wk == "Weekend":
    f = f[f.is_weekend]

# ---------------- KPIs ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Violations (filtered)", f"{len(f):,}",
          help="Number of parking violations matching the current filters.")
c2.metric("Hotspot cells", f"{len(hx):,}",
          help="Distinct ~150 m hexagons that contain at least one violation.")
c3.metric("Police stations", f"{f.police_station.nunique()}",
          help="Jurisdictions present in the filtered data.")
c4.metric("Critical zones (CIS >= 60)", f"{int((hx.CIS >= 60).sum())}",
          help="Hexagons scoring 60+ on the Congestion Impact Score - high priority.")

left, right = st.columns([3, 2], gap="large")

# ---------------- 3D map ----------------
with left:
    st.subheader("Congestion impact - 3D hotspot map")
    layer_choice = st.radio(
        "Map layer", ["CIS hotspots (3D)", "Raw density hexbin"],
        horizontal=True,
        help="'CIS hotspots' = ranked priority zones. "
             "'Raw density' = where violations simply pile up, no scoring.",
    )

    if layer_choice == "CIS hotspots (3D)":
        top = hx.head(topn).copy()
        vmax = top.CIS.max() or 1
        top["frac"] = top.CIS / vmax
        top["r"] = (60 + 195 * top.frac).astype(int)
        top["g"] = (200 * (1 - top.frac) + 30).astype(int)
        top["b"] = 50
        top["elev"] = top.CIS * 60
        layer = pdk.Layer(
            "H3HexagonLayer", top, get_hexagon="h3",
            get_fill_color="[r, g, b, 200]", get_elevation="elev",
            elevation_scale=1, extruded=True, pickable=True,
            coverage=0.92, auto_highlight=True,
        )
        tooltip = {
            "html": "<b>Rank #{rank} - CIS {CIS}</b><br/>"
                    "{violations} violations<br/>"
                    "{top_violation} - {top_station}<br/>"
                    "Peak: {peak_daypart}",
            "style": {"backgroundColor": "#1a1d29", "color": "#fff"},
        }
        st.markdown(
            '<div class="legend">Impact: '
            '<span style="background:#3fc850;">low</span>'
            '<span style="background:#e0b020;">medium</span>'
            '<span style="background:#ff5a32;">high</span>'
            '&nbsp;- taller = higher CIS</div>',
            unsafe_allow_html=True,
        )
    else:
        pts = f[["latitude", "longitude"]].sample(
            min(len(f), 60000), random_state=1
        ).rename(columns={"latitude": "lat", "longitude": "lng"})
        layer = pdk.Layer(
            "HexagonLayer", pts, get_position="[lng, lat]", radius=120,
            elevation_scale=4, extruded=True, pickable=True, coverage=0.9,
            color_range=[[33, 102, 172], [103, 169, 207], [209, 229, 240],
                         [253, 219, 199], [239, 138, 98], [178, 24, 43]],
        )
        tooltip = {"text": "{elevationValue} violations here"}
        st.caption("Colour/height = raw violation count in each hexagon "
                   "(no severity or junction weighting).")

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(
            latitude=12.972, longitude=77.594, zoom=11.2, pitch=50, bearing=12),
        map_style="dark", tooltip=tooltip,
    )
    st.pydeck_chart(deck, use_container_width=True, height=520)
    st.caption("Drag to rotate - scroll to zoom - hover a hexagon for details.")

# ---------------- ranked table + drill-down ----------------
with right:
    st.subheader("Top enforcement zones")
    st.caption("Worst hexagons by Congestion Impact Score. The bar shows CIS (0-100).")
    tbl = hx.head(topn)[
        ["rank", "CIS", "violations", "top_violation", "top_station", "peak_daypart"]
    ].rename(columns={"top_violation": "violation", "top_station": "station",
                      "peak_daypart": "peak"})
    st.dataframe(
        tbl, hide_index=True, height=240, use_container_width=True,
        column_config={
            "CIS": st.column_config.ProgressColumn(
                "CIS", min_value=0, max_value=100, format="%.1f"),
        },
    )

    st.markdown("**Zone drill-down**")
    st.caption("Pick a rank to see what's driving that zone and when to enforce.")
    pick = st.selectbox("Zone rank", hx.head(topn)["rank"].tolist(),
                        label_visibility="collapsed")
    z = hx[hx["rank"] == pick].iloc[0]
    road_line = f"\n- **Road class:** {z.road_class}" if HAS_ROAD else ""
    if HAS_POI and z.poi_category != "General on-street":
        name = f" ({z.poi_name})" if z.poi_name not in ("-", None) else ""
        driver_line = f"\n- **Likely driver:** {z.poi_category}{name}, {int(z.poi_dist_m)} m away"
    elif HAS_POI:
        driver_line = "\n- **Likely driver:** General on-street (no major POI nearby)"
    else:
        driver_line = ""
    st.markdown(
        f"""
- **Congestion Impact Score:** `{z.CIS}`  (rank #{int(z['rank'])} of {len(hx):,})
- **Violations:** {int(z.violations):,} across {int(z.active_days)} distinct days
- **Dominant violation:** {z.top_violation}
- **Top vehicle:** {z.top_vehicle}
- **Police station:** {z.top_station}
- **At / near a junction:** {z.at_junction*100:.0f}% of cases{road_line}{driver_line}
- **Recommended enforcement window:** **{z.peak_daypart}**
"""
    )

st.divider()
cc1, cc2 = st.columns(2)
with cc1:
    st.subheader("Violations by hour (IST)")
    st.caption("When in the day violations are logged - drives patrol timing.")
    st.bar_chart(f.groupby("hour").size())
with cc2:
    st.subheader("Violation mix")
    st.caption("Which violation types dominate the current selection.")
    st.bar_chart(f.primary_violation.value_counts())

if HAS_POI:
    st.divider()
    st.subheader("What's driving these hotspots?")
    st.caption(f"Likely cause of the top {topn} zones - each hotspot tagged with the "
               "nearest metro / market / school / hospital / event venue (OSM).")
    drivers = hx.head(topn).poi_category.value_counts()
    dc1, dc2 = st.columns([3, 2], gap="large")
    with dc1:
        st.bar_chart(drivers)
    with dc2:
        near = int((hx.head(topn).poi_category != "General on-street").sum())
        st.metric("Top zones near a known driver", f"{near} / {topn}",
                  help="Hotspots within 250 m of a metro, market, school, "
                       "hospital, bus or event venue.")
        st.caption("These are the categories the problem statement targets: "
                   "commercial areas, transit, and event/institution draws.")
