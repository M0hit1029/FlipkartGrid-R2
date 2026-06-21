"""
Phase 6 - Point-of-interest (POI) driver analysis.

The problem statement names the real causes of spillover parking: commercial
areas, metro stations and events. This script tags every hotspot hexagon with
the nearest such POI, so each hotspot gets an explanation - *why* it exists -
instead of being an anonymous dot.

Input : data/hotspots.parquet
Output: data/hotspots.parquet  (overwritten, adds poi_category / poi_name / poi_dist_m)

Method
------
1. Pull relevant POIs for Bengaluru from OpenStreetMap (metro, market, mall,
   school/college, hospital, transit hub, event venue, place of worship).
2. For each hotspot centroid, find the nearest POI (haversine BallTree).
3. If the nearest POI is within DRIVER_RADIUS_M, label the hotspot with that
   driver category; otherwise label it "General on-street".

Run:  python src/poi.py   (needs internet; cached road download is separate)
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HEX = ROOT / "data" / "hotspots.parquet"
POI_CACHE = ROOT / "data" / "pois.parquet"

NORTH, SOUTH, EAST, WEST = 13.16, 12.80, 77.78, 77.44
DRIVER_RADIUS_M = 250  # within this distance, the POI is the likely driver

# category -> OSM tag filter (osmnx features_from_bbox tags dict)
POI_TAGS = {
    "Metro / transit": {"railway": ["station", "subway_entrance"],
                        "station": "subway", "public_transport": "station"},
    "Market / mall": {"amenity": "marketplace",
                     "shop": ["mall", "supermarket", "department_store"]},
    "School / college": {"amenity": ["school", "college", "university"]},
    "Hospital": {"amenity": ["hospital"]},
    "Bus station": {"amenity": "bus_station"},
    "Event venue": {"leisure": ["stadium"],
                   "amenity": ["cinema", "theatre", "events_venue", "conference_centre"]},
}


def fetch_pois(ox):
    if POI_CACHE.exists():
        print(f"Loading cached POIs: {POI_CACHE.name}")
        return pd.read_parquet(POI_CACHE)

    rows = []
    for cat, tags in POI_TAGS.items():
        print(f"  fetching {cat} ...")
        try:
            gdf = ox.features_from_bbox(bbox=(WEST, SOUTH, EAST, NORTH), tags=tags)
        except TypeError:
            gdf = ox.features_from_bbox(NORTH, SOUTH, EAST, WEST, tags=tags)
        except Exception as e:
            print(f"    skip {cat}: {e}")
            continue
        if gdf.empty:
            continue
        cent = gdf.geometry.representative_point()
        name = gdf["name"] if "name" in gdf.columns else pd.Series(index=gdf.index)
        rows.append(pd.DataFrame({
            "category": cat,
            "name": name.fillna(cat).values,
            "lat": cent.y.values,
            "lng": cent.x.values,
        }))
    pois = pd.concat(rows, ignore_index=True).dropna(subset=["lat", "lng"])
    pois.to_parquet(POI_CACHE, index=False)
    print(f"  cached {len(pois):,} POIs -> {POI_CACHE.name}")
    return pois


def main():
    try:
        import osmnx as ox
        from sklearn.neighbors import BallTree
    except ImportError as e:
        raise SystemExit(f"missing dependency: {e}")

    hx = pd.read_parquet(HEX)
    print(f"Loaded {len(hx):,} hotspot hexagons")
    pois = fetch_pois(ox)
    print(f"Using {len(pois):,} POIs across {pois.category.nunique()} categories")

    # nearest POI per hexagon via haversine BallTree (radians)
    poi_rad = np.radians(pois[["lat", "lng"]].values)
    hex_rad = np.radians(hx[["lat", "lng"]].values)
    tree = BallTree(poi_rad, metric="haversine")
    dist, idx = tree.query(hex_rad, k=1)
    dist_m = (dist[:, 0] * 6371000.0).round(0)  # earth radius m
    near = pois.iloc[idx[:, 0]].reset_index(drop=True)

    hx["poi_dist_m"] = dist_m.astype(int)
    within = hx["poi_dist_m"] <= DRIVER_RADIUS_M
    hx["poi_category"] = np.where(within, near["category"].values, "General on-street")
    hx["poi_name"] = np.where(within, near["name"].values, "-")

    hx.to_parquet(HEX, index=False)
    print(f"\nUpdated hotspots with POI drivers -> {HEX.name}")
    print(f"Within {DRIVER_RADIUS_M} m of a known driver: "
          f"{within.mean()*100:.1f}% of hotspots\n")
    print("Hotspot drivers (all zones):")
    print(hx.poi_category.value_counts())
    print("\nDrivers among the TOP 50 zones:")
    print(hx.sort_values("CIS", ascending=False).head(50).poi_category.value_counts())


if __name__ == "__main__":
    main()
