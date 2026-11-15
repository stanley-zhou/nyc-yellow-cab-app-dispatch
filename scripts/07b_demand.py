"""Phase 4, steps 2-3: demand DiD (pickups), event study, checks, MDE and heterogeneity.

Panel: dbt `fct_weekly_zone_panel` (+ `fct_weekly_zone_trip_stats`, `fct_weekly_zone_vendor`),
complete weeks inside data.event_study_window. Treated = CBD zones, primary control = the donut
(`causal.control`). Outcome log1p(pickups) (and pickups in levels); zone FE + week FE; weather
enters as weather x treated; SEs clustered by zone. Reads those tables from
data/warehouse.duckdb, results/zone_summary.csv and config `causal`, `panel`.

Writes
    results/did_static.json     main estimate, persistence split, levels, without weather,
                                treated-seasonality (not pre-registered), alternative controls,
                                vendors present throughout (CMT + Curb), PLAN-literal filters,
                                leave-one-zone-out summary
    results/event_study.csv     monthly and weekly event-study coefficients (+ the
                                pre-volume-weighted monthly path, not pre-registered)
    results/placebo.json        pre-trend joint tests, placebo in time, leave-one-zone-out
    results/power_mde.json      permutation-placebo power analysis (PLAN Amendment 1, A2):
                                distribution, share |placebo| >= |beta|, MDE at 80% power /
                                5% size
    results/demand_placebo_draws.csv, results/leave_one_out.csv
    results/placebo_time_distribution.csv  time-only placebos with the real assignment
    results/heterogeneity.csv   static DiD on sub-panels (hour band, weekday/weekend, dropoff in
                                CBD or not, pass-through, distance and fare terciles, airports)

Usage:
    python scripts/07b_demand.py
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.causal.did import SEASONAL, add_seasonal, add_unit_trends, static_did
from taxi_shock.causal.event_study import event_study
from taxi_shock.causal.panel import control_zone_ids, demand_panel
from taxi_shock.causal.placebo import (
    leave_one_out,
    permutation,
    power_summary,
    quick_beta,
    with_fake_policy,
)
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("demand")


def load(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        w = demand_panel(con, cfg)
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    return w, zs


def design(w: pd.DataFrame, zs: pd.DataFrame, cfg: dict, control: str | None = None,
           y_cols: list[str] | None = None) -> pd.DataFrame:
    cbd = set(zs.loc[zs["is_cbd"], "zone_id"])
    ctl = set(control_zone_ids(zs, cfg, control))
    d = w[w["zone_id"].isin(cbd | ctl)].copy()
    d["treated"] = d["zone_id"].isin(cbd).astype(int)
    for c in y_cols or ["pickups"]:
        d[f"log1p_{c}"] = np.log1p(d[c])
    for c in cfg["causal"]["weather_controls"]:
        d[f"tr_{c}"] = d["treated"] * d[c]
    return add_seasonal(d)


def did(d: pd.DataFrame, y: str, cfg: dict, weather: bool = True, extra=(), splits=False,
        post_end=None, weights: str | None = None) -> dict:
    cc = cfg["causal"]
    ctrl = [f"tr_{c}" for c in cc["weather_controls"]] if weather else []
    return static_did(d, y, "zone_id", ["zone_id"], cc["pre_weeks"], controls=[*ctrl, *extra],
                      post_splits=cc["post_splits"] if splits else None,
                      post_end=post_end, weights=weights).to_dict()


def add_pre_volume_weight(d: pd.DataFrame, pre_weeks: int, col: str = "pickups",
                          unit: str = "zone_id") -> pd.DataFrame:
    """w_pre = the unit's mean weekly `col` over the static pre window (fixed per unit): the
    weighted DiD estimates the effect on the aggregate (the primary demand specification set at
    Checkpoint 4, PLAN C2; not pre-registered)."""
    pre = d[d["event_week"].between(-pre_weeks, -1)].groupby(unit)[col].mean()
    out = d.assign(w_pre=d[unit].map(pre).fillna(0.0))
    return out[out["w_pre"] > 0]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    cc, res, policy = cfg["causal"], path("results", cfg), cfg["data"]["policy_date"]
    w, zs = load(cfg)
    ycols = ["pickups", "pickups_cmt_curb", "pickups_literal"]
    d = design(w, zs, cfg, y_cols=ycols)
    ctrl = [f"tr_{c}" for c in cc["weather_controls"]]
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "outcome": "log1p(weekly pickups) per zone", "control": cc["control"],
           "n_treated_zones": int(d.loc[d["treated"] == 1, "zone_id"].nunique()),
           "n_control_zones": int(d.loc[d["treated"] == 0, "zone_id"].nunique()),
           "pre_mean_weekly_pickups_treated": float(
               d.loc[(d["treated"] == 1) & d["event_week"].between(-cc["pre_weeks"], -1),
                     "pickups"].mean()),
           "estimates": {}}
    e = out["estimates"]
    e["main"] = did(d, "log1p_pickups", cfg)
    e["persistence"] = did(d, "log1p_pickups", cfg, splits=True)
    e["levels"] = did(d, "pickups", cfg)
    e["without_weather"] = did(d, "log1p_pickups", cfg, weather=False)
    e["treated_seasonality_not_preregistered"] = did(d, "log1p_pickups", cfg, extra=SEASONAL)
    e["treated_seasonality_persistence_not_preregistered"] = did(
        d, "log1p_pickups", cfg, extra=SEASONAL, splits=True)
    dw = add_pre_volume_weight(d, cc["pre_weeks"])
    e["pre_volume_weighted_not_preregistered"] = did(dw, "log1p_pickups", cfg, weights="w_pre")
    e["pre_volume_weighted_persistence_not_preregistered"] = did(
        dw, "log1p_pickups", cfg, weights="w_pre", splits=True)
    dt, trends = add_unit_trends(d, "zone_id")
    e["zone_trends_not_preregistered"] = did(dt, "log1p_pickups", cfg, extra=trends)
    dwt, trends_w = add_unit_trends(dw, "zone_id")
    e["pre_volume_weighted_zone_trends_not_preregistered"] = did(
        dwt, "log1p_pickups", cfg, weights="w_pre", extra=trends_w)
    e["vendors_present_throughout_cmt_curb"] = did(d, "log1p_pickups_cmt_curb", cfg)
    e["plan_literal_filters"] = did(d, "log1p_pickups_literal", cfg)
    for c in [*cc["control_robustness"], "outer_boroughs_with_airports"]:
        e[f"control_{c}"] = did(design(w, zs, cfg, control=c), "log1p_pickups", cfg)
    # PLAN's checks on the weighted (primary, C2) specification too (review round 2)
    e["pre_volume_weighted_without_weather"] = did(dw, "log1p_pickups", cfg, weather=False,
                                                   weights="w_pre")
    for col, key in (("pickups_cmt_curb", "vendors_present_throughout_cmt_curb"),
                     ("pickups_literal", "plan_literal_filters")):
        e[f"pre_volume_weighted_{key}"] = did(add_pre_volume_weight(d, cc["pre_weeks"], col=col),
                                              f"log1p_{col}", cfg, weights="w_pre")
    for c in [*cc["control_robustness"], "outer_boroughs_with_airports"]:
        e[f"pre_volume_weighted_control_{c}"] = did(
            add_pre_volume_weight(design(w, zs, cfg, control=c), cc["pre_weeks"]),
            "log1p_pickups", cfg, weights="w_pre")
    out["primary"] = "pre_volume_weighted_not_preregistered"
    out["primary_note"] = ("C2 (Checkpoint 4, Amendment 3): the pre-volume-weighted estimate is "
                           "primary; `main` is the pre-registered equal-weight estimate")
    b = e["main"]["terms"]["treated_post"]
    LOG.info("demand main: %.4f [%.4f, %.4f]", b["coef"], b["ci_lo"], b["ci_hi"])

    # event studies (+ the pre-volume-weighted monthly path)
    rows, tests = [], {}
    for unit in ("month", "week"):
        t, info = event_study(d, "log1p_pickups", "zone_id", ["zone_id"], policy, unit,
                              controls=ctrl)
        rows.append(t.assign(spec="main", bins=unit))
        tests[f"event_study_{unit}"] = info
    # (no treated-seasonality event study: monthly event bins x treated already span treated x
    # calendar month, so that variant is identical to the main one; it exists only as a static
    # DiD)
    t, info = event_study(dw, "log1p_pickups", "zone_id", ["zone_id"], policy, "month",
                          weights="w_pre", controls=ctrl)
    rows.append(t.assign(spec="pre_volume_weighted_not_preregistered", bins="month"))
    tests["event_study_month_pre_volume_weighted_not_preregistered"] = info
    pd.concat(rows, ignore_index=True).to_csv(res / "event_study.csv", index=False,
                                              lineterminator="\n", float_format="%.6g")
    LOG.info("pre-trend p(F) monthly: %.4f", tests["event_study_month"]["pretrend"]["p_F"])

    # placebo in time (2023-2024 only, fake policy week causal.placebo_week)
    plo, phi = (pd.Timestamp(x) for x in cc["placebo_window"])
    pdat = d[(d["week_start"] >= plo) & (d["week_start"] + pd.Timedelta(days=6) <= phi)]
    pdat = with_fake_policy(pdat, pd.Timestamp(cc["placebo_week"]))
    placebo_time = did(pdat, "log1p_pickups", cfg)
    placebo_time_w = did(add_pre_volume_weight(pdat, cc["pre_weeks"]), "log1p_pickups", cfg,
                         weights="w_pre")

    # leave one zone out
    loo = leave_one_out(d, sorted(d["zone_id"].unique()),
                        lambda x: did(x, "log1p_pickups", cfg)["terms"]["treated_post"]["coef"],
                        ["zone_id"])
    loo_w = leave_one_out(dw, sorted(dw["zone_id"].unique()),
                          lambda x: did(x, "log1p_pickups", cfg, weights="w_pre")["terms"][
                              "treated_post"]["coef"], ["zone_id"])
    pd.concat([loo.assign(spec="equal_weight"), loo_w.assign(spec="pre_volume_weighted")]
              ).to_csv(res / "leave_one_out.csv", index=False, lineterminator="\n",
                       float_format="%.6g")
    loo_sum = {"n": len(loo), "min": float(loo["coef"].min()), "max": float(loo["coef"].max()),
               "median": float(loo["coef"].median()),
               "all_same_sign_as_main": bool((np.sign(loo["coef"]) == np.sign(b["coef"])).all())}
    e["leave_one_zone_out"] = loo_sum
    bw0 = e["pre_volume_weighted_not_preregistered"]["terms"]["treated_post"]["coef"]
    e["leave_one_zone_out_pre_volume_weighted"] = {
        "n": len(loo_w), "min": float(loo_w["coef"].min()), "max": float(loo_w["coef"].max()),
        "median": float(loo_w["coef"].median()),
        "dropped_zone_at_min": int(loo_w.loc[loo_w["coef"].idxmin(), "dropped_zone"]),
        "dropped_zone_at_max": int(loo_w.loc[loo_w["coef"].idxmax(), "dropped_zone"]),
        "all_same_sign_as_main": bool((np.sign(loo_w["coef"]) == np.sign(bw0)).all())}
    (res / "placebo.json").write_text(json.dumps({
        "generated_utc": out["generated_utc"], "pretrend_tests": tests,
        "placebo_in_time": {"fake_policy_week": cc["placebo_week"],
                            "data": cc["placebo_window"], **placebo_time},
        "placebo_in_time_pre_volume_weighted": {"fake_policy_week": cc["placebo_week"],
                                                "data": cc["placebo_window"],
                                                **placebo_time_w},
        "leave_one_zone_out": loo_sum}, indent=2, default=str) + "\n")
    (res / "did_static.json").write_text(json.dumps(out, indent=2, default=str) + "\n")

    # permutation-placebo power analysis (PLAN A2; pre-policy data; 38 random Manhattan zones as
    # fake treatment)
    pc = cc["permutation"]
    lo, hi = (pd.Timestamp(x) for x in pc["window"])
    man = w[w["zone_id"].isin(zs.loc[zs["borough"] == "Manhattan", "zone_id"])]
    pre = man[(man["week_start"] >= lo) & (man["week_start"] + pd.Timedelta(days=6) <= hi)]
    pre = pre.assign(log1p_pickups=np.log1p(pre["pickups"]))
    weeks = sorted(pre["week_start"].unique())
    k = int(pc["min_side_weeks"])
    n_tr = int(zs["is_cbd"].sum())

    wctl = [f"tr_{c}" for c in cc["weather_controls"]]

    def assign(df, fake):
        t = df["zone_id"].isin(fake).astype(int)
        return df.assign(treated=t, **{f"tr_{c}": t * df[c] for c in cc["weather_controls"]})

    # Every placebo is estimated on the specification of the estimate it is compared with
    # (review round 3): the reported estimates have weather x treated; the variants without
    # weather are kept beside them, compared with the real estimates without weather.
    def estimate(df, weather=True):
        return quick_beta(df[df["event_week"] >= -int(pc["pre_weeks"])], "log1p_pickups",
                          "zone_id", controls=wctl if weather else ())

    def estimate_w(df, weather=True):
        """Weighted spec (primary, C2): weights = each zone's mean weekly pickups in the
        placebo's own pre window (<= pre_weeks before the fake week)."""
        x = df[df["event_week"] >= -int(pc["pre_weeks"])]
        wpre = x[x["event_week"] < 0].groupby("zone_id")["pickups"].mean()
        x = x.assign(w_pre=x["zone_id"].map(wpre).fillna(0.0))
        return quick_beta(x[x["w_pre"] > 0], "log1p_pickups", "zone_id", weights="w_pre",
                          controls=wctl if weather else ())

    zones_m = sorted(man["zone_id"].unique())
    fake_weeks = weeks[k:len(weeks) - k + 1]
    # time-only placebos (review round 2): the REAL CBD / donut assignment, the fake policy week
    # moved over the same weeks; this keeps the design's spatial structure, which random zone
    # sets do not reproduce
    real = design(w, zs, cfg)
    real = real[(real["week_start"] >= lo) & (real["week_start"] + pd.Timedelta(days=6) <= hi)]
    tp = []
    for wk in fake_weeks:
        x = with_fake_policy(real, pd.Timestamp(wk))
        tp.append({"fake_week": pd.Timestamp(wk), "equal_weight": estimate(x),
                   "pre_volume_weighted": estimate_w(x),
                   "equal_weight_no_weather": estimate(x, weather=False),
                   "pre_volume_weighted_no_weather": estimate_w(x, weather=False)})
    tp = pd.DataFrame(tp)
    tp.to_csv(res / "placebo_time_distribution.csv", index=False, lineterminator="\n",
              float_format="%.6g")
    n_d, seed = int(pc["draws"]), cfg["seed"]      # same seed: the same draws, paired
    specs = {"equal_weight": lambda d: estimate(d),
             "pre_volume_weighted": lambda d: estimate_w(d),
             "equal_weight_no_weather": lambda d: estimate(d, weather=False),
             "pre_volume_weighted_no_weather": lambda d: estimate_w(d, weather=False)}
    dr = {s_: permutation(pre, zones_m, n_tr, n_d, fake_weeks, assign, f, seed)
          for s_, f in specs.items()}
    pd.concat([v.assign(spec=s_) for s_, v in dr.items()]).to_csv(
        res / "demand_placebo_draws.csv", index=False, lineterminator="\n", float_format="%.6g")
    bw = e["pre_volume_weighted_not_preregistered"]["terms"]["treated_post"]
    b_nw = e["without_weather"]["terms"]["treated_post"]
    bw_nw = e["pre_volume_weighted_without_weather"]["terms"]["treated_post"]
    real_b = {"equal_weight": b["coef"], "pre_volume_weighted": bw["coef"],
              "equal_weight_no_weather": b_nw["coef"],
              "pre_volume_weighted_no_weather": bw_nw["coef"]}

    def summ(x, s_):
        return {"real_beta": real_b[s_], **power_summary(x, real_b[s_], pc["size"], pc["power"])}

    def lag1(x):
        return float(pd.Series(x).autocorr(lag=1))

    power = {"outcome": "log1p_pickups", "real_beta": b["coef"],
             "specification": "every placebo is estimated with the controls of the real "
                              "estimate it is compared with: weather x treated (the reported "
                              "specification); the *_no_weather variants omit them and are "
                              "compared with the real estimates without weather "
                              "(did_static.json: without_weather, "
                              "pre_volume_weighted_without_weather)",
             "design": f"{pc['draws']} draws on pre-policy weeks {pc['window']}: fake policy "
                       f"week uniform over weeks with >= {k} weeks on each side, {n_tr} random "
                       "Manhattan zones as fake treatment vs the other Manhattan zones; static "
                       f"window <= {pc['pre_weeks']} weeks before the fake week to the end of "
                       "the pre-policy data; zone + week FE, weather x treated",
             **power_summary(dr["equal_weight"]["coef"], b["coef"], pc["size"], pc["power"]),
             "pre_volume_weighted": {
                 "weights": "each zone's mean weekly pickups in the (placebo) pre window",
                 **summ(dr["pre_volume_weighted"]["coef"], "pre_volume_weighted")},
             "no_weather": {s_: summ(dr[s_]["coef"], s_) for s_ in
                            ("equal_weight_no_weather", "pre_volume_weighted_no_weather")},
             "time_only_real_assignment": {
                 "design": "the real CBD / donut assignment with the fake policy week moved over "
                           f"the {len(fake_weeks)} admissible pre-policy weeks (consecutive "
                           "weeks: strongly dependent draws, see lag1_autocorrelation)",
                 **{s_: {**summ(tp[s_], s_), "lag1_autocorrelation": lag1(tp[s_]),
                         "min": float(tp[s_].min()), "max": float(tp[s_].max())}
                    for s_ in specs}}}
    (res / "power_mde.json").write_text(json.dumps(power, indent=2, default=str) + "\n")
    tw = power["time_only_real_assignment"]["pre_volume_weighted"]
    LOG.info("demand permutation: sd %.4f, MDE %.4f, share %.3f; weighted MDE %.4f, share %.3f; "
             "time-only weighted sd %.4f, mean %.4f, share %.3f",
             power["sd"], power["mde"], power["share_abs_ge_abs_beta"],
             power["pre_volume_weighted"]["mde"],
             power["pre_volume_weighted"]["share_abs_ge_abs_beta"], tw["sd"], tw["mean"],
             tw["share_abs_ge_abs_beta"])

    heterogeneity(w, zs, cfg, res)


