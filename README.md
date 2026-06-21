# Parking Congestion Intelligence (Bengaluru)

AI-driven detection of **illegal-parking hotspots** and quantification of their
**impact on traffic flow**, to enable targeted (not patrol-based) enforcement.

**Problem:** On-street illegal/spillover parking chokes carriageways and
intersections. Enforcement today is reactive; there's no heatmap of violations
vs. congestion impact, so it's hard to prioritise zones.

**Dataset:** 298,450 traffic-police parking-violation records, Nov 2023–Apr 2024,
with GPS, violation type, vehicle type, timestamp, police station, junction.

## Pipeline

| Step | Script | Output |
|---|---|---|
| 1. Clean & parse | `src/clean.py` | `data/clean.parquet` |
| 2. Hotspots + scoring | `src/hotspots.py` | `data/hotspots.parquet`, `output/top_zones.csv` |
| 3. Road-network weighting (OSM) | `src/roads.py` | re-scored `data/hotspots.parquet` + cached graph |
| 4. POI driver analysis (OSM) | `src/poi.py` | hotspots tagged with nearest metro/market/school/etc. |
| 5. Enforcement simulation | `src/simulate.py` | planning estimates (used by the planner page) |
| 6. Predictive scheduler | `src/schedule.py` | `data/zone_time.parquet`, `output/patrol_roster.csv` |
| 7. Dashboard (3 pages) | `src/app.py` | Dashboard · Deployment · How it works |

## Congestion Impact Score (CIS)

The raw data has **no live traffic feed**, so "impact on flow" is modelled from
proxies that are known to choke roads. Per ~150 m H3 hexagon:

```
CIS = 100 · ( 0.35·volume + 0.30·severity + 0.20·persistence + 0.15·junction )
```
- **volume** – number of violations (log-scaled)
- **severity** – footpath / main-road / near-crossing parking weighted highest
- **persistence** – recurring across many distinct days = chronic, not one-off
- **junction** – share of violations at/near a tagged junction

## Run

```bash
pip install streamlit folium streamlit-folium h3 pandas pyarrow scikit-learn
python src/clean.py
python src/hotspots.py
streamlit run src/app.py
```

## Notes / caveats
- Timestamps are stored UTC and converted to IST (+5:30). The recorded hours
  skew to early-day; the daypart story should be validated with the police before
  operational use. Spatial ranking is unaffected.
- Stretch: weight CIS by OpenStreetMap road class/lane-width (OSMnx) for a
  stronger physical congestion model.
