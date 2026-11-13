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
    f3b_three_shocks,
    f4_event_study,
    f4b_effect_map,
    f4b_effect_map_html,
    f4c_heterogeneity,
    f4d_counterfactual_vs_did,
    f4e_placebo_distribution,
    f4f_speed_event_study,
    f4g_app_dispatch,
    f4h_synth_control,
    f4i_leave_one_out,
    f5_adaptation,
    f6_taxi_vs_fhv,
    f6a_channel_areas,
    f6b_app_share_maps,
    f6c_incrementality,
    f6d_lyft_entry,
    f6e_app_share_step,
    smoke_placeholder,
)
from taxi_shock.viz.maps import load_zones
from taxi_shock.viz.style import PALETTE


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

    cal = prim["groups"]["cbd"]["cusum"].get("calibration_alarms", [])
    stats["cbd"]["cusum_calibration_alarms"] = cal
    # wording: Stanley's ruling (Checkpoint 6, Amendment 5) - no CBD-specific break detected
    title = (f"No CBD-specific break: in the first four weeks of congestion pricing CBD pickups "
             f"ran {gap(c['actual_vs_forecast_pct_first_post_window'])} the frozen forecast, "
             f"non-CBD {gap(n['actual_vs_forecast_pct_first_post_window'])}")
    if c["cusum"] and cal:
        title += (f"; the one CBD CUSUM alarm (day {c['cusum']['delay_days']}) matches the "
                  f"calibration year's ({cal[0]['date']})")
    markers = []
    for a in cal:
        markers.append((a["date"], "CUSUM alarm, 2024 (calibration)", PALETTE["muted_text"]))
    for key, name in (("cusum", "CUSUM"), ("rolling_bias", "rolling-bias rule")):
        a = c[key]
        if a:
            markers.append((a["date"], f"{name} alarm (CBD), day {a['delay_days']}",
                            PALETTE["cbd"]))
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


LEVEL_LABELS = {"weekday": "weekday", "weekend": "weekend", "do_cbd": "ends in CBD",
                "do_non_cbd": "ends outside CBD", "dropoff_only_in_cbd": "dropoff only in CBD",
                "pickup_in_cbd": "pickup in CBD", "outer_boroughs": "B+Q control",
                "outer_boroughs_with_airports": "B+Q incl. airports"}


def _label(level: str) -> str:
    if level in LEVEL_LABELS:
        return LEVEL_LABELS[level]
    if level.startswith("h") and "_" in level:
        a, b = level[1:].split("_")
        return f"{a}-{b} h"
    return level.replace("dist_t", "distance T").replace("fare_t", "fare T").replace(
        "t1", "distance T1").replace("t2", "distance T2").replace("t3", "distance T3")


def _pct_str(b: float) -> str:
    """exp(b) - 1 as a signed percentage string (Phase-4 titles)."""
    return f"{(np.exp(b) - 1) * 100:+.1f}%"


