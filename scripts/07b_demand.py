"""Phase 4, steps 2-3: demand DiD (pickups), event study, checks, MDE and heterogeneity.

Panel: dbt `fct_weekly_zone_panel` (+ `fct_weekly_zone_trip_stats`, `fct_weekly_zone_vendor`),
complete weeks inside data.event_study_window. Treated = CBD zones, primary control = the donut
(`causal.control`). Outcome log1p(pickups) (and pickups in levels); zone FE + week FE; weather
enters as weather x treated; SEs clustered by zone.

Writes
    results/did_static.json     main estimate, persistence split, levels, without weather,
                                treated-seasonality (not pre-registered), alternative controls,
                                vendors present throughout (CMT + Curb), PLAN-literal filters,
                                leave-one-zone-out summary
    results/event_study.csv     monthly and weekly event-study coefficients (+ the
                                pre-volume-weighted monthly path, not pre-registered)
    results/placebo.json        pre-trend joint tests, placebo in time, leave-one-zone-out
    results/power_mde.json      Amendment 1 (A2) permutation placebo: distribution, share
                                |placebo| >= |beta|, MDE at 80% power / 5% size
    results/demand_placebo_draws.csv, results/leave_one_out.csv
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

from taxi_shock.causal.did import SEASONAL, add_seasonal, static_did
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


def add_pre_volume_weight(d: pd.DataFrame, pre_weeks: int) -> pd.DataFrame:
    """w_pre = the zone's mean weekly pickups over the static pre window (fixed per zone): the
    weighted DiD estimates the effect on aggregate pickups (not pre-registered; DECISIONS.md)."""
    pre = d[d["event_week"].between(-pre_weeks, -1)].groupby("zone_id")["pickups"].mean()
    out = d.assign(w_pre=d["zone_id"].map(pre).fillna(0.0))
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
    e["vendors_present_throughout_cmt_curb"] = did(d, "log1p_pickups_cmt_curb", cfg)
    e["plan_literal_filters"] = did(d, "log1p_pickups_literal", cfg)
    for c in [*cc["control_robustness"], "outer_boroughs_with_airports"]:
        e[f"control_{c}"] = did(design(w, zs, cfg, control=c), "log1p_pickups", cfg)
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

    # leave one zone out
    loo = leave_one_out(d, sorted(d["zone_id"].unique()),
                        lambda x: did(x, "log1p_pickups", cfg)["terms"]["treated_post"]["coef"],
                        ["zone_id"])
    loo.to_csv(res / "leave_one_out.csv", index=False, lineterminator="\n",
               float_format="%.6g")
    loo_sum = {"n": len(loo), "min": float(loo["coef"].min()), "max": float(loo["coef"].max()),
               "median": float(loo["coef"].median()),
               "all_same_sign_as_main": bool((np.sign(loo["coef"]) == np.sign(b["coef"])).all())}
    e["leave_one_zone_out"] = loo_sum
    (res / "placebo.json").write_text(json.dumps({
        "generated_utc": out["generated_utc"], "pretrend_tests": tests,
        "placebo_in_time": {"fake_policy_week": cc["placebo_week"],
                            "data": cc["placebo_window"], **placebo_time},
        "leave_one_zone_out": loo_sum}, indent=2, default=str) + "\n")
    (res / "did_static.json").write_text(json.dumps(out, indent=2, default=str) + "\n")

    # A2 permutation placebo (pre-policy data; 38 random Manhattan zones as fake treatment)
    pc = cc["permutation"]
    lo, hi = (pd.Timestamp(x) for x in pc["window"])
    man = w[w["zone_id"].isin(zs.loc[zs["borough"] == "Manhattan", "zone_id"])]
    pre = man[(man["week_start"] >= lo) & (man["week_start"] + pd.Timedelta(days=6) <= hi)]
    pre = pre.assign(log1p_pickups=np.log1p(pre["pickups"]))
    weeks = sorted(pre["week_start"].unique())
    k = int(pc["min_side_weeks"])
    n_tr = int(zs["is_cbd"].sum())

    def assign(df, fake):
        return df.assign(treated=df["zone_id"].isin(fake).astype(int))

    def estimate(df):
        return quick_beta(df[df["event_week"] >= -int(pc["pre_weeks"])], "log1p_pickups",
                          "zone_id")

    draws = permutation(pre, sorted(man["zone_id"].unique()), n_tr, int(pc["draws"]),
                        weeks[k:len(weeks) - k + 1], assign, estimate, cfg["seed"])
    draws.to_csv(res / "demand_placebo_draws.csv", index=False, lineterminator="\n",
                 float_format="%.6g")
    power = {"outcome": "log1p_pickups", "real_beta": b["coef"],
             "design": f"{pc['draws']} draws on pre-policy weeks {pc['window']}: fake policy "
                       f"week uniform over weeks with >= {k} weeks on each side, {n_tr} random "
                       "Manhattan zones as fake treatment vs the other Manhattan zones; static "
                       f"window <= {pc['pre_weeks']} weeks before the fake week to the end of "
                       "the pre-policy data; zone + week FE",
             **power_summary(draws["coef"], b["coef"], pc["size"], pc["power"])}
    (res / "power_mde.json").write_text(json.dumps(power, indent=2, default=str) + "\n")
    LOG.info("demand permutation: sd %.4f, MDE %.4f, share %.3f", power["sd"], power["mde"],
             power["share_abs_ge_abs_beta"])

    heterogeneity(w, zs, cfg, res)


def heterogeneity(w: pd.DataFrame, zs: pd.DataFrame, cfg: dict, res) -> None:
    """Static DiD on sub-panels: log1p of the sub-count per zone-week, same design."""
    bands = [f"pickups_h{lo:02d}_{hi:02d}" for lo, hi in cfg["panel"]["hour_bands"]]
    cuts = {"hour_band": bands, "day_type": ["pickups_weekday", "pickups_weekend"],
            "dropoff": ["pickups_do_cbd", "pickups_do_non_cbd"],
            "distance_tercile": ["pickups_dist_t1", "pickups_dist_t2", "pickups_dist_t3"],
            "fare_tercile": ["pickups_fare_t1", "pickups_fare_t2", "pickups_fare_t3"]}
    rows = []
    for cut, cols in cuts.items():
        d = design(w, zs, cfg, y_cols=cols)
        for c in cols:
            r = did(d, f"log1p_{c}", cfg)
            rows.append({"cut": cut, "level": c.removeprefix("pickups_"),
                         "comparison": "CBD vs donut control zones, this trip subset",
                         **r["terms"]["treated_post"], "n_obs": r["n_obs"]})
    # pass-through (A1, Checkpoint 1 item 3): within the control zones, trips ending in the CBD
    # (they pay the fee) vs trips ending outside it; units = zone x trip type
    ctl = control_zone_ids(zs, cfg)
    base = w[w["zone_id"].isin(ctl)]
    long = pd.concat([base.assign(unit=base["zone_id"] * 10 + 1, treated=1,
                                  y=np.log1p(base["pickups_do_cbd"])),
                      base.assign(unit=base["zone_id"] * 10, treated=0,
                                  y=np.log1p(base["pickups_do_non_cbd"]))])
    r = static_did(long, "y", "unit", ["zone_id"], cfg["causal"]["pre_weeks"]).to_dict()
    rows.append({"cut": "pass_through", "level": "dropoff_only_in_cbd",
                 "comparison": "control-zone pickups ending in the CBD vs ending outside it",
                 **r["terms"]["treated_post"], "n_obs": r["n_obs"]})
    d = design(w, zs, cfg)
    r = did(d, "log1p_pickups", cfg)
    rows.append({"cut": "pass_through", "level": "pickup_in_cbd",
                 "comparison": "CBD vs donut control zones (= main estimate)",
                 **r["terms"]["treated_post"], "n_obs": r["n_obs"]})
    for c in ("outer_boroughs", "outer_boroughs_with_airports"):
        r = did(design(w, zs, cfg, control=c), "log1p_pickups", cfg)
        rows.append({"cut": "airports", "level": c, "comparison": f"CBD vs {c}",
                     **r["terms"]["treated_post"], "n_obs": r["n_obs"]})
    pd.DataFrame(rows).to_csv(res / "heterogeneity.csv", index=False, lineterminator="\n",
                              float_format="%.6g")
    LOG.info("heterogeneity: %d rows", len(rows))


if __name__ == "__main__":
    main()
