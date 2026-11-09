"""Build figures from files under results/ only (never from the warehouse directly).

Zone polygons come from the raw TLC shapefile (a lookup, not a result). Numbers used in figure
titles are computed here from results/ files and saved to results/figure_stats_phase1.json, so
every title number has a source file.

Usage:
    python scripts/09_figures.py --smoke     # Phase-0 placeholder figure
    python scripts/09_figures.py --all       # every implemented figure
                                              # (Phase 1: F1, F1b, F1c; Phase 2: F2, F2b)
"""

from __future__ import annotations

import argparse
import json
import logging

import pandas as pd

from taxi_shock.config import load_config, path
from taxi_shock.viz.figures import (
    f1_demand_map,
    f1b_citywide_weekly,
    f1c_vendor_weekly,
    f2_model_comparison,
    f2b_fan_chart,
    smoke_placeholder,
)
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
    vs = json.loads((res / "vendor_summary.json").read_text())
    new_id = str(vs["new_vendor"]["vendor_id"])
    new_share = vs["presence"][new_id]["share_of_window_pickups"]
    post_share = vs["detectability"]["post_policy_new_vendor_share_by_zone_group"]
    stats = {
        "source_files": ["results/zone_summary.csv", "results/citywide_yearly.csv",
                         "results/vendor_summary.json"],
        "f1c_new_vendor_entry_week": vs["new_vendor"]["entry_week"],
        "f1c_new_vendor_post_policy_share_cbd": post_share["cbd"],
        "f1c_new_vendor_share_of_window_pickups": new_share,
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
    name = vs["presence"][new_id]["vendor_name"]
    t1c = (f"{name} (VendorID {new_id}) passed 1% of weekly pickups on "
           f"{vs['new_vendor']['entry_week']}; {post_share['cbd']:.1%} of post-policy CBD pickups")
    f1c_vendor_weekly(pd.read_csv(res / "vendor_series.csv"), t1c, figs / "F1c_vendor_weekly")
    logging.info("wrote F1, F1b, F1c to %s", figs)


def phase2(cfg: dict) -> None:
    res, figs = path("results", cfg), path("figures", cfg)
    if not (res / "backtest_2024.csv").exists():
        logging.warning("results/backtest_2024.csv missing: Phase-2 figures skipped")
        return
    summary = json.loads((res / "forecast_summary.json").read_text())
    primary = summary["primary_window"]["chosen"] or "expanding"
    t = pd.read_csv(res / "backtest_2024.csv")
    sel = ((t["metric"] == "wape") & (t["horizon_bucket"] == "all") & (t["subset"] == "all")
           & (t["calibration"] == "raw") & t["window"].isin([primary, "zero_shot"]))
    wape = t.loc[sel, ["model", "zone_group", "value"]]
    allz = wape[wape["zone_group"] == "all"].set_index("model")["value"]
    base, lg = float(allz["seasonal_naive"]), float(allz.get("lgbm_quantile", float("nan")))
    boot = pd.read_csv(res / "wape_gap_bootstrap.csv")
    ball = boot[boot["zone_group"] == "all"]
    tied = ball.loc[ball["tied_with_best"], "model"].tolist()   # sorted by WAPE
    best = ball["best_model"].iloc[0]
    stats = {"source_files": ["results/backtest_2024.csv", "results/forecast_summary.json",
                              "results/wape_gap_bootstrap.csv", "results/fan_chart_f2b.csv"],
             "primary_window": primary,
             "wape_all_zones": {k: round(float(v), 4) for k, v in allz.items()},
             "lgbm_wape_change_vs_seasonal_naive": round(lg / base - 1, 4),
             "lowest_wape_model": best,
             "tied_with_lowest_all_zones": tied}
    names = {"seasonal_naive": "seasonal naive", "stat_ets_profile": "AutoETS baseline",
             "lgbm_quantile": "LightGBM", "chronos2_weather_past": "Chronos-2 (past weather)",
             "chronos2_weather_future": "Chronos-2 (future weather)"}
    # a single model is named lowest only if the bootstrap interval of every other model's gap
    # to it excludes 0 (results/wape_gap_bootstrap.csv)
    if len(tied) == 1:
        title = (f"2024 day-ahead WAPE over all modeled zones: {names[best]} lowest "
                 f"({allz[best]:.4f} vs seasonal naive {base:.4f})")
    else:
        listed = ", ".join(names[m] for m in tied[:-1]) + f" and {names[tied[-1]]}"
        title = (f"2024 day-ahead WAPE over all modeled zones: {listed} within bootstrap "
                 f"uncertainty ({allz[tied].min():.4f}-{allz[tied].max():.4f}) vs seasonal "
                 f"naive {base:.4f}")
    note = (f"Raw forecasts (calibration does not change point forecasts); trained models: "
            f"{primary} training window, monthly refit; Chronos-2 zero-shot, "
            f"{cfg['chronos']['context_hours']} h context. "
            "Each panel has its own scale. Ties: 95% paired block bootstrap over origin days "
            f"({int(ball['block_days'].iloc[0])}-day blocks). Sources: "
            "results/backtest_2024.csv, results/wape_gap_bootstrap.csv.")
    f2_model_comparison(wape, title, note, figs / "F2_model_comparison")

    fan = pd.read_csv(res / "fan_chart_f2b.csv", parse_dates=["target_ts"])
    fan = fan[(fan["model"] == "lgbm_quantile") & (fan["window"] == primary)]
    if len(fan):
        zs = pd.read_csv(res / "zone_summary.csv").set_index("zone_id")
        zone = int(fan["zone_id"].iloc[0])
        raw = fan[fan["calibration"] == "raw"]
        inside = int(((raw["y"] >= raw["q10"]) & (raw["y"] <= raw["q90"])).sum())
        stats.update({"f2b_zone_id": zone, "f2b_hours": len(raw),
                      "f2b_hours_inside_raw_80": inside})
        t2b = (f"LightGBM day-ahead forecast, {zs.loc[zone, 'zone_name']}: raw 80% band holds "
               f"{inside} of {len(raw)} hours, week of {raw['target_ts'].min().date()}")
        f2b_fan_chart(fan, zs.loc[zone, "zone_name"], t2b, figs / "F2b_fan_chart")
    (res / "figure_stats_phase2.json").write_text(json.dumps(stats, indent=2) + "\n")
    logging.info("wrote F2, F2b to %s", figs)


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
    phase2(cfg)


if __name__ == "__main__":
    main()