def phase4(cfg: dict) -> None:
    """F4, F4b (+ html), F4c, F4d, F4e, F4f from Phase-4 results; title numbers saved to
    results/figure_stats_phase4.json."""
    res, figs = path("results", cfg), path("figures", cfg)
    if not (res / "did_static.json").exists() or not (res / "speed_did.json").exists():
        logging.warning("Phase-4 results missing: F4 figures skipped")
        return
    policy = cfg["data"]["policy_date"]
    sp = json.loads((res / "speed_did.json").read_text())["outcomes"]
    pl = json.loads((res / "placebo.json").read_text())
    es = pd.read_csv(res / "event_study.csv")
    ses = pd.read_csv(res / "speed_event_study.csv")
    month = es[(es["bins"] == "month")]
    main_es = month[month["spec"] == "main"]
    w_es = month[month["spec"] == "pre_volume_weighted_not_preregistered"]
    p_f = pl["pretrend_tests"]["event_study_month"]["pretrend"]["p_F"]
    yr = {lab: float(main_es.loc[main_es["k"].between(a, b), "coef"].mean())
          for lab, (a, b) in {"2023": (-24, -13), "2024": (-12, -1), "post": (0, 99)}.items()}
    stats: dict = {"source_files": ["results/did_static.json", "results/speed_did.json",
                                    "results/event_study.csv", "results/speed_event_study.csv",
                                    "results/placebo.json", "results/power_mde.json",
                                    "results/speed_power.json", "results/heterogeneity.csv",
                                    "results/speed_heterogeneity.csv",
                                    "results/counterfactual.csv", "results/effect_map.csv"],
                   "demand_mean_monthly_coef": yr, "demand_pretrend_p_F": p_f}
    ds = json.loads((res / "did_static.json").read_text())["estimates"]
    pw = json.loads((res / "power_mde.json").read_text())
    bw = ds["pre_volume_weighted_not_preregistered"]["terms"]["treated_post"]
    mde_w = pw["pre_volume_weighted"]["mde_pct"]
    p_fw = pl["pretrend_tests"]["event_study_month_pre_volume_weighted_not_preregistered"][
        "pretrend"]["p_F_hotelling"]
    stats.update({"demand_weighted": bw, "demand_weighted_mde_pct": mde_w,
                  "demand_weighted_pretrend_p_F_hotelling": p_fw})
    tpd = pd.read_csv(res / "placebo_time_distribution.csv")["pre_volume_weighted"]
    stats["demand_weighted_time_placebo_range"] = [float(tpd.min()), float(tpd.max())]
    # wording: Stanley's decision (a) "inconclusive" (DECISIONS 2026-11-12)
    t4 = (f"Weighted DiD, CBD pickups {_pct_str(bw['coef'])} [{_pct_str(bw['ci_lo'])}, "
          f"{_pct_str(bw['ci_hi'])}]: inconclusive. Pre-trends fail; outside every fake-date "
          f"placebo ({_pct_str(tpd.min())} to {_pct_str(tpd.max())})")
    f4_event_study(w_es, policy, t4,
                   "Monthly bins of log1p(weekly pickups) per zone, zones weighted by their mean "
                   "weekly pickups in the 52 pre weeks (primary since Checkpoint 4, C2; not "
                   "pre-registered); 38 CBD zones vs the donut control; zone and week FE, "
                   "weather x treated; 95% CIs clustered by zone; reference: the week before "
                   "2025-01-05. The pre-registered equal-weight path is in F4d. Source: "
                   "results/event_study.csv.", figs / "F4_event_study", "Effect on CBD pickups (%)")

    spd, dur = (sp[k]["main"]["terms"]["treated_post"] for k in ("log_mean_speed_mph",
                                                                  "log_mean_duration_min"))
    sp_f = sp["log_mean_speed_mph"]["event_study_month"]["pretrend"]["p_F"]
    stats["speed"] = {"speed": spd, "duration": dur, "pretrend_p_F": sp_f}
    spo = json.loads((res / "speed_did_outer.json").read_text())["outcomes"]
    so = spo["log_mean_speed_mph"]
    so_m, so_s = so["main"]["terms"]["treated_post"], so[
        "treated_seasonality_not_preregistered"]["terms"]["treated_post"]
    so_f = so["event_study_month"]["pretrend"]["p_F_hotelling"]
    stats["speed_outer"] = {"speed": so_m, "speed_seasonality": so_s,
                            "pretrend_p_F_hotelling": so_f}
    sm = ses[ses["bins"] == "month"]
    om = sm[(sm["control"] == "outer") & (sm["outcome"] == "log_mean_speed_mph")].sort_values("k")
    pre_first, pre_last = (float(om.loc[om["k"] < 0, "coef"].iloc[i]) for i in (0, -1))
    stats["speed_outer"].update({"pre_first_month_coef": pre_first,
                                 "pre_last_month_coef": pre_last})
    t4f = (f"Within-CBD speed {_pct_str(spd['coef'])} vs the donut, {_pct_str(so_m['coef'])} "
           f"vs Brooklyn/Queens; that gap fell from {_pct_str(pre_first)} to "
           f"{_pct_str(pre_last)} before the policy; both fail the pre-trend test")
    ser = {o: [("vs donut control (pre-registered)", sm[(sm["outcome"] == o)
                                                         & (sm["control"] == "donut")],
                PALETTE["cbd"]),
               ("vs Brooklyn/Queens (C4)", sm[(sm["outcome"] == o) & (sm["control"] == "outer")],
                PALETTE["comparison"])] for o in ("log_mean_speed_mph", "log_mean_duration_min")}
    f4f_speed_event_study(
        [("Speed (%)", ser["log_mean_speed_mph"]),
         ("Duration (%)", ser["log_mean_duration_min"])],
        policy, t4f, "Pair-week means of trips with pickup and dropoff in the CBD vs pairs within "
        "the donut control or with both ends in Brooklyn/Queens (no airports); pair and week FE, "
        "weather x treated, weighted by trips; 95% CIs two-way clustered by pickup and dropoff "
        "zone; lighter points = before the policy. Sources: results/speed_event_study.csv, "
        "results/speed_did_outer.json.", figs / "F4f_speed_event_study")

    em = pd.read_csv(res / "effect_map.csv")
    min_pre = float(cfg["causal"]["effect_map_min_pre_weekly"])
    cbd_rel = em.loc[em["is_cbd"] & (em["pre_mean_weekly"] >= min_pre),
                     "relative_to_control_aggregate"]
    stats["effect_map"] = {"cbd_median_relative": float(cbd_rel.median()),
                           "min_pre_weekly": min_pre}
    t4b = (f"CBD zones: median post/pre change in weekly pickups "
           f"{_pct_str(float(cbd_rel.median()))} relative to the control group's aggregate change")
    zones = load_zones(path("raw_lookup", cfg) / "taxi_zones.shp")
    f4b_effect_map(zones, em, t4b, "Manhattan zones; log(mean weekly pickups after / in the 52 "
                   "weeks before 2025-01-05) minus the same for the donut control's total "
                   f"pickups. Hatched: < {min_pre:.0f} pickups per week before. Red outline: "
                   "CBD. Source: results/effect_map.csv.", figs / "F4b_effect_map", min_pre,
                   float(cfg["causal"]["effect_map_colour_quantile"]))
    f4b_effect_map_html(zones, em, t4b, figs / "F4b_effect_map.html", min_pre,
                        float(cfg["causal"]["effect_map_colour_quantile"]))

    het = pd.read_csv(res / "heterogeneity.csv")
    sh = pd.read_csv(res / "speed_heterogeneity.csv")
    panels = []
    names = {"hour_band": "Demand: hour band", "day_type": "Demand: weekday / weekend",
             "dropoff": "Demand: CBD pickups by dropoff", "distance_tercile":
             "Demand: distance tercile", "fare_tercile": "Demand: fare tercile",
             "pass_through": "Demand: pass-through (A1)"}
    hw = het[het["spec"] == "pre_volume_weighted"]
    for cut, name in names.items():
        d = hw[hw["cut"] == cut].assign(label=lambda x: x["level"].map(_label))
        panels.append((name, d))
    for cut, name in (("hour_band", "Speed: hour band"), ("dist_tercile",
                                                          "Speed: distance tercile")):
        d = sh[(sh["outcome"] == "log_mean_speed_mph") & (sh["cut"] == cut)
               & (sh["control"] == "donut")]
        panels.append((name, d.assign(label=d["level"].map(_label))))
    sub = hw[hw["cut"].isin(list(names)[:5])]
    dzero = int(((sub["ci_lo"] < 0) & (sub["ci_hi"] > 0)).sum())
    dn = len(sub)
    shd = sh[(sh["outcome"] == "log_mean_speed_mph") & (sh["control"] == "donut")]
    szero = int(((shd["ci_lo"] < 0) & (shd["ci_hi"] > 0)).sum())
    sn = len(shd)
    stats["heterogeneity"] = {"demand_ci_includes_zero": dzero, "demand_n": dn,
                              "speed_ci_includes_zero": szero, "speed_n": sn}
    t4c = (f"95% CI includes zero in {dzero} of {dn} trip subsets for weighted demand and in "
           f"{szero} of {sn} for within-CBD speed (vs the donut)")
    f4c_heterogeneity(panels, t4c, "Static DiD (%) with 95% CIs on sub-panels; demand: "
                      "log1p(weekly pickups of the subset) per zone, CBD vs donut control, zones "
                      "weighted by their pre-period count of the subset (pass-through: "
                      "control-zone trips ending in the CBD vs ending outside it); speed: log "
                      "mean trip speed of within-CBD vs within-donut pairs (pre-registered). "
                      "Sources: results/heterogeneity.csv (spec pre_volume_weighted), "
                      "results/speed_heterogeneity.csv.", figs / "F4c_heterogeneity")

    cf = pd.read_csv(res / "counterfactual.csv")
    post = cf[~cf["in_sample"]]
    cf_mean = float(post["mean_daily_rel"].mean())
    stats["counterfactual"] = {"mean_post_monthly_rel": cf_mean,
                               "did_main_post_mean": yr["post"],
                               "did_weighted_post_mean": float(
                                   w_es.loc[w_es["k"] >= 0, "coef"].mean())}
    t4d = (f"After the policy, CBD pickups averaged {cf_mean * 100:+.1f}% against the frozen "
           f"forecast, while the event-study paths say {_pct_str(yr['post'])} (pre-registered) and "
           f"{_pct_str(stats['counterfactual']['did_weighted_post_mean'])} (volume-weighted)")
    f4d_counterfactual_vs_did(
        cf, [("DiD, volume-weighted (primary)", w_es, PALETTE["cbd"]),
             ("DiD, pre-registered", main_es, PALETTE["comparison"])], policy, t4d,
        "Counterfactual: mean over days of (actual - forecast) / forecast of CBD daily pickups, "
        "frozen LightGBM (trained to 2024-12-31; 2024 months in-sample, lighter). DiD: monthly "
        "event-study coefficients as exp(b) - 1; the volume-weighted path is not "
        "pre-registered. Sources: results/counterfactual.csv, results/event_study.csv.",
        figs / "F4d_counterfactual_vs_did")

    dpl = pd.read_csv(res / "demand_placebo_draws.csv")
    dp = dpl[dpl["spec"] == "pre_volume_weighted"]["coef"]
    spl = pd.read_csv(res / "speed_placebo.csv")
    spw = json.loads((res / "speed_power.json").read_text())["by_control"]
    pww = pw["pre_volume_weighted"]
    sd_, so_ = (spw[c]["outcomes"]["log_mean_speed_mph"] for c in ("donut", "outer"))
    stats["permutation"] = {k: {"beta": v["real_beta"], "mde": v["mde"], "mean": v["mean"],
                                "share": v["share_abs_ge_abs_beta"]}
                            for k, v in (("demand_weighted", pww), ("speed_donut", sd_),
                                         ("speed_outer", so_))}
    t4e = (f"Permutation placebos: weighted demand {pww['real_beta']:+.3f} ("
           f"{pww['share_abs_ge_abs_beta'] * 100:.0f}% of placebos as large, MDE "
           f"{pww['mde']:.3f}); speed vs donut {sd_['real_beta']:+.3f} ("
           f"{sd_['share_abs_ge_abs_beta'] * 100:.0f}%, MDE {sd_['mde']:.3f}); vs Brooklyn/Queens "
           f"the placebos themselves centre on {so_['mean']:+.3f}")

    def draws(c):
        return spl[(spl["control"] == c) & (spl["outcome"] == "log_mean_speed_mph")]["coef"]

    f4e_placebo_distribution(
        [("Demand, volume-weighted (primary)", dp, pww["real_beta"], pww["mde"]),
         ("Speed vs donut (pre-registered)", draws("donut"), sd_["real_beta"], sd_["mde"]),
         ("Speed vs Brooklyn/Queens (C4)", draws("outer"), so_["real_beta"], so_["mde"])], t4e,
        "Amendment 1 (A2): 500 draws on pre-policy weeks 2023-01 to 2025-01-04, each with a "
        "random fake policy week and 38 random Manhattan zones as fake CBD (speed: pairs within "
        "the fake set vs the other Manhattan zones' pairs, or vs the fixed Brooklyn/Queens "
        "pairs); demand placebos with weather x treated, as the real estimate; grey band = +- MDE "
        "at 80% power / 5% size; red line = the real estimate. "
        "Sources: results/power_mde.json, results/speed_power.json.",
        figs / "F4e_placebo_distribution")

    loo = pd.read_csv(res / "leave_one_out.csv")
    lw = ds["leave_one_zone_out_pre_volume_weighted"]
    stats["leave_one_out"] = {"equal_weight": ds["leave_one_zone_out"], "pre_volume_weighted": lw}
    t4i = (f"Leave one zone out: weighted {_pct_str(lw['min'])} to {_pct_str(lw['max'])}; "
           f"equal-weight (pre-registered) {_pct_str(ds['leave_one_zone_out']['min'])} to "
           f"{_pct_str(ds['leave_one_zone_out']['max'])}")
    f4i_leave_one_out(loo, {"equal_weight": ds["main"]["terms"]["treated_post"]["coef"],
                            "pre_volume_weighted": bw["coef"]}, t4i,
                      "Static DiD of log1p(weekly pickups), CBD vs donut control, re-estimated "
                      f"without each zone (dots: {ds['leave_one_zone_out']['n']} equal-weight, "
                      f"{lw['n']} weighted — zones without pre-period pickups carry no weight) "
                      "and on all zones (bar). Source: "
                      "results/leave_one_out.csv, results/did_static.json.",
                      figs / "F4i_leave_one_out")
    for k, v in (("t4", t4), ("t4b", t4b), ("t4c", t4c), ("t4d", t4d), ("t4e", t4e),
                 ("t4f", t4f), ("t4i", t4i)):
        stats[f"title_{k}"] = v
    (res / "figure_stats_phase4.json").write_text(json.dumps(stats, indent=2, default=float)
                                                  + "\n")
    logging.info("wrote F4, F4b, F4c, F4d, F4e, F4f, F4i to %s", figs)


