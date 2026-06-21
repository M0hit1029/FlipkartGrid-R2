"""
Phase 2/3 - Hotspot detection + Congestion Impact Score (CIS).

Input : data/clean.parquet
Output: data/hotspots.parquet   (one row per H3 cell with violations)
        output/top_zones.csv     (ranked enforcement zones, human-readable)

Method
------
1. Bin every violation into an H3 hexagon (~150 m edge, res 9).
2. For each cell aggregate volume, severity, persistence, junction signal.
3. Combine into a single 0-100 Congestion Impact Score so zones are rankable.

Why a composite score?
The raw CSV has NO live traffic feed, so "impact on traffic flow" is modelled
from proxies that are known to choke carriageways:
  - SEVERITY  : footpath / main-road / near-crossing parking hurts flow most
  - VOLUME    : more violations = more chronic obstruction
  - PERSISTENCE: recurring across many distinct days = systemic, not one-off
  - JUNCTION  : violations at/near tagged junctions hit intersection throughput
"""
from pathlib import Path

import h3
import numpy as np
import pandas as pd

CLEAN = Path(__file__).resolve().parents[1] / "data" / "clean.parquet"
OUT_HEX = Path(__file__).resolve().parents[1] / "data" / "hotspots.parquet"
OUT_CSV = Path(__file__).resolve().parents[1] / "output" / "top_zones.csv"

H3_RES = 9  # ~150 m hex edge -> street-block granularity

# Weights for the composite CIS (sum = 1.0). Tunable.
W_VOLUME = 0.35
W_SEVERITY = 0.30
W_PERSISTENCE = 0.20
W_JUNCTION = 0.15


def latlng_to_cell(lat, lng):
    # h3 v4 renamed the function; support both.
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lng, H3_RES)
    return h3.geo_to_h3(lat, lng, H3_RES)


def cell_to_latlng(cell):
    if hasattr(h3, "cell_to_latlng"):
        return h3.cell_to_latlng(cell)
    return h3.h3_to_geo(cell)


def minmax(s):
    """Scale a series to 0..1; flat series -> 0."""
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.0, index=s.index)
    return (s - lo) / (hi - lo)


def main():
    df = pd.read_parquet(CLEAN)
    print(f"Loaded {len(df):,} violations")

    df["h3"] = [latlng_to_cell(la, lo) for la, lo in zip(df.latitude, df.longitude)]

    def top_mode(s):
        m = s.mode()
        return m.iloc[0] if len(m) else None

    g = df.groupby("h3")
    agg = g.agg(
        violations=("id", "count"),
        mean_severity=("severity", "mean"),
        max_severity=("severity", "max"),
        active_days=("date", "nunique"),
        active_hours=("hour", "nunique"),
        at_junction=("junction_name", lambda s: (s != "No Junction").mean()),
        top_violation=("primary_violation", top_mode),
        top_vehicle=("vehicle_type", top_mode),
        top_station=("police_station", top_mode),
        peak_hour=("hour", top_mode),
        peak_daypart=("daypart", top_mode),
    ).reset_index()

    # centroid of each hex for mapping
    cents = [cell_to_latlng(c) for c in agg.h3]
    agg["lat"] = [c[0] for c in cents]
    agg["lng"] = [c[1] for c in cents]

    # --- component scores (0..1) ---
    # log-scale volume so a few mega-cells don't flatten everything else
    agg["s_volume"] = minmax(np.log1p(agg.violations))
    agg["s_severity"] = minmax(agg.mean_severity)
    agg["s_persistence"] = minmax(np.log1p(agg.active_days))
    agg["s_junction"] = agg.at_junction.clip(0, 1)

    agg["CIS"] = 100 * (
        W_VOLUME * agg.s_volume
        + W_SEVERITY * agg.s_severity
        + W_PERSISTENCE * agg.s_persistence
        + W_JUNCTION * agg.s_junction
    )
    agg["CIS"] = agg.CIS.round(1)
    agg = agg.sort_values("CIS", ascending=False).reset_index(drop=True)
    agg["rank"] = agg.index + 1

    OUT_HEX.parent.mkdir(parents=True, exist_ok=True)
    agg.to_parquet(OUT_HEX, index=False)

    # human-readable top-50 enforcement zones
    cols = [
        "rank", "CIS", "lat", "lng", "violations", "active_days",
        "top_violation", "top_vehicle", "top_station", "peak_daypart",
        "at_junction",
    ]
    top = agg[cols].head(50).copy()
    top["at_junction"] = (top.at_junction * 100).round(0).astype(int).astype(str) + "%"
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    top.to_csv(OUT_CSV, index=False)

    print(f"\n{len(agg):,} hotspot cells written -> {OUT_HEX}")
    print(f"Top-50 enforcement zones -> {OUT_CSV}\n")
    print("==== TOP 10 ENFORCEMENT ZONES ====")
    show = top.head(10)[["rank", "CIS", "violations", "top_violation",
                         "top_station", "peak_daypart", "at_junction"]]
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
