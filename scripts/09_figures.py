"""Build figures from files under results/ only (never from the warehouse directly).

Zone polygons come from the raw TLC shapefile (a lookup, not a result). Numbers used in figure
titles are computed here from results/ files and saved to results/figure_stats_phase1.json, so
every title number has a source file.

Usage:
    python scripts/09_figures.py --smoke     # Phase-0 placeholder figure
    python scripts/09_figures.py --all       # every implemented figure (Phase 1: F1, F1b)
"""

from __future__ import annotations

import argparse
import json
import logging

import pandas as pd

from taxi_shock.config import load_config, path
from taxi_shock.viz.figures import f1_demand_map, f1b_citywide_weekly, smoke_placeholder
from taxi_shock.viz.maps import load_zones


def phase1(cfg: dict) -> None:
    res, figs = path("results", cfg), path("figures", cfg)
    summary = pd.read_csv(res / "zone_summary.csv")
    weekly = pd.read_csv(res / "citywide_weekly.csv")
    yearly = pd.read_csv(res / "citywide_yearly.csv")

    total = summary["pickups_2024"].sum()
    share = {g: float(summary.loc[summary["zone_group"] == g, "pickups_2024"].sum() / total)
             for g in ["cbd", "manhattan_non_cbd", "airports", "other"]}
    n_cbd = int(summary["is_cbd"].sum())
    base_year = int(yearly["year"].min())
    ratio_col = f"ratio_to_{base_year}"
    r2024 = float(yearly.loc[yearly["year"] == 2024, ratio_col].iloc[0])
    stats = {
        "source_files": ["results/zone_summary.csv", "results/citywide_yearly.csv"],
        "share_2024_pickups_by_zone_group": {k: round(v, 4) for k, v in share.items()},
        "n_cbd_zones": n_cbd,
        f"mean_daily_pickups_2024_vs_{base_year}": r2024,
    }
    (res / "figure_stats_phase1.json").write_text(json.dumps(stats, indent=2) + "\n")

    t1 = (f"{n_cbd} CBD zones held {share['cbd']:.0%} of 2024 yellow-taxi pickups; "
          f"airports {share['airports']:.0%}")
    f1_demand_map(load_zones(path("raw_lookup", cfg) / "taxi_zones.shp"), summary, t1,
                  figs / "F1_demand_map")
    t1b = (f"Weekly yellow-taxi pickups: 2024 daily mean at {r2024:.0%} of {base_year}")
    f1b_citywide_weekly(weekly, cfg["annotations"]["covid_ny_pause"], t1b,
                        figs / "F1b_citywide_weekly")
    logging.info("wrote F1, F1b to %s", figs)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if args.smoke:
        fc = pd.read_parquet(path("smoke.results_dir", cfg) / "forecasts_smoke.parquet")
        paths = smoke_placeholder(fc, path("smoke.figures_dir", cfg) / "F0_smoke_placeholder")
        logging.info("wrote %s", ", ".join(str(p) for p in paths))
        return
    phase1(cfg)


if __name__ == "__main__":
    main()