def phase4b(cfg: dict) -> None:
    """Amendment 3 figures whose results exist: F4g (C1)."""
    res, figs = path("results", cfg), path("figures", cfg)
    stats: dict = {}
    f = res / "app_dispatch_summary.json"
    if f.exists():
        sm = json.loads(f.read_text())
        share = pd.read_csv(res / "app_dispatch_share.csv")
        g, c = sm["groups"], sm["correlation_growth_vs_app_share"]
        fast = share[share["is_donut_control"]].nlargest(5, "growth_log")
        stats["c1"] = {"cbd_pooled": g["cbd"]["share_app_pooled"],
                       "donut_pooled": g["donut_control"]["share_app_pooled"],
                       "cbd_median_zone": g["cbd"]["share_app_median_zone"],
                       "fastest_donut_zones_share_range": [float(fast["share_app"].min()),
                                                           float(fast["share_app"].max())],
                       "r_manhattan": c["manhattan"]["pearson_r"], "r_all": c["all_zones"][
                           "pearson_r"]}
        t = (f"The fastest-growing donut-control zones are "
             f"{fast['share_app'].min() * 100:.0f}-{fast['share_app'].max() * 100:.0f}% "
             f"Uber/Lyft-dispatched vs a CBD median of "
             f"{g['cbd']['share_app_median_zone'] * 100:.0f}%; growth vs app share "
             f"r = {c['manhattan']['pearson_r']:.2f} in Manhattan")
        stats["c1"]["title"] = t
        zones = load_zones(path("raw_lookup", cfg) / "taxi_zones.shp")
        f4g_app_dispatch(zones, share, t,
                         f"request_source of yellow records {sm['months'][0]} to "
                         f"{sm['months'][1]} (HV0003 Uber, HV0005 Lyft from 2026-08; other codes "
                         f"undocumented, not counted); hatched: < {sm['min_trips']} records. "
                         "Growth: log of 2025 / 2023 mean weekly pickups (zones with >= "
                         f"{sm['min_weekly_base']} in 2023). Sources: "
                         "results/app_dispatch_share.csv, results/app_dispatch_summary.json.",
                         figs / "F4g_app_dispatch_map")
    f = res / "shock_comparison.json"
    if f.exists():
        sc = json.loads(f.read_text())["events"]
        names = {"covid": "COVID-19, 2020-03-01", "fare_increase":
                 "Metered-fare increase (+23%), 2022-12-19", "congestion_pricing":
                 "Congestion pricing, 2025-01-05"}
        evs, parts, c5 = [], [], {}
        for key, ev in sc.items():
            g = ev["groups"]["cbd"]
            alarm = g["cusum"]["first_alarm"]
            lvl = g["post_event_level"]["first_28_days"]["pct"]
            c5[key] = {"cusum_first_alarm": alarm, "first_28_days_pct": lvl}
            evs.append((key, f"{names.get(key, key)}: CBD {lvl * 100:+.0f}% vs forecast in the "
                        "first 4 weeks", alarm))
            when = (f"day {alarm['delay_days']}" if alarm else "no alarm")
            parts.append(f"{names.get(key, key).split(',')[0]} {when}")
        stats["c5"] = c5
        t = "One CUSUM monitor, three shocks (CBD): " + "; ".join(parts)
        stats["c5"]["title"] = t
        daily = pd.read_csv(res / "shock_daily.csv", parse_dates=["day"])
        f3b_three_shocks(daily, evs, t, "Frozen LightGBM trained on the 12 months before each "
                         "event, day-ahead forecasts for 12 months from it; calibration year = "
                         "two-fold cross-fit out-of-sample residuals; 7-day means of the daily "
                         "log(actual / forecast). Sources: results/shock_comparison.json, "
                         "results/shock_daily.csv.", figs / "F3b_three_shocks")
    f = res / "synth_control.json"
    if f.exists():
        sc = json.loads(f.read_text())
        sp_ = sc["in_space_placebos"]
        stats["c3"] = {"post_gap_mean_pct": sc["post_gap_mean_pct"],
                       "pre_rmspe": sc["pre_rmspe"], "ratio": sc["post_pre_rmspe_ratio"],
                       "rank": sp_["cbd_rank"], "n_units": sp_["n"] + 1,
                       "p_value": sp_["p_value"], "resolves": sc["resolves"]}
        stats["c3"]["can_speak"] = sc["can_speak"]
        it = sc["in_time_placebo"]["post_gap_mean_pct"] * 100
        verdict = ("the method can speak" if sc["resolves"] and sc["can_speak"]
                   else "the method cannot resolve the question")
        t = (f"Synthetic control: CBD pickups {sc['post_gap_mean_pct'] * 100:+.1f}% vs synthetic "
             f"after the policy, rank {sp_['cbd_rank']} of {sp_['n'] + 1} donors "
             f"(p = {sp_['p_value']:.2f}), and {it:+.1f}% at a fake 2024 date: {verdict}")
        stats["c3"]["title"] = t
        paths = pd.read_csv(res / "synth_control_paths.csv", parse_dates=["week_start"])
        f4h_synth_control(paths, cfg["data"]["policy_date"], t,
                          f"Weekly total pickups of the {sc['n_cbd_zones']} CBD zones vs a "
                          f"weighted combination of {sc['n_donors']} donor zones "
                          f"({sc['donor_rule']}), fitted on log pickups demeaned over "
                          f"{sc['pre_period'][0]} to "
                          f"{sc['pre_period'][1]} (pysyncon, equal weight per pre week); grey: "
                          "every donor in turn as a placebo. Sources: "
                          "results/synth_control.json, results/synth_control_paths.csv.",
                          figs / "F4h_synth_control")
    if stats:
        (res / "figure_stats_phase4b.json").write_text(json.dumps(stats, indent=2) + "\n")
        logging.info("wrote Phase-4b figures: %s", ", ".join(stats))


