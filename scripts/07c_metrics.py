"""Phase 4, step 4: metric framework (A1, B4), trade-off table (A3, B5), forecast counterfactual.

Reads the step-1/2/3 results (results/speed_did.json, did_static.json, heterogeneity.csv,
power_mde.json, speed_power.json) and estimates the guardrail DiDs that are not in them:
spillover (donut-control zones vs Brooklyn + Queens) and mean fare per trip (CBD vs donut).

Writes
    results/metric_framework.csv   one row per metric: role, outcome, estimate, 95% CI, %, n,
                                   source (A1 table, extended by B4 rows)
    results/elasticity_tradeoff.json  A3 implied price elasticity; B5 rider trade-off (minutes
                                   saved x value of time vs $0.75, break-even value of time);
                                   quarterly congestion-fee revenue collected
    results/counterfactual.csv     PLAN forecast counterfactual: CBD daily pickups vs the
                                   frozen-LightGBM forecast, implied effect by month
    results/effect_map.csv         F4b input: per Manhattan zone, mean weekly pickups in the 52
                                   pre weeks and the post weeks, log change, and log change minus
                                   the donut-control mean log change

Usage:
    python scripts/07c_metrics.py
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.causal.did import Z95, static_did
from taxi_shock.causal.panel import control_zone_ids, full_weeks
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("metrics")
FEE = 0.75          # taxi congestion fee per trip (PLAN §1)
VOT = [20, 30, 40]  # B5: values of time, $/h


def row(role, area, metric, term, src, note="", n=None) -> dict:
    return {"role": role, "area": area, "metric": metric, "coef": term["coef"],
            "ci_lo": term["ci_lo"], "ci_hi": term["ci_hi"], "pvalue": term.get("pvalue"),
            "pct": float(np.expm1(term["coef"])) if "log" in metric else np.nan,
            "n_obs": n, "source": src, "note": note}


def term_of(e: dict, name: str = "treated_post") -> dict:
    return e["terms"][name]


def guardrails(cfg: dict) -> dict:
    """Spillover (donut control zones vs outer boroughs) and mean fare per trip (CBD vs donut)."""
    cc = cfg["causal"]
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        w = con.execute("""select w.zone_id, w.week_start, w.event_week, w.n_days, w.pickups,
                                  w.mean_temp_f, w.total_precip_in, s.n_revenue_known,
                                  s.sum_fare_amount
                           from fct_weekly_zone_panel w
                           join fct_weekly_zone_trip_stats s using (zone_id, week_start)""").df()
    w["week_start"] = pd.to_datetime(w["week_start"])
    w = full_weeks(w[w["n_days"] == 7], cfg)
    ctrl = [f"tr_{c}" for c in cc["weather_controls"]]

    def prep(treated: list[int], control: list[int]) -> pd.DataFrame:
        d = w[w["zone_id"].isin(treated + control)].copy()
        d["treated"] = d["zone_id"].isin(treated).astype(int)
        for c in cc["weather_controls"]:
            d[f"tr_{c}"] = d["treated"] * d[c]
        d["log1p_pickups"] = np.log1p(d["pickups"])
        pre = d[d["event_week"].between(-cc["pre_weeks"], -1)].groupby("zone_id")["pickups"]
        d["w_pre"] = d["zone_id"].map(pre.mean()).fillna(0)
        return d

    out = {}
    donut = control_zone_ids(zs, cfg)
    outer = control_zone_ids(zs, cfg, "outer_boroughs")
    d = prep(donut, outer)
    out["spillover"] = static_did(d, "log1p_pickups", "zone_id", ["zone_id"], cc["pre_weeks"],
                                  controls=ctrl).to_dict()
    dw = d[d["w_pre"] > 0]
    out["spillover_pre_volume_weighted"] = static_did(
        dw, "log1p_pickups", "zone_id", ["zone_id"], cc["pre_weeks"], weights="w_pre",
        controls=ctrl).to_dict()
    cbd = sorted(zs.loc[zs["is_cbd"], "zone_id"].astype(int))
    f = prep(cbd, donut)
    f = f[f["n_revenue_known"] > 0].assign(
        log_mean_fare=lambda x: np.log(x["sum_fare_amount"] / x["n_revenue_known"]))
    out["mean_fare"] = static_did(f, "log_mean_fare", "zone_id", ["zone_id"], cc["pre_weeks"],
                                  weights="n_revenue_known", controls=ctrl).to_dict()
    return out


def fee_revenue(cfg: dict) -> pd.DataFrame:
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        q = con.execute("""
            select date_trunc('quarter', week_start) as quarter, sum(sum_cbd_fee) as fee,
                   sum(n_cbd_fee_positive) as trips_with_fee, count(distinct week_start) as weeks
            from fct_weekly_zone_trip_stats
            where week_start >= ? group by 1 order by 1""", [cfg["data"]["policy_date"]]).df()
    q["quarter"] = pd.to_datetime(q["quarter"]).dt.to_period("Q").astype(str)
    return q


def pre_cbd_stats(cfg: dict) -> dict:
    """Pre-period (52 weeks) mean fare of CBD pickups and mean duration of within-CBD trips."""
    lo, hi = cfg["data"]["pre_period"]
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    cbd = sorted(zs.loc[zs["is_cbd"], "zone_id"].astype(int))
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        con.execute("create temp table c as select unnest(?::integer[]) as zone_id", [cbd])
        fare = con.execute("""select sum(sum_fare_amount) / sum(n_revenue_known)
                              from fct_weekly_zone_trip_stats
                              where zone_id in (select zone_id from c)
                                and week_start between ? and ?""", [lo, hi]).fetchone()[0]
        dur = con.execute("""
            select case when pu_zone_id in (select zone_id from c) then 'from_cbd' else 'to_cbd'
                   end as k,
                   case when pu_zone_id in (select zone_id from c)
                         and do_zone_id in (select zone_id from c) then 'within_cbd'
                        when do_zone_id in (select zone_id from c) then 'entering'
                        when pu_zone_id in (select zone_id from c) then 'leaving' end as cat,
                   sum(sum_duration_min) / sum(n_used) as mean_duration_min,
                   sum(n_used) as trips
            from fct_weekly_pair_speed
            where week_start between ? and ? and (pu_zone_id in (select zone_id from c)
                                                  or do_zone_id in (select zone_id from c))
            group by all""", [lo, hi]).df()
    dur = dur.dropna(subset=["cat"]).groupby("cat").apply(
        lambda x: np.average(x["mean_duration_min"], weights=x["trips"]), include_groups=False)
    return {"pre_period": [lo, hi], "mean_fare_cbd_pickups": float(fare),
            "mean_duration_min": {k: float(v) for k, v in dur.items()}}


def counterfactual(cfg: dict) -> pd.DataFrame:
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    cbd = set(zs.loc[zs["is_cbd"], "zone_id"].astype(int))
    fc = pd.read_parquet(path("forecasts", cfg) / "frozen" / "lgbm_quantile.parquet",
                         columns=["zone_id", "target_ts", "y", "point"])
    fc = fc[fc["zone_id"].isin(cbd) & fc["y"].notna() & fc["point"].notna()]
    day = fc.assign(day=fc["target_ts"].dt.normalize()).groupby("day")[["y", "point"]].sum()
    day["rel"] = (day["y"] - day["point"]) / day["point"]
    m = day.groupby(day.index.to_period("M")).agg(
        actual=("y", "sum"), forecast=("point", "sum"), mean_daily_rel=("rel", "mean"),
        n_days=("rel", "size")).reset_index().rename(columns={"day": "month"})
    m["month"] = m["month"].astype(str)
    end = pd.Timestamp(cfg["shock"]["frozen_train_end"]).to_period("M")
    m["in_sample"] = pd.PeriodIndex(m["month"], freq="M") <= end
    return m


def effect_map(cfg: dict) -> pd.DataFrame:
    cc = cfg["causal"]
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    man = zs[zs["borough"] == "Manhattan"].set_index("zone_id")
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        w = con.execute("select zone_id, week_start, event_week, n_days, pickups "
                        "from fct_weekly_zone_panel").df()
    w["week_start"] = pd.to_datetime(w["week_start"])
    w = full_weeks(w[(w["n_days"] == 7) & w["zone_id"].isin(man.index)], cfg)
    pre = w[w["event_week"].between(-cc["pre_weeks"], -1)].groupby("zone_id")["pickups"].mean()
    post = w[w["event_week"] >= 0].groupby("zone_id")["pickups"].mean()
    m = pd.DataFrame({"pre_mean_weekly": pre, "post_mean_weekly": post}).join(
        man[["zone_name", "is_cbd"]])
    m["log_change"] = np.log(m["post_mean_weekly"] / m["pre_mean_weekly"])
    ctl = control_zone_ids(zs, cfg)
    m["is_control"] = m.index.isin(ctl)
    ref = m.loc[m["is_control"], "log_change"].replace([np.inf, -np.inf], np.nan).dropna()
    m["control_mean_log_change"] = float(ref.mean())
    m["relative_log_change"] = m["log_change"] - float(ref.mean())     # PLAN literal
    c = m[m["is_control"]]
    agg = float(np.log(c["post_mean_weekly"].sum() / c["pre_mean_weekly"].sum()))
    m["control_aggregate_log_change"] = agg
    m["relative_to_control_aggregate"] = m["log_change"] - agg        # F4b (DECISIONS)
    return m.reset_index()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    ds = json.loads((res / "did_static.json").read_text())["estimates"]
    sp = json.loads((res / "speed_did.json").read_text())["outcomes"]
    het = pd.read_csv(res / "heterogeneity.csv")
    g = guardrails(cfg)
    rows = [
        row("primary", "demand (quantity)", "log1p CBD pickups", term_of(ds["main"]),
            "did_static.json:main", "pre-registered; pre-trend test rejects",
            ds["main"]["n_obs"]),
        row("primary", "demand (quantity)", "CBD pickups, levels per zone-week",
            term_of(ds["levels"]), "did_static.json:levels", "", ds["levels"]["n_obs"]),
        row("primary", "demand (quantity)", "log1p CBD pickups, pre-volume weighted",
            term_of(ds["pre_volume_weighted_not_preregistered"]),
            "did_static.json:pre_volume_weighted_not_preregistered", "not pre-registered"),
        row("primary", "service quality (speed)", "log mean trip speed, within-CBD trips",
            term_of(sp["log_mean_speed_mph"]["main"]), "speed_did.json", "pre-registered"),
        row("primary", "service quality (speed)", "log mean trip duration, within-CBD trips",
            term_of(sp["log_mean_duration_min"]["main"]), "speed_did.json", "pre-registered"),
        row("secondary", "service quality (speed)", "log fare per minute, within-CBD trips",
            term_of(sp["log_fare_per_min"]["main"]), "speed_did.json", "B4"),
        row("guardrail", "spillover", "log1p pickups, donut-control zones vs Brooklyn+Queens",
            term_of(g["spillover"]), "guardrails (this script)", "", g["spillover"]["n_obs"]),
        row("guardrail", "spillover",
            "log1p pickups, donut vs Brooklyn+Queens, pre-volume weighted",
            term_of(g["spillover_pre_volume_weighted"]), "guardrails (this script)",
            "not pre-registered"),
        row("guardrail", "price", "log mean fare per trip, CBD vs donut (trip-weighted)",
            term_of(g["mean_fare"]), "guardrails (this script)", "", g["mean_fare"]["n_obs"]),
    ]
    for r in het.itertuples():
        role = "secondary" if r.cut in ("hour_band", "day_type", "distance_tercile",
                                        "fare_tercile", "pass_through", "dropoff") else "check"
        rows.append(row(role, f"heterogeneity: {r.cut}", f"log1p pickups, {r.level}",
                        {"coef": r.coef, "ci_lo": r.ci_lo, "ci_hi": r.ci_hi,
                         "pvalue": r.pvalue}, "heterogeneity.csv", r.comparison, r.n_obs))
    fw = pd.DataFrame(rows)
    fw.to_csv(res / "metric_framework.csv", index=False, lineterminator="\n",
              float_format="%.6g")

    # A3 / B5
    pre = pre_cbd_stats(cfg)
    price_change = FEE / pre["mean_fare_cbd_pickups"]
    elast = {}
    for k in ("main", "pre_volume_weighted_not_preregistered"):
        t = term_of(ds[k])
        elast[k] = {"pct_change_trips": float(np.expm1(t["coef"])),
                    "pct_change_trips_ci": [float(np.expm1(t["ci_lo"])),
                                            float(np.expm1(t["ci_hi"]))],
                    "implied_elasticity": float(np.expm1(t["coef"]) / price_change),
                    "implied_elasticity_ci": [float(np.expm1(t["ci_lo"]) / price_change),
                                              float(np.expm1(t["ci_hi"]) / price_change)]}
    trade = {}
    specs = {"within_cbd": sp["log_mean_duration_min"]["main"],
             "within_cbd_treated_seasonality_not_preregistered":
                 sp["log_mean_duration_min"]["treated_seasonality_not_preregistered"],
             "entering": sp["log_mean_duration_min"]["entering_cbd"],
             "leaving": sp["log_mean_duration_min"]["leaving_cbd"]}
    for name, e in specs.items():
        cat = name.split("_treated")[0]
        base = pre["mean_duration_min"][cat]
        t = term_of(e)
        mins = {k: -base * float(np.expm1(v)) for k, v in
                (("point", t["coef"]), ("ci_a", t["ci_lo"]), ("ci_b", t["ci_hi"]))}
        lo, hi = sorted([mins["ci_a"], mins["ci_b"]])
        saved = mins["point"]
        trade[name] = {
            "pre_mean_duration_min": base, "duration_effect_log": t["coef"],
            "minutes_saved_per_trip": saved, "minutes_saved_ci": [lo, hi],
            "value_of_time_saved": {str(v): saved / 60 * v for v in VOT},
            "net_vs_fee": {str(v): saved / 60 * v - FEE for v in VOT},
            "break_even_value_of_time_per_hour": (FEE / (saved / 60)) if saved > 0 else None,
            "break_even_ci": [FEE / (hi / 60) if hi > 0 else None,
                              FEE / (lo / 60) if lo > 0 else None]}
    q = fee_revenue(cfg)
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "fee_per_trip": FEE, "pre_period_stats": pre, "price_change_pct": price_change,
           "a3_implied_elasticity": elast,
           "b5_rider_tradeoff": trade,
           "b5_note": "minutes saved per trip = pre-period mean duration x (1 - exp(beta)); "
                      "break-even value of time = fee / hours saved; the passenger's time only "
                      "(no driver time, no unpriced trips); NBER w33584 benchmark: $46/h for the "
                      "average priced taxi/FHV trip, $37/h including unpriced trips (DECISIONS)",
           "fee_revenue_by_quarter": q.to_dict(orient="records"),
           "fee_revenue_note": "sum of cbd_congestion_fee on valid yellow trips (all pickup "
                               "zones); fee recording varies by vendor (limitation, DECISIONS)",
           "z95": Z95}
    (res / "elasticity_tradeoff.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    effect_map(cfg).to_csv(res / "effect_map.csv", index=False, lineterminator="\n",
                           float_format="%.6g")
    cf = counterfactual(cfg)
    cf.to_csv(res / "counterfactual.csv", index=False, lineterminator="\n", float_format="%.6g")
    LOG.info("metric_framework: %d rows; elasticity (main) %.2f; break-even VOT within CBD %s",
             len(fw), elast["main"]["implied_elasticity"],
             trade["within_cbd"]["break_even_value_of_time_per_hour"])


if __name__ == "__main__":
    main()
