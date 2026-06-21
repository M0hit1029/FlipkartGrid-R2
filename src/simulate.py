"""
Phase 5 - Enforcement planning & before/after simulation.

Enforcement resources are limited: a city can only actively cover so many zones
at once. This module answers two operational questions:

  1. "If we can patrol K zones, WHICH ones, and how much congestion impact do we
      recover?"  -> greedy pick of the highest-impact hexagons.
  2. "How concentrated is the problem?"  -> a coverage curve showing what share
      of total impact sits in the top-N zones (the diminishing-returns story).

Impact unit
-----------
We score each hexagon's burden as:

    impact = violations * (CIS / 100)

i.e. how many violations occur, scaled by how congestion-impactful the spot is.
A zone with many violations AND a high CIS contributes most to city congestion.

Enforcing a zone is assumed to remove `effectiveness` of its impact (deterrence),
a tunable 0..1 factor (default 0.6). Zones are independent, so a greedy pick of
the top-impact zones is optimal for a fixed budget.

These are planning estimates from a proxy model, not measured traffic outcomes.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HEX = ROOT / "data" / "hotspots.parquet"


def with_impact(hx: pd.DataFrame) -> pd.DataFrame:
    """Add the per-zone impact column (violations weighted by CIS)."""
    out = hx.copy()
    out["impact"] = out["violations"] * (out["CIS"] / 100.0)
    return out


def coverage_curve(hx: pd.DataFrame) -> pd.DataFrame:
    """Cumulative share of total impact vs. number of zones enforced (sorted)."""
    d = with_impact(hx).sort_values("impact", ascending=False).reset_index(drop=True)
    total = d["impact"].sum() or 1.0
    d["zones"] = np.arange(1, len(d) + 1)
    d["cum_impact_share"] = d["impact"].cumsum() / total
    d["cum_violation_share"] = d["violations"].cumsum() / (d["violations"].sum() or 1)
    return d


def plan(hx: pd.DataFrame, n_zones: int, effectiveness: float = 0.6) -> dict:
    """Pick the top-n_zones by impact and estimate the recovery."""
    d = with_impact(hx).sort_values("impact", ascending=False).reset_index(drop=True)
    n_zones = int(min(max(n_zones, 0), len(d)))
    return _bundle(d, d.head(n_zones), effectiveness)


def station_summary(hx: pd.DataFrame) -> pd.DataFrame:
    """Per police-station rollup: zones owned, critical zones, impact, violations."""
    d = with_impact(hx)
    s = d.groupby("top_station").agg(
        zones=("h3", "count"),
        critical_zones=("CIS", lambda x: int((x >= 60).sum())),
        violations=("violations", "sum"),
        impact=("impact", "sum"),
        top_zone_rank=("rank", "min"),
    ).reset_index().rename(columns={"top_station": "station"})
    total = s["impact"].sum() or 1.0
    s["impact_share"] = s["impact"] / total
    return s.sort_values("impact", ascending=False).reset_index(drop=True)


def allocate_by_station(hx: pd.DataFrame, capacity: dict,
                        effectiveness: float = 0.6) -> dict:
    """For each station, greedily pick its own top-impact zones, up to its capacity.

    capacity: {station_name: n_patrols}. Picks within each station's jurisdiction.
    """
    d = with_impact(hx)
    picks = []
    for station, n in capacity.items():
        if not n:
            continue
        owned = d[d.top_station == station].sort_values("impact", ascending=False)
        picks.append(owned.head(int(n)))
    sel = (pd.concat(picks) if picks else d.head(0)).copy()
    return _bundle(d, sel, effectiveness)


def evaluate_selection(hx: pd.DataFrame, selected_h3, effectiveness: float = 0.6) -> dict:
    """Evaluate an arbitrary, hand-picked set of zones (by h3 id)."""
    d = with_impact(hx)
    sel = d[d.h3.isin(list(selected_h3))].sort_values("impact", ascending=False)
    res = _bundle(d, sel, effectiveness)
    # benchmark vs the optimal plan of the SAME size (top-k by impact)
    k = len(sel)
    optimal_impact = d.sort_values("impact", ascending=False).head(k)["impact"].sum()
    res["optimal_impact_share"] = (optimal_impact / (d["impact"].sum() or 1.0))
    res["efficiency_vs_optimal"] = (
        sel["impact"].sum() / optimal_impact if optimal_impact else 0.0
    )
    return res


def _bundle(all_d: pd.DataFrame, sel: pd.DataFrame, eff: float) -> dict:
    """Shared metrics for a selected set of zones."""
    total_impact = all_d["impact"].sum() or 1.0
    total_viol = all_d["violations"].sum() or 1
    return {
        "selected": sel,
        "n_zones": len(sel),
        "effectiveness": eff,
        "impact_share_addressed": sel["impact"].sum() / total_impact,
        "impact_recovered_share": eff * sel["impact"].sum() / total_impact,
        "viol_in_selected": int(sel["violations"].sum()),
        "viol_deterred": int(round(eff * sel["violations"].sum())),
        "viol_share_in_selected": sel["violations"].sum() / total_viol,
        "total_zones": len(all_d),
        "n_stations": sel["top_station"].nunique() if len(sel) else 0,
    }


def zones_to_cover(hx: pd.DataFrame, target_share: float) -> int:
    """Smallest number of zones whose impact covers `target_share` of the total."""
    d = coverage_curve(hx)
    hit = d[d["cum_impact_share"] >= target_share]
    return int(hit["zones"].iloc[0]) if len(hit) else len(d)


def main():
    hx = pd.read_parquet(HEX)
    print(f"Loaded {len(hx):,} hexagons\n")
    for share in (0.5, 0.8):
        k = zones_to_cover(hx, share)
        print(f"  {int(share*100)}% of city congestion impact sits in the top {k} "
              f"zones ({k/len(hx)*100:.1f}% of all hotspots)")
    print()
    for k in (25, 50, 100):
        p = plan(hx, k, effectiveness=0.6)
        print(f"  Patrol top {k:3d} zones (eff 60%): "
              f"covers {p['impact_share_addressed']*100:4.1f}% of impact, "
              f"deters ~{p['viol_deterred']:,} violations")


if __name__ == "__main__":
    main()