def _k(v: float) -> str:
    return f"{v / 1000:+,.1f}k"


def phase4c(cfg: dict) -> None:
    """Amendment 4 figures whose results exist: F6a, F6b (D1)."""
    res, figs = path("results", cfg), path("figures", cfg)
    stats: dict = {}
    f = res / "channel_decomposition.csv"
    if f.exists():
        dec = pd.read_csv(f)
        weekly = pd.read_csv(res / "channel_weekly.csv", parse_dates=["week_start"])

        def row(g, incl, comp="2023_to_2025"):
            return dec[(dec["comparison"] == comp) & (dec["zone_group"] == g)
                       & (dec["with_cmt_block"] == incl)].iloc[0]

        c, o = row("cbd", True), row("other", False)
        stats["d1"] = {"cbd": c[["app_change", "street_change", "change"]].to_dict(),
                       "other_excl_block": o[["app_change", "street_change", "change"]].to_dict()}
        t = (f"2023 to 2025, per week: CBD app trips {_k(c['app_change'])}, street hails "
             f"{_k(c['street_change'])}; outer boroughs (without the CMT block) app "
             f"{_k(o['app_change'])}, street hails {_k(o['street_change'])}")
        stats["d1"]["title_f6a"] = t
        f6a_channel_areas(weekly, [("cbd", "CBD (38 zones)"),
                                   ("other", "Outer boroughs (no airports)")], t,
                          "Valid yellow pickups per complete week by channel: app = any e-hail "
                          "app (Flex Fare before 2026-06, request_source not NULL from 2026-06; "
                          "Amendment 4a), street = street hail; grey = VendorID 1 contracted "
                          "trips in the outer boroughs, ended 2026-05 (DECISIONS, D1). Own y-axis "
                          "per panel; dashed line = congestion pricing 2025-01-05. Sources: "
                          "results/channel_weekly.csv, results/channel_decomposition.csv.",
                          figs / "F6a_channel_areas")
        zs = pd.read_csv(res / "channel_zone_share.csv").merge(
            pd.read_csv(res / "zone_summary.csv")[["zone_id", "is_cbd"]], on="zone_id")
        min_w = float(cfg["channel"]["map_min_weekly"])
        med = {p: float(x.loc[x["mean_weekly_pickups"] >= min_w, "app_share_excl_block"].median())
               for p, x in zs.groupby("period")}
        stats["d1"]["zone_median_app_share"] = med
        t2 = (f"Median zone app share of pickups: {med['2023'] * 100:.0f}% (2023), "
              f"{med['2024'] * 100:.0f}% (2024), {med['2025'] * 100:.0f}% (2025), "
              f"{med['2026_jan_sep'] * 100:.0f}% (Jan-Sep 2026)")
        stats["d1"]["title_f6b"] = t2
        zones = load_zones(path("raw_lookup", cfg) / "taxi_zones.shp")
        f6b_app_share_maps(zones, zs, [("2023", "2023"), ("2024", "2024"), ("2025", "2025"),
                                       ("2026_jan_sep", "Jan-Sep 2026")], min_w, t2,
                           f"App share = app pickups / (app + street-hail pickups) per pickup "
                           f"zone, the CMT contracted block excluded; hatched: < {min_w:.0f} "
                           "pickups per week in that period; CBD outlined. Medians over the "
                           "non-hatched zones. Source: results/channel_zone_share.csv.",
                           figs / "F6b_app_share_maps")
    f = res / "incrementality_panel_summary.csv"
    if f.exists():
        sm = pd.read_csv(f)
        inc = json.loads((res / "incrementality_dml.json").read_text())

        def th(a):
            return inc["areas"][a]["dml_plr"]

        stats["d2"] = {a: th(a) for a in ("cbd", "manhattan_non_cbd", "other")}
        c, o = th("cbd"), th("other")
        cb = sm[sm["area"] == "cbd"]
        stats["d2"]["cbd_range"] = [float(cb["theta"].min()), float(cb["theta"].max())]
        # wording: Amendment 5 (D2)
        t = (f"Share of app trips that are additional: CBD estimates range from "
             f"{cb['theta'].min():.2f} to {cb['theta'].max():.2f} across estimators (primary DML "
             f"{c['theta']:.2f} [{c['theta_ci'][0]:.2f}, {c['theta_ci'][1]:.2f}]); they disagree "
             "beyond their intervals: not identified")
        stats["d2"]["title"] = t
        est = [("dml_plr", "DML, time-blocked folds (primary)", PALETTE["app"]),
               ("dml_zone_trends", "DML + zone trends", PALETTE["comparison"]),
               ("dml_panel_plpr", "DoubleML panel (median of 25 fold draws)", PALETTE["model"]),
               ("twfe", "TWFE", PALETTE["non_cbd"]),
               ("first_difference", "First differences", PALETTE["baseline"])]
        f6c_incrementality(sm, [("cbd", "CBD"), ("manhattan_non_cbd", "Manhattan non-CBD"),
                                ("other", "Outer boroughs")], est, t,
                           "theta = 1 + d street hails / d app pickups per zone-week (1 = every "
                           "app trip is additional, 0 = every app trip replaces a street hail); "
                           "observational. Zones with >= 20 pickups/week in 2023; 2023-01 to "
                           "2026-09; CMT contracted block excluded; 95% CIs clustered by zone. "
                           "Airports (2 zones) not shown. Sources: results/incrementality_dml.json,"
                           " results/incrementality_panel_summary.csv.",
                           figs / "F6c_incrementality")
    f = res / "lyft_entry.json"
    if f.exists():
        ly = json.loads(f.read_text())
        pr, lg = ly["primary_clean_windows"], ly["log_specification"]["clean_windows"]
        stats["d3"] = {"levels_incrementality": pr["incrementality"],
                       "log_incrementality": lg["incrementality"],
                       "log_incrementality_ci": lg["incrementality_ci"],
                       "log_pretrend_p": lg["pretrend"]["total"]["p_F_hotelling"]}
        t = (f"Lyft on Curb cabs (preliminary): incrementality {pr['incrementality']:.2f} in "
             f"levels, {lg['incrementality']:.2f} [{lg['incrementality_ci'][0]:.2f}, "
             f"{lg['incrementality_ci'][1]:.2f}] in logs, whose pre-trend test rejects: not "
             "identified yet")
        stats["d3"]["title"] = t
        daily = pd.read_csv(res / "lyft_entry_daily.csv", parse_dates=["day"])
        f6d_lyft_entry(daily, ly["windows"], t,
                       "Weekly pickups of Curb (VendorID 2) and CMT (VendorID 1) cabs in the CBD "
                       "and Manhattan non-CBD, each indexed to its mean over the 8 weeks to "
                       f"{ly['windows']['pre_end']}; grey band = {ly['windows']['secondary_start']}"
                       f" to {ly['windows']['post_start']} (excluded from the primary windows; "
                       "Curb code-A surge). Incrementality = DiD change in Curb total pickups / "
                       "Lyft pickups per Curb zone-day. Sources: results/lyft_entry.json, "
                       "results/lyft_entry_daily.csv.", figs / "F6d_lyft_entry")
    f = res / "fhv_did.json"
    if f.exists():
        fh = json.loads(f.read_text())
        fes = pd.read_csv(res / "fhv_event_study.csv")
        yes = pd.read_csv(res / "event_study.csv")
        y_w = yes[(yes["bins"] == "month")
                  & (yes["spec"] == "pre_volume_weighted_not_preregistered")]
        f_w = fes[(fes["series"] == "fhv_all") & (fes["weighting"] == "pre_volume_weighted")]
        pf_ = {s: fh["series"][s]["pre_volume_weighted"]["pretrend"]["p_F_hotelling"]
               for s in fh["series"]}
        p_y = json.loads((res / "placebo.json").read_text())["pretrend_tests"][
            "event_study_month_pre_volume_weighted_not_preregistered"]["pretrend"][
            "p_F_hotelling"]
        stats["c6"] = {"fhv_pretrend_p_hotelling_weighted": pf_, "yellow_pretrend_p": p_y,
                       "any_estimate": any(v.get("passes") for s in fh["series"].values()
                                           for v in s.values())}
        t = (r"Taxi (\$0.75 fee) vs FHV (\$1.50 fee) in the CBD: both pre-trend tests "
             f"reject (yellow p = {p_y:.1g}, Uber + Lyft p = {pf_['fhv_all']:.1g}), so no "
             "effect is estimated")
        stats["c6"]["title"] = t
        f6_taxi_vs_fhv([("Yellow taxi (Phase 4 primary)", y_w, PALETTE["cbd"]),
                        ("Uber + Lyft (HVFHV)", f_w, PALETTE["comparison"])],
                       cfg["data"]["policy_date"], t,
                       "Monthly event-study coefficients as exp(b) - 1, 38 CBD zones vs the donut "
                       "control, zone and week FE, weather x treated, zones weighted by their own "
                       "series' pre-period volume, 95% CIs clustered by zone; reference: the week "
                       "before 2025-01-05; lighter = before the policy. Descriptive only (C6: "
                       "pre-trend test first). Sources: results/fhv_did.json, "
                       "results/fhv_event_study.csv, results/event_study.csv.",
                       figs / "F6_taxi_vs_fhv")
    f = res / "app_share_policy_step.json"
    if f.exists():
        st = json.loads(f.read_text())
        bt = st["yellow"]["d0_step_by_trip_type"]["by_type"]
        po = st["yellow"]["pooled"]["app_share"]
        stats["d5b"] = {"step_pp": {k: v["step_pp"] for k, v in bt.items()}, "pooled": po}
        pp = st["yellow"]["pretrend"]["app_share"]["p_F_hotelling"]
        stats["d5b"]["pretrend_p_hotelling"] = pp
        t = (f"App-share step at 2025-01-19: {bt['within']['step_pp']:+.1f} pp within the CBD, "
             f"{bt['into']['step_pp']:+.1f} into, {bt['out_of']['step_pp']:+.1f} out of, "
             f"{bt['neither']['step_pp']:+.1f} for trips touching neither end; the DiD "
             f"({po['coef'] * 100:+.1f} pp) fails its pre-trend test (p = {pp:.0e})")
        stats["d5b"]["title"] = t
        f6e_app_share_step(pd.read_csv(res / "app_share_by_trip_type_weekly.csv",
                                       parse_dates=["week_start"]),
                           pd.read_csv(res / "app_share_step_event_study.csv"), t,
                           "Left: weekly app share of valid yellow pickups by trip type vs the "
                           "CBD (60th St rule), CMT contracted block excluded. Right: event study "
                           "on pickup zone x trip type x week cells, CBD-touching (within, into, "
                           "out of) minus neither, weighted by cell trips, cell and week FE, 95% "
                           "CIs clustered by pickup zone; reference: the week before 2025-01-05. "
                           "Steps: 4 weeks after vs 4 before 2025-01-19. Sources: "
                           "results/app_share_policy_step.json, "
                           "results/app_share_by_trip_type_weekly.csv, "
                           "results/app_share_step_event_study.csv.", figs / "F6e_app_share_step")
    if stats:
        (res / "figure_stats_phase4c.json").write_text(json.dumps(stats, indent=2,
                                                                  default=float) + "\n")
        logging.info("wrote Phase-4c figures: %s", ", ".join(stats))


