"""
Phase 1 - Clean & parse the Bengaluru parking-violation dataset.

Input : the raw police-violation CSV
Output: data/clean.parquet  (one row per violation, parsed & enriched)

What it does
------------
- Parses the `violation_type` JSON list column into real Python lists
- Derives a primary (most-severe) violation type per record
- Parses timestamps and converts UTC -> IST (Asia/Kolkata, +5:30)
- Adds hour / day-of-week / is_weekend / daypart features
- Drops records with missing or out-of-Bengaluru coordinates
"""
import ast
import json
from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parents[1] / "data" / "raw.csv"
OUT = Path(__file__).resolve().parents[1] / "data" / "clean.parquet"

# Bengaluru bounding box (drop GPS noise outside the city)
LAT_MIN, LAT_MAX = 12.7, 13.4
LON_MIN, LON_MAX = 77.3, 77.9

# Severity ranking: how much each violation type chokes traffic flow.
# Higher = worse for carriageway/intersection throughput.
SEVERITY = {
    "PARKING NEAR ROAD CROSSING": 5,
    "PARKING IN A MAIN ROAD": 5,
    "PARKING ON FOOTPATH": 4,   # pushes pedestrians onto the road
    "WRONG PARKING": 3,
    "NO PARKING": 2,
}
DEFAULT_SEVERITY = 2


def parse_violation_list(val):
    """The column looks like '["WRONG PARKING","NO PARKING"]' -> real list."""
    if pd.isna(val):
        return []
    try:
        out = json.loads(val)
    except (json.JSONDecodeError, TypeError):
        try:
            out = ast.literal_eval(val)
        except (ValueError, SyntaxError):
            return []
    return [str(x).strip().upper() for x in out] if isinstance(out, list) else []


def primary_violation(vlist):
    """Pick the single most-severe violation in the record."""
    if not vlist:
        return "UNKNOWN"
    return max(vlist, key=lambda v: SEVERITY.get(v, DEFAULT_SEVERITY))


def daypart(hour):
    if 7 <= hour < 11:
        return "Morning peak (7-11)"
    if 11 <= hour < 16:
        return "Midday (11-16)"
    if 16 <= hour < 21:
        return "Evening peak (16-21)"
    return "Night (21-7)"


def main():
    print(f"Reading {RAW} ...")
    df = pd.read_csv(RAW, low_memory=False)
    n0 = len(df)
    print(f"  {n0:,} raw rows")

    # --- coordinates ---
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[
        df.latitude.between(LAT_MIN, LAT_MAX)
        & df.longitude.between(LON_MIN, LON_MAX)
    ]
    print(f"  {len(df):,} rows after coord cleaning ({n0 - len(df):,} dropped)")

    # --- violation types ---
    df["violations"] = df["violation_type"].apply(parse_violation_list)
    df["primary_violation"] = df["violations"].apply(primary_violation)
    df["severity"] = df["primary_violation"].map(SEVERITY).fillna(DEFAULT_SEVERITY)
    df["n_violations"] = df["violations"].apply(len)

    # --- time (UTC -> IST) ---
    ts = pd.to_datetime(df["created_datetime"], errors="coerce", utc=True)
    ist = ts.dt.tz_convert("Asia/Kolkata")
    df["ts_ist"] = ist
    df["hour"] = ist.dt.hour
    df["dow"] = ist.dt.dayofweek          # 0=Mon
    df["dow_name"] = ist.dt.day_name()
    df["is_weekend"] = df["dow"] >= 5
    df["date"] = ist.dt.date
    df["daypart"] = df["hour"].apply(lambda h: daypart(h) if pd.notna(h) else "Unknown")

    # store violations as JSON string so parquet is happy
    df["violations_str"] = df["violations"].apply(json.dumps)

    keep = [
        "id", "latitude", "longitude", "location", "vehicle_type",
        "primary_violation", "severity", "n_violations", "violations_str",
        "police_station", "junction_name", "ts_ist", "hour", "dow",
        "dow_name", "is_weekend", "date", "daypart",
    ]
    out = df[keep].copy()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"\nWrote {len(out):,} rows -> {OUT}")
    print("\nPrimary violation mix:")
    print(out.primary_violation.value_counts())
    print("\nDaypart mix (IST):")
    print(out.daypart.value_counts())


if __name__ == "__main__":
    main()
