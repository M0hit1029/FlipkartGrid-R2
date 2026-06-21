"""
Phase 4 - Road-network weighting (OpenStreetMap).

Augments each hotspot hexagon with the class of road it sits on, then folds a
"road class" term into the Congestion Impact Score. The intuition: the same
illegal parking chokes traffic far more on an arterial/main road than on a quiet
residential lane, so impact should be weighted by road importance.

Input : data/hotspots.parquet   (from hotspots.py)
Output: data/hotspots.parquet   (overwritten, now with road_class + new CIS)
        data/roads_cache.graphml (cached OSM network, so we only download once)
        output/top_zones.csv     (refreshed)

Method
------
1. Download Bengaluru's drivable road network from OSM (cached locally).
2. For each hexagon centroid, find the nearest road edge and read its highway tag.
3. Map highway tag -> importance weight (motorway/trunk high, residential low).
4. Recompute CIS with a 5th component and renormalised weights.

Run:  python src/roads.py
If OSM is unreachable, the dashboard still works on the 4-component CIS.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HEX = ROOT / "data" / "hotspots.parquet"
GRAPH_CACHE = ROOT / "data" / "roads_cache.graphml"
OUT_CSV = ROOT / "output" / "top_zones.csv"

# Bengaluru bbox (lat/lng) - matches clean.py
NORTH, SOUTH, EAST, WEST = 13.16, 12.80, 77.78, 77.44

# OSM highway tag -> (display label, importance weight 0..1)
ROAD_WEIGHT = {
    "motorway": 1.00, "motorway_link": 0.95,
    "trunk": 0.95, "trunk_link": 0.90,
    "primary": 0.85, "primary_link": 0.80,
    "secondary": 0.65, "secondary_link": 0.60,
    "tertiary": 0.45, "tertiary_link": 0.42,
    "unclassified": 0.30,
    "residential": 0.25, "living_street": 0.20,
    "service": 0.15,
}
DEFAULT_ROAD_W = 0.30  # unknown / missing tag

ROAD_LABEL = {
    "motorway": "Expressway", "trunk": "Major arterial",
    "primary": "Arterial", "secondary": "Sub-arterial",
    "tertiary": "Collector", "unclassified": "Minor road",
    "residential": "Residential", "living_street": "Local street",
    "service": "Service road",
}

# CIS weights WITH road class (sum = 1.0)
W = {"volume": 0.30, "severity": 0.28, "persistence": 0.18,
     "junction": 0.12, "road": 0.12}


def minmax(s):
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.0, index=s.index)
    return (s - lo) / (hi - lo)


def base_highway(val):
    """OSM 'highway' can be a list; take the first / most important token."""
    if isinstance(val, list):
        val = val[0] if val else None
    return str(val) if val is not None else None


def load_graph(ox):
    if GRAPH_CACHE.exists():
        print(f"Loading cached road network: {GRAPH_CACHE.name}")
        return ox.load_graphml(GRAPH_CACHE)
    print("Downloading Bengaluru drive network from OSM (one-time, ~1-3 min)...")
    # osmnx v1/v2 differ in bbox signature; try both.
    try:
        G = ox.graph_from_bbox(bbox=(WEST, SOUTH, EAST, NORTH), network_type="drive")
    except TypeError:
        G = ox.graph_from_bbox(NORTH, SOUTH, EAST, WEST, network_type="drive")
    ox.save_graphml(G, GRAPH_CACHE)
    print(f"  cached -> {GRAPH_CACHE.name}")
    return G


def main():
    try:
        import osmnx as ox
    except ImportError:
        raise SystemExit("osmnx not installed. Run: pip install osmnx")

    hx = pd.read_parquet(HEX)
    print(f"Loaded {len(hx):,} hotspot hexagons")

    G = load_graph(ox)
    _, edges = ox.graph_to_gdfs(G)

    # nearest edge for every hexagon centroid
    print("Matching hexagons to nearest road edge...")
    try:
        ne = ox.distance.nearest_edges(G, X=hx.lng.values, Y=hx.lat.values)
    except Exception:
        ne = ox.nearest_edges(G, X=hx.lng.values, Y=hx.lat.values)
    idx = pd.MultiIndex.from_tuples([(u, v, k) for u, v, k in ne])
    hw = edges.loc[idx, "highway"].apply(base_highway).values

    hx["highway"] = hw
    hx["road_class"] = [ROAD_LABEL.get(h, "Minor road") for h in hw]
    hx["s_road"] = [ROAD_WEIGHT.get(h, DEFAULT_ROAD_W) for h in hw]

    # recompute the component scores (volume/persistence may already exist; redo cleanly)
    hx["s_volume"] = minmax(np.log1p(hx.violations))
    hx["s_severity"] = minmax(hx.mean_severity)
    hx["s_persistence"] = minmax(np.log1p(hx.active_days))
    hx["s_junction"] = hx.at_junction.clip(0, 1)

    hx["CIS"] = (100 * (
        W["volume"] * hx.s_volume
        + W["severity"] * hx.s_severity
        + W["persistence"] * hx.s_persistence
        + W["junction"] * hx.s_junction
        + W["road"] * hx.s_road
    )).round(1)

    hx = hx.sort_values("CIS", ascending=False).reset_index(drop=True)
    hx["rank"] = hx.index + 1
    hx.to_parquet(HEX, index=False)

    # refresh human-readable top-50
    cols = ["rank", "CIS", "lat", "lng", "violations", "active_days",
            "top_violation", "top_vehicle", "top_station", "road_class",
            "peak_daypart", "at_junction"]
    top = hx[cols].head(50).copy()
    top["at_junction"] = (top.at_junction * 100).round(0).astype(int).astype(str) + "%"
    top.to_csv(OUT_CSV, index=False)

    print(f"\nUpdated {len(hx):,} hexagons with road class -> {HEX.name}")
    print("\nRoad-class distribution of hotspots:")
    print(hx.road_class.value_counts())
    print("\n==== TOP 10 (road-weighted CIS) ====")
    show = hx.head(10)[["rank", "CIS", "violations", "top_violation",
                        "road_class", "top_station", "peak_daypart"]]
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
