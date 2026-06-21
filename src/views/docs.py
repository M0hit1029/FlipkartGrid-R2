"""How it works - methodology & glossary page."""
import streamlit as st

from common import load

df, hx = load()

st.title("How it works")
st.caption("Methodology, scoring model and glossary behind the dashboard.")

st.header("The problem")
st.markdown(
    """
On-street **illegal and spillover parking** near commercial areas, metro stations
and events chokes carriageways and intersections. Today enforcement is
**patrol-based and reactive** - there's no heatmap of violations vs. their
congestion impact, so it's hard to know *which* zones to prioritise.

**Our question:** can we use parking-violation data to detect illegal-parking
hotspots and **quantify their impact on traffic flow**, so enforcement can be
targeted at the spots that hurt the most?
    """
)

st.header("The data")
col1, col2, col3 = st.columns(3)
col1.metric("Violation records", f"{len(df):,}")
col2.metric("Hotspot hexagons", f"{len(hx):,}")
col3.metric("Date range", "Nov 2023 - Apr 2024")
st.markdown(
    """
Each record is one traffic-police parking violation with: **GPS location**,
**violation type(s)** (wrong parking, no parking, parking on a main road / footpath /
near a crossing...), **vehicle type**, **timestamp**, **police station** and
**junction** tag. There is **no direct traffic-speed feed** - so congestion impact
has to be *modelled*, which is what the CIS below does.
    """
)

st.header("Pipeline")
st.markdown(
    """
1. **Clean & parse** (`clean.py`) - validate GPS to the Bengaluru area, parse the
   violation-type list, pick the most-severe "primary" violation, convert
   timestamps to IST and derive hour / day / day-part features.
2. **Hotspot detection** (`hotspots.py`) - bin every violation into a **~150 m H3
   hexagon** and aggregate volume, severity, recurrence and junction signal.
3. **Road-network weighting** (`roads.py`, optional) - tag each hexagon with the
   class of road it sits on (arterial / primary / residential) from OpenStreetMap,
   so violations on busy narrow roads score higher.
4. **Score & rank** - combine those into the **Congestion Impact Score (CIS)**.
5. **POI driver analysis** (`poi.py`) - tag each hexagon with the nearest metro /
   market / school / hospital / bus / event venue from OSM, so each hotspot has a
   likely *cause*, not just a location.
6. **Deployment engines** (`simulate.py` + `schedule.py`) - pick which zones to
   cover (and recover) and forecast *when* to patrol each one as a weekly roster.
7. **Dashboard** (`app.py`) - explore hotspots, then plan deployment end to end.
    """
)

st.header("Deployment: where, who and when")
st.markdown(
    """
The **Deployment** page turns the analysis into an actual plan in two chained steps -
Step 2 always schedules exactly the zones picked in Step 1, so there's a single,
unambiguous flow.

**Step 1 - WHERE & WHO (which zones to cover).** Three strategies, all picking by
*impact* (= violations x CIS / 100):

- **Top priority (auto)** - the highest-impact zones across the whole city.
- **By police station** - allocate patrols per station; each station gets its own
  worst zones (jurisdiction-aware). Includes a station leaderboard.
- **Hand-pick** - choose exact zones (e.g. for an event or VIP route); the tool
  shows how your selection compares to the optimal same-size plan.

Each strategy reports the **congestion impact addressed** and **violations deterred**
at a tunable enforcement-effectiveness level.

**Step 2 - WHEN (the weekly roster).** For the chosen zones we forecast demand by
**weekday x hour** from history, with **empirical-Bayes shrinkage** toward the
city-wide pattern so sparse zones don't overfit a few records:
    """
)
st.latex(
    r"expected = \frac{count + \alpha \cdot city\_rate}{n_{weekdays} + \alpha}"
)
st.markdown(
    "A greedy scheduler assigns a fixed number of daily patrols to the "
    "highest-expected-demand `(zone, day, window)` cells, producing a ready-to-issue "
    "**weekly roster** (downloadable as CSV). The recorded timestamps skew to "
    "early-day hours, so the *timing* is a data-driven starting roster to validate "
    "operationally, not ground truth."
)

