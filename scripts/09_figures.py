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

import numpy as np
import pandas as pd

from taxi_shock.config import load_config, path
from taxi_shock.evaluation import tied_with_best
from taxi_shock.viz.figures import (
    f1_demand_map,
    f1b_citywide_weekly,
    f1c_vendor_weekly,
    f2_model_comparison,
    f2b_fan_chart,
    f3_error_over_time,
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
    gaps = pd.read_csv(res / "wape_gap_bootstrap.csv")
    best, tied = tied_with_best(gaps, "all")   # tied: gap to the best not distinguishable
    stats = {"source_files": ["results/backtest_2024.csv", "results/forecast_summary.json",
                              "results/wape_gap_bootstrap.csv", "results/fan_chart_f2b.csv"],
             "primary_window": primary,
             "wape_all_zones": {k: round(float(v), 4) for k, v in allz.items()},
             "lgbm_wape_change_vs_seasonal_naive": round(lg / base - 1, 4),
             "lowest_wape_model": best,
             "not_distinguishable_from_lowest_all_zones": tied}
    names = {"seasonal_naive": "seasonal naive", "stat_ets_profile": "AutoETS baseline",
             "lgbm_quantile": "LightGBM", "chronos2_weather_past": "Chronos-2 (past weather)",
             "chronos2_weather_future": "Chronos-2 (future weather)"}
    # the title names the lowest point WAPE and every model whose bootstrap gap to it is not
    # distinguishable from 0; it implies nothing about the other pairs (all pairs are in
    # results/wape_gap_bootstrap.csv)
    title = (f"2024 day-ahead WAPE over all modeled zones: {names[best]} lowest at "
             f"{allz[best]:.4f}")
    if tied:
        listed = " and ".join(f"{names[m]} ({allz[m]:.4f})" for m in tied)
        title += f"; {listed} not distinguishable from it"
    title += f"; seasonal naive {base:.4f}"
    note = (f"Raw forecasts (calibration does not change point forecasts); trained models: "
            f"{primary} training window, monthly refit; Chronos-2 zero-shot, "
            f"{cfg['chronos']['context_hours']} h context. "
            "Each panel has its own scale. Not distinguishable: the 95% interval of the WAPE gap "
            f"(paired bootstrap over origin days, {int(gaps['block_days'].iloc[0])}-day blocks) "
            "contains 0. Sources: "
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


def _pct(log_ratio: float) -> float:
    return (float(np.exp(log_ratio)) - 1) * 100


def phase3(cfg: dict) -> None:
    """F3 from results/shock_errors.csv and results/drift_detection.json; title numbers saved
    to results/figure_stats_phase3.json."""
    res, figs = path("results", cfg), path("figures", cfg)
    if not (res / "shock_errors.csv").exists():
        logging.warning("results/shock_errors.csv missing: F3 skipped")
        return
    sh = cfg["shock"]
    det = json.loads((res / "drift_detection.json").read_text())
    prim = det["primary"]
    t = pd.read_csv(res / "shock_errors.csv", parse_dates=["date"])
    sel = t[(t["model"] == prim["model"]) & (t["series"] == prim["series"])
            & (t["window_days"] == sh["rolling_days"])]
    policy = pd.Timestamp(cfg["data"]["policy_date"])
    first_full = policy + pd.Timedelta(days=sh["rolling_days"] - 1)   # first all-post window
    pre_end = policy - pd.Timedelta(days=1)                            # last all-pre window
    at = sel.set_index(["zone_group", "date"])
    stats = {"source_files": ["results/shock_errors.csv", "results/drift_detection.json"],
             "model": prim["model"], "series": prim["series"],
             "first_post_window_end": str(first_full.date()),
             "last_pre_window_end": str(pre_end.date())}
    for g in ("cbd", "non_cbd"):
        stats[g] = {
            "wape_last_pre_window": round(float(at.loc[(g, pre_end), "wape"]), 4),
            "wape_first_post_window": round(float(at.loc[(g, first_full), "wape"]), 4),
            "actual_vs_forecast_pct_first_post_window": round(
                _pct(at.loc[(g, first_full), "log_actual_over_forecast"]), 2),
            "cusum": prim["groups"][g]["cusum"]["first_alarm_on_or_after_policy"],
            "rolling_bias": prim["groups"][g]["rolling_bias"]["first_alarm_on_or_after_policy"]}
    c, n = stats["cbd"], stats["non_cbd"]

    def gap(v: float) -> str:
        return f"{abs(v):.1f}% {'below' if v < 0 else 'above'}"

    title = (f"First four weeks of congestion pricing: CBD pickups "
             f"{gap(c['actual_vs_forecast_pct_first_post_window'])} the frozen forecast, "
             f"non-CBD {gap(n['actual_vs_forecast_pct_first_post_window'])}")
    if c["cusum"]:
        title += f"; CUSUM alarm for the CBD after {c['cusum']['delay_days']} days"
    else:
        title += "; no CUSUM alarm for the CBD"
    markers = []
    for key, name in (("cusum", "CUSUM"), ("rolling_bias", "rolling-bias rule")):
        a = c[key]
        if a:
            markers.append((a["date"], f"{name} alarm (CBD), day {a['delay_days']}"))
    note = (f"LightGBM day-ahead forecasts: Phase-2 out-of-sample backtest (monthly refits) "
            f"before {sh['monitor_start']}, then the model frozen on data to "
            f"{sh['frozen_train_end']}. Trailing {sh['rolling_days']}-day windows; pre-policy "
            "segments lighter. Non-CBD = every modeled zone outside the CBD. Monitors: daily "
            "log(actual/forecast) standardized on 2024. Sources: results/shock_errors.csv, "
            "results/drift_detection.json.")
    stats["title"] = title
    f3_error_over_time(sel, cfg["data"]["policy_date"], markers, title, note,
                       figs / "F3_error_over_time")
    (res / "figure_stats_phase3.json").write_text(json.dumps(stats, indent=2) + "\n")
    logging.info("wrote F3 to %s", figs)


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
    phase3(cfg)


if __name__ == "__main__":
    main()
