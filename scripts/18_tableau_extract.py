"""Write tidy extracts for Stanley's Tableau Public dashboard (`make tableau-extract`).

PLAN Amendment 4 (E2). The Builder provides data and a specification
(reports/dashboard_spec.md); Stanley builds and publishes the dashboard. Every file is derived
from the dbt marts or from results/ files, so the dashboard shows the same numbers as the report.
Written to reports/tableau/:

  channel_zone_week.csv   pickup zone x complete panel week: app, street hail, CMT contracted block
                          and total pickups (fct_weekly_zone_channel; app = any e-hail app,
                          Amendment 4a), with zone name, borough, zone group and CBD flag
  zone_summary.csv        per zone and period (2023, 2024, 2025, Jan-Sep 2026): app share (block
                          excluded), mean weekly pickups, and growth 2023 -> 2025 (log ratio of
                          mean weekly pickups) — results/channel_zone_share.csv
  zones.geojson           TLC zone polygons (WGS84, simplified to ~10 m) with the same zone fields
  incrementality.csv      incrementality estimates (D2) by area and estimator with 95% intervals
                          (results/incrementality_panel_summary.csv), with the reading set in
                          PLAN Amendment 5 (not identified)
  lyft_entry_daily.csv    Lyft-entry (D3) daily Curb vs CMT series in the CBD and Manhattan
                          non-CBD with the window labels (results/lyft_entry_daily.csv,
                          results/lyft_entry.json)
  README.txt              field definitions and sources

Reads: warehouse mart fct_weekly_zone_channel, results/zone_summary.csv, the TLC zone shapefile
(data/raw/lookup), the results/ files named above; config keys `tableau`, `channel.map_min_weekly`.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from taxi_shock.causal.panel import full_weeks
from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect
from taxi_shock.viz.maps import load_zones

LOG = logging.getLogger("tableau")
READING_D2 = ("Estimates of the share of app trips that are additional range across estimators; "
              "they disagree beyond their intervals and one lead placebo fails, so "
              "incrementality is not identified from these data (Amendment 5).")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    out = repo_root() / cfg["tableau"]["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    zs = pd.read_csv(res / "zone_summary.csv")[["zone_id", "zone_name", "borough",
                                                 "zone_group", "is_cbd"]]

    with connect(path("warehouse", cfg), cfg=cfg) as con:
        w = con.execute("""
            select zone_id, week_start,
                   sum(pickups) filter (where channel = 'app') as app,
                   sum(pickups) filter (where channel = 'street'
                                        and not is_cmt_outer_block) as street_hail,
                   sum(pickups) filter (where is_cmt_outer_block) as cmt_contracted_block,
                   sum(pickups) as total
            from fct_weekly_zone_channel group by all""").df()
    w["week_start"] = pd.to_datetime(w["week_start"])
    w = full_weeks(w, cfg).fillna(0)
    cnt = ["app", "street_hail", "cmt_contracted_block", "total"]
    w[cnt] = w[cnt].astype("int64")
    w = w.merge(zs, on="zone_id", how="left").sort_values(["zone_id", "week_start"])
    w["week_start"] = w["week_start"].dt.date
    w.to_csv(out / "channel_zone_week.csv", index=False, lineterminator="\n")

    z = pd.read_csv(res / "channel_zone_share.csv")
    p = z.pivot_table(index="zone_id", columns="period",
                      values=["app_share_excl_block", "mean_weekly_pickups"])
    p.columns = [f"{a}_{b}" for a, b in p.columns]
    p = p.reset_index()
    b, e = p["mean_weekly_pickups_2023"], p["mean_weekly_pickups_2025"]
    min_w = float(cfg["channel"]["map_min_weekly"])
    p["growth_log_2023_2025"] = np.where((b >= min_w) & (e > 0), np.log(e / b), np.nan)
    p = zs.merge(p, on="zone_id", how="left")
    p.to_csv(out / "zone_summary.csv", index=False, lineterminator="\n", float_format="%.6g")

    g = load_zones(path("raw_lookup", cfg) / "taxi_zones.shp").merge(zs, on="zone_id")
    g["geometry"] = g.geometry.simplify(float(cfg["tableau"]["simplify_feet"]))
    g.to_crs(4326).to_file(out / "zones.geojson", driver="GeoJSON")

    inc = pd.read_csv(res / "incrementality_panel_summary.csv")
    inc = inc[inc["area"] != "airports"].assign(reading=READING_D2)
    inc.to_csv(out / "incrementality.csv", index=False, lineterminator="\n",
               float_format="%.6g")

    ly = pd.read_csv(res / "lyft_entry_daily.csv", parse_dates=["day"])
    win = json.loads((res / "lyft_entry.json").read_text())["windows"]
    ly["vendor"] = ly["vendor_id"].map({1: "CMT (control)", 2: "Curb (gains Lyft)"})
    ly["window"] = np.select(
        [ly["day"] <= pd.Timestamp(win["pre_end"]), ly["day"] >= pd.Timestamp(win["post_start"])],
        ["pre", "post"], default="excluded (code-A surge)")
    ly["label"] = "preliminary, not identified (Amendment 5)"
    ly["day"] = ly["day"].dt.date
    ly.to_csv(out / "lyft_entry_daily.csv", index=False, lineterminator="\n")

    (out / "README.txt").write_text(
        "Extracts for the Tableau Public dashboard (reports/dashboard_spec.md); regenerate with "
        "`make tableau-extract`.\n"
        "channel_zone_week.csv: valid yellow pickups per pickup zone and complete panel week "
        "(Sunday start; a row only where the zone had pickups that week, so a missing "
        "zone-week means 0); app = any e-hail app (Flex Fare before 2026-06, request_source not "
        "NULL from 2026-06); street_hail excludes the CMT contracted block (VendorID 1 outer-"
        "borough trips, ended 2026-05), which is its own column.\n"
        "zone_summary.csv: app_share_excl_block_<period> and mean_weekly_pickups_<period>; "
        f"growth_log_2023_2025 only for zones with >= {min_w:.0f} pickups/week in 2023.\n"
        "zones.geojson: TLC taxi zones, WGS84, simplified.\n"
        "incrementality.csv: theta = 1 + d street / d app per zone-week; not identified "
        "(estimators disagree).\n"
        "lyft_entry_daily.csv: CBD + Manhattan non-CBD daily pickups by vendor; preliminary.\n"
        "Sources: dbt mart fct_weekly_zone_channel and results/ files named in "
        "scripts/18_tableau_extract.py.\n")
    LOG.info("extracts written to %s", out)


if __name__ == "__main__":
    main()