st.header("Why each hotspot exists (POI drivers)")
st.markdown(
    """
The problem statement names the real causes of spillover parking: **commercial
areas, metro stations and events**. We pull those points of interest from
OpenStreetMap and tag every hotspot with its **nearest driver within 250 m** -
metro / transit, market / mall, school / college, hospital, bus station or event
venue. About **70%+ of hotspots** sit next to one of these, which turns an
anonymous dot into an actionable explanation (e.g. *"this zone is driven by a
metro station 90 m away"*) and points to longer-term fixes (sanctioned parking,
pickup bays) beyond enforcement.
    """
)

st.header("Congestion Impact Score (CIS)")
st.markdown(
    "For each hexagon, signals (each scaled 0-1) are blended into a single "
    "0-100 score so zones are directly comparable and rankable:"
)
st.latex(
    r"CIS = 100 \times (0.30\,\text{Volume} + 0.28\,\text{Severity} + "
    r"0.18\,\text{Persistence} + 0.12\,\text{Junction} + 0.12\,\text{Road class})"
)
st.caption(
    "When road-network weighting has not been run, the road-class term is dropped "
    "and the remaining four weights are renormalised."
)
st.table(
    {
        "Component": ["Volume", "Severity", "Persistence", "Junction", "Road class"],
        "What it captures": [
            "How many violations occur (log-scaled so a few mega-spots don't flatten the rest).",
            "Average traffic-blocking severity of the violation types present.",
            "How many distinct days the spot recurs - chronic vs. one-off.",
            "Share of violations sitting at / near a tagged junction.",
            "Importance of the road the hexagon sits on (arterial > primary > local).",
        ],
    }
)
st.markdown("**Severity weights** (how much each violation type chokes flow):")
st.table(
    {
        "Violation type": [
            "Parking near road crossing", "Parking in a main road",
            "Parking on footpath", "Wrong parking", "No parking",
        ],
        "Severity (1-5)": [5, 5, 4, 3, 2],
        "Why": [
            "Blocks turning movements at the most sensitive point.",
            "Directly removes a live carriageway lane.",
            "Forces pedestrians onto the road.",
            "Obstructs but usually off the main flow.",
            "Restricted zone, lower direct flow impact.",
        ],
    }
)

st.header("How to use it for enforcement")
st.markdown(
    """
1. **Explore** the hotspots on the **Dashboard** - filter by violation, vehicle and
   time to understand the problem.
2. On the **Deployment** page, **Step 1**: choose which zones to cover (auto, by
   station, or hand-picked) and see the impact you'd address.
3. **Step 2**: download the **weekly roster** telling each team which zone to patrol
   on which day and time window.
4. **Track** the same map month-over-month to see whether enforcement moved the needle.
    """
)

st.header("Glossary")
st.markdown(
    """
- **H3 hexagon** - Uber's hexagonal grid system; we use resolution 9 (~150 m edge)
  so each cell is roughly a street block.
- **CIS** - Congestion Impact Score, 0-100. The headline ranking metric.
- **Primary violation** - when a record has several violations, the single most
  severe one, used for colouring and severity.
- **Day-part (IST)** - Morning peak (7-11), Midday (11-16), Evening peak (16-21),
  Night (21-7).
- **Road class** - OpenStreetMap highway tag (motorway / trunk / primary /
  secondary / tertiary / residential), mapped to an importance weight.
    """
)

st.header("Honest caveats")
st.info(
    "CIS is a **proxy** model - without a live speed/flow feed, impact is inferred "
    "from violation characteristics, not measured directly.\n\n"
    "Recorded timestamps skew to early-day hours; the **time-of-day** recommendation "
    "should be validated with the police before operational use. Spatial ranking is "
    "unaffected.\n\n"
    "The **Deployment** page's recovery numbers assume a fixed deterrence "
    "effectiveness per covered zone; treat them as planning estimates, not measured "
    "traffic outcomes."
)