def heterogeneity(w: pd.DataFrame, zs: pd.DataFrame, cfg: dict, res) -> None:
    """Static DiD on sub-panels: log1p of the sub-count per zone-week, same design, in both
    specifications: equal zone weights (pre-registered) and pre-volume weighted (primary, C2;
    weights = the zone's pre-period mean of that subset's count)."""
    pw = cfg["causal"]["pre_weeks"]
    bands = [f"pickups_h{lo:02d}_{hi:02d}" for lo, hi in cfg["panel"]["hour_bands"]]
    cuts = {"hour_band": bands, "day_type": ["pickups_weekday", "pickups_weekend"],
            "dropoff": ["pickups_do_cbd", "pickups_do_non_cbd"],
            "distance_tercile": ["pickups_dist_t1", "pickups_dist_t2", "pickups_dist_t3"],
            "fare_tercile": ["pickups_fare_t1", "pickups_fare_t2", "pickups_fare_t3"]}
    rows = []

    def add(spec, cut, level, comparison, r):
        rows.append({"spec": spec, "cut": cut, "level": level, "comparison": comparison,
                     **r["terms"]["treated_post"], "n_obs": r["n_obs"]})

    for cut, cols in cuts.items():
        d = design(w, zs, cfg, y_cols=cols)
        for c in cols:
            lab, comp = c.removeprefix("pickups_"), "CBD vs donut control zones, this subset"
            add("equal_weight", cut, lab, comp, did(d, f"log1p_{c}", cfg))
            dw = add_pre_volume_weight(d, pw, col=c)
            add("pre_volume_weighted", cut, lab, comp,
                did(dw, f"log1p_{c}", cfg, weights="w_pre"))
    # pass-through split of the metric framework (PLAN A1; Checkpoint 1 decision 3, the
    # trip-level fee check): within the control zones, trips ending in the CBD
    # (they pay the fee) vs trips ending outside it; units = zone x trip type
    ctl = control_zone_ids(zs, cfg)
    base = w[w["zone_id"].isin(ctl)]
    long = pd.concat([base.assign(unit=base["zone_id"] * 10 + 1, treated=1,
                                  cnt=base["pickups_do_cbd"],
                                  y=np.log1p(base["pickups_do_cbd"])),
                      base.assign(unit=base["zone_id"] * 10, treated=0,
                                  cnt=base["pickups_do_non_cbd"],
                                  y=np.log1p(base["pickups_do_non_cbd"]))])
    comp = "control-zone pickups ending in the CBD vs ending outside it"
    add("equal_weight", "pass_through", "dropoff_only_in_cbd", comp,
        static_did(long, "y", "unit", ["zone_id"], pw).to_dict())
    lw = add_pre_volume_weight(long, pw, col="cnt", unit="unit")
    add("pre_volume_weighted", "pass_through", "dropoff_only_in_cbd", comp,
        static_did(lw, "y", "unit", ["zone_id"], pw, weights="w_pre").to_dict())
    d = design(w, zs, cfg)
    comp = "CBD vs donut control zones (= main estimate)"
    add("equal_weight", "pass_through", "pickup_in_cbd", comp, did(d, "log1p_pickups", cfg))
    add("pre_volume_weighted", "pass_through", "pickup_in_cbd", comp,
        did(add_pre_volume_weight(d, pw), "log1p_pickups", cfg, weights="w_pre"))
    for c in ("outer_boroughs", "outer_boroughs_with_airports"):
        d = design(w, zs, cfg, control=c)
        add("equal_weight", "airports", c, f"CBD vs {c}", did(d, "log1p_pickups", cfg))
        add("pre_volume_weighted", "airports", c, f"CBD vs {c}",
            did(add_pre_volume_weight(d, pw), "log1p_pickups", cfg, weights="w_pre"))
    pd.DataFrame(rows).to_csv(res / "heterogeneity.csv", index=False, lineterminator="\n",
                              float_format="%.6g")
    LOG.info("heterogeneity: %d rows", len(rows))

if __name__ == "__main__":
    main()
