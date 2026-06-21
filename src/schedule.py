"""
Phase 7 - Predictive patrol scheduler ("AI-driven" piece).

Detection tells you WHERE to enforce. This tells you WHEN, per zone, and turns it
into a concrete weekly patrol roster.

Idea
----
For every hotspot we learn its temporal demand pattern from history - how
violations distribute across day-of-week x hour - and forecast the expected
violations in each future time slot. A greedy scheduler then assigns a limited
number of daily patrols to the highest-expected-demand (zone, day, time-window)
cells, producing a ready-to-issue weekly roster.

Forecast model
--------------
Expected violations for a zone in a given (weekday, hour) slot =

    expected = (count + a * city_rate) / (n_weekdays + a)

i.e. the zone's own historical rate for that slot, smoothed (empirical-Bayes
shrinkage, a = SMOOTH) toward the city-wide rate for that slot so sparse zones
borrow strength from the global pattern instead of overfitting a few records.

Input : data/clean.parquet, data/hotspots.parquet
Output: data/zone_time.parquet     (per-zone weekday x hour expected demand)
        output/patrol_roster.csv    (example weekly roster, 5 patrols/day)

Run:  python src/schedule.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean.parquet"
HEX = ROOT / "data" / "hotspots.parquet"
ZT = ROOT / "data" / "zone_time.parquet"
ROSTER = ROOT / "output" / "patrol_roster.csv"

TOP_N = 300       # build the schedule pool from the top-N zones by CIS
SMOOTH = 4.0      # empirical-Bayes shrinkage strength
H3_RES = 9

DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAYPARTS = [("Morning peak", 7, 11), ("Midday", 11, 16),
            ("Evening peak", 16, 21), ("Night", 21, 31)]  # 21-07 wraps


def latlng_to_cell(lat, lng):
    import h3
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lng, H3_RES)
    return h3.geo_to_h3(lat, lng, H3_RES)


def daypart_of(hour):
    for name, lo, hi in DAYPARTS:
        if lo <= hour < hi or (name == "Night" and (hour >= 21 or hour < 7)):
            return name
    return "Night"


def build_zone_time():
    df = pd.read_parquet(CLEAN)
    hot = pd.read_parquet(HEX).sort_values("CIS", ascending=False).head(TOP_N)
    top_set = set(hot.h3)

    print(f"Tagging {len(df):,} violations to H3 cells...")
    df["h3"] = [latlng_to_cell(la, lo) for la, lo in zip(df.latitude, df.longitude)]
    df = df[df.h3.isin(top_set)].copy()
    print(f"  {len(df):,} violations fall in the top {TOP_N} zones")

    # how many of each weekday appear in the full window (e.g. ~22 Mondays)
    alldates = pd.read_parquet(CLEAN)[["date", "dow"]].drop_duplicates("date")
    n_weekday = alldates.groupby("dow").size()  # index 0..6

    # city-wide average violations per (dow,hour) per zone -> shrinkage prior
    cnt = df.groupby(["h3", "dow", "hour"]).size().rename("count").reset_index()
    city_rate = (df.groupby(["dow", "hour"]).size() /
                 (len(top_set))).rename("city_count").reset_index()
    cnt = cnt.merge(city_rate, on=["dow", "hour"], how="left")
    cnt["n_wd"] = cnt["dow"].map(n_weekday)
    cnt["city_rate"] = cnt["city_count"] / cnt["n_wd"]
    cnt["expected"] = ((cnt["count"] + SMOOTH * cnt["city_rate"]) /
                       (cnt["n_wd"] + SMOOTH)).round(3)

    cnt["dow_name"] = cnt["dow"].map(dict(enumerate(DOW_NAMES)))
    cnt["daypart"] = cnt["hour"].map(daypart_of)
    out = cnt[["h3", "dow", "dow_name", "hour", "daypart", "count", "expected"]]
    out.to_parquet(ZT, index=False)
    print(f"Wrote {len(out):,} (zone,day,hour) demand rows -> {ZT.name}")
    return out


def roster(zone_time: pd.DataFrame, hot: pd.DataFrame, patrols_per_day: int,
           stations=None, zones=None) -> pd.DataFrame:
    """Assign `patrols_per_day` patrols each day to the top expected-demand cells.

    zones    : optional iterable of h3 ids to restrict scheduling to (e.g. the
               zones chosen in the deployment step).
    stations : optional list of station names to restrict to.
    """
    meta = hot.set_index("h3")
    zt = zone_time.copy()
    if zones is not None:
        zt = zt[zt.h3.isin(set(zones))]
    if stations:
        keep = set(meta[meta.top_station.isin(stations)].index)
        zt = zt[zt.h3.isin(keep)]
    # expected demand per (zone, day, daypart) = sum of hourly expecteds
    cell = (zt.groupby(["h3", "dow", "dow_name", "daypart"])["expected"]
            .sum().reset_index())
    rows = []
    for dow in range(7):
        day = cell[cell.dow == dow].sort_values("expected", ascending=False)
        # one patrol per (zone,daypart); avoid sending two patrols to same slot
        day = day.head(patrols_per_day)
        rows.append(day)
    plan = pd.concat(rows, ignore_index=True)
    plan["station"] = plan.h3.map(meta.top_station)
    plan["CIS"] = plan.h3.map(meta.CIS)
    plan["rank"] = plan.h3.map(meta["rank"]).astype(int)
    if "poi_category" in meta.columns:
        plan["driver"] = plan.h3.map(meta.poi_category)
    plan["expected"] = plan.expected.round(1)
    plan = plan.sort_values(["dow", "expected"], ascending=[True, False])
    cols = ["dow_name", "daypart", "rank", "CIS", "station", "expected"]
    if "driver" in plan.columns:
        cols.append("driver")
    return plan[cols].rename(columns={"dow_name": "day", "daypart": "window",
                                      "expected": "exp_violations"})


def main():
    zt = build_zone_time()
    hot = pd.read_parquet(HEX)
    r = roster(zt, hot, patrols_per_day=5)
    ROSTER.parent.mkdir(parents=True, exist_ok=True)
    r.to_csv(ROSTER, index=False)
    print(f"\nExample weekly roster (5 patrols/day) -> {ROSTER.name}")
    print(f"  {len(r)} patrol assignments across the week\n")
    print(r.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