STRATEGY_LABELS = {"s0": "S0 frozen", "s1": "S1 monthly retrain", "s4": "S4 Chronos-2",
                   "s6": "S6 channel-aware"}


def phase5(cfg: dict) -> None:
    """F5 (Phase 5, D6) from results/adaptation_daily.csv, adaptation_summary.json and
    adaptation_gaps.csv; title numbers saved to results/figure_stats_phase5.json."""
    res, figs = path("results", cfg), path("figures", cfg)
    if not (res / "adaptation_summary.json").exists():
        logging.warning("results/adaptation_summary.json missing: F5 skipped")
        return
    ac = cfg["adapt"]
    summ = json.loads((res / "adaptation_summary.json").read_text())
    gaps = pd.read_csv(res / "adaptation_gaps.csv")
    daily = pd.read_csv(res / "adaptation_daily.csv", parse_dates=["day"])
    head, bias = summ["headline"], summ["bias_pct_of_pickups"]
    names = summ["strategies"]
    best = min(names, key=lambda k: head[f"{k}|all"]["wape"])

    def gap(m: str, ref: str, g: str = "all") -> dict:
        r = gaps[(gaps["zone_group"] == g) & (gaps["model"] == m) & (gaps["reference"] == ref)]
        return {k: float(r.iloc[0][k]) for k in ("gap", "gap_ci_lo", "gap_ci_hi")} | {
            "distinguishable": bool(r.iloc[0]["distinguishable"])}

    stats = {"source_files": ["results/adaptation_summary.json", "results/adaptation_gaps.csv",
                              "results/adaptation_daily.csv"],
             "eval_window": summ["eval_window"], "lowest_wape_all": best,
             "wape_all": {k: head[f"{k}|all"]["wape"] for k in names},
             "bias_pct_all": {k: bias[f"{k}|all"] for k in names},
             "bias_pct_cbd": {k: bias[f"{k}|cbd"] for k in names},
             "gap_vs_s0_all": {k: gap(k, "s0") for k in names if k != "s0"}}
    w, b = stats["wape_all"], stats["bias_pct_all"]
    span = "–".join(pd.Timestamp(x).strftime("%b %Y") for x in summ["eval_window"])
    if best == "s1" and b["s6"] < b["s0"]:
        title = (f"{span}: monthly retraining has the lowest day-ahead error (WAPE "
                 f"{w['s1'] * 100:.1f}% vs {w['s0'] * 100:.1f}% frozen); app-share features "
                 f"deepen the under-forecast (bias {b['s6']:.1f}% vs {b['s0']:.1f}% frozen)")
    else:
        title = (f"{span}: lowest day-ahead error {STRATEGY_LABELS[best]} "
                 f"(WAPE {w[best] * 100:.1f}%)")
    stats["title"] = title
    series = [("s0", STRATEGY_LABELS["s0"], PALETTE["baseline"]),
              ("s1", STRATEGY_LABELS["s1"], PALETTE["model"]),
              ("s4", STRATEGY_LABELS["s4"], PALETTE["foundation"]),
              ("s6", STRATEGY_LABELS["s6"], PALETTE["app"])]
    series = [x for x in series if x[0] in names]
    note = (f"Day-ahead hourly forecasts; metrics on origins {summ['eval_window'][0]} to "
            f"{summ['eval_window'][1]} (unshaded); each line starts at its strategy's first "
            f"origin (S1/S6 from {ac['run_start'][:7]}, S0 and S4 from "
            f"{cfg['shock']['forecast_window'][0][:7]}); trailing {ac['rolling_days']}-day sums "
            "of absolute "
            "error (WAPE) and signed error (forecast minus actual; negative = under-forecast) "
            "over actual pickups. S1/S6: LightGBM refit on the first of each month on a sliding "
            "24-month window; S6 adds trailing app-share features; S4: Chronos-2 zero-shot, "
            "weather_past. Sources: results/adaptation_daily.csv, results/adaptation_summary.json,"
            " results/adaptation_gaps.csv.")
    f5_adaptation(daily, series, int(ac["rolling_days"]), tuple(cfg["shock"]["forecast_window"]),
                  summ["eval_window"][0], title, note, figs / "F5_adaptation")
    (res / "figure_stats_phase5.json").write_text(json.dumps(stats, indent=2) + "\n")
    logging.info("wrote F5 to %s", figs)


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
    phase4(cfg)
    phase4b(cfg)
    phase4c(cfg)
    phase5(cfg)


if __name__ == "__main__":
    main()
