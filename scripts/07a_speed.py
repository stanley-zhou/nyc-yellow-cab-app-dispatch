"""Phase 4, step 1 (Amendment 2, B1-B3): trip speed and duration, DiD and event study.

Unit: pickup zone x dropoff zone ("pair") x panel week, from dbt `fct_weekly_pair_speed` (trips
within Manhattan). Treated = pairs with pickup and dropoff in the CBD; control = pairs with both
zones in the primary control (`causal.control`, the donut). Outcomes: log of the pair-week mean
trip speed (mph) and mean trip duration (minutes), weighted by trips used; pair FE + week FE;
SEs two-way clustered by pickup and dropoff zone (`speed.cluster`). Pre-specified direction:
speed up / duration down (DECISIONS.md, Amendment 2 pre-registration).

Writes
    results/speed_did.json          static DiD (+ persistence split, one-way clusters, without
                                    weather, with a distance control), entering / leaving trips,
                                    fare per minute, pre-trend tests of the event studies
    results/speed_event_study.csv   monthly and weekly event-study coefficients
    results/speed_heterogeneity.csv distance terciles (B3) and pickup-hour bands (B2)
    results/speed_exclusions.csv    excluded share by month, category and reason (B3)
    results/speed_power.json        permutation-placebo distribution summary and MDE (A2-style)
    results/speed_placebo.csv       the placebo draws

Usage:
    python scripts/07a_speed.py
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.causal.did import SEASONAL, add_seasonal, static_did
from taxi_shock.causal.event_study import event_study
from taxi_shock.causal.panel import control_zone_ids, full_weeks, pair_category
from taxi_shock.causal.placebo import permutation, power_summary, quick_beta
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("speed")
OUTCOMES = {"log_mean_speed_mph": "mean trip speed (mph)",
            "log_mean_duration_min": "mean trip duration (minutes)"}


def load(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Pair-week-band-tercile panel with zone flags, the weekly weather, and the zone sets."""
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    manhattan = zs[zs["borough"] == "Manhattan"]
    cbd = set(manhattan.loc[manhattan["is_cbd"], "zone_id"].astype(int))
    ctl = set(control_zone_ids(zs, cfg))
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        p = con.execute("select * from fct_weekly_pair_speed").df()
        wx = con.execute("""select week_start, any_value(mean_temp_f) as mean_temp_f,
                                   any_value(total_precip_in) as total_precip_in
                            from fct_weekly_zone_panel group by 1""").df()
    p["week_start"] = pd.to_datetime(p["week_start"])
    wx["week_start"] = pd.to_datetime(wx["week_start"])
    p["category"] = pair_category(p["pu_zone_id"].isin(cbd), p["do_zone_id"].isin(cbd),
                                  p["pu_zone_id"].isin(ctl), p["do_zone_id"].isin(ctl))
    sets = {"cbd": sorted(cbd), "control": sorted(ctl), "manhattan": sorted(
        manhattan["zone_id"].astype(int))}
    return p, wx, sets


SUMS = ["n_trips", "n_excl_duration", "n_excl_distance", "n_excl_speed", "n_used",
        "sum_duration_min", "sum_distance_mi", "sum_speed_mph", "n_fare", "sum_fare",
        "sum_duration_fare_min"]


def pair_week(p: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Aggregate to pair x week (x `by`) and form the outcomes."""
    keys = ["pu_zone_id", "do_zone_id", "category", "week_start", "event_week", *(by or [])]
    a = p.groupby(keys, observed=True)[SUMS].sum().reset_index()
    a = a[a["n_used"] > 0].copy()
    a["mean_speed_mph"] = a["sum_speed_mph"] / a["n_used"]
    a["mean_duration_min"] = a["sum_duration_min"] / a["n_used"]
    a["log_mean_speed_mph"] = np.log(a["mean_speed_mph"])
    a["log_mean_duration_min"] = np.log(a["mean_duration_min"])
    a["log_mean_distance_mi"] = np.log(a["sum_distance_mi"] / a["n_used"])
    a["pair"] = a["pu_zone_id"] * 1000 + a["do_zone_id"]
    return a


def design(a: pd.DataFrame, wx: pd.DataFrame, treated_cat: str, cfg: dict) -> pd.DataFrame:
    """Treated category vs within-control pairs, full weeks, weather x treated."""
    d = a[a["category"].isin([treated_cat, "within_control"])].copy()
    d = full_weeks(d, cfg).merge(wx, on="week_start", how="left")
    d["treated"] = (d["category"] == treated_cat).astype(int)
    for c in cfg["causal"]["weather_controls"]:
        d[f"tr_{c}"] = d["treated"] * d[c]
    return add_seasonal(d)


def did(d: pd.DataFrame, y: str, cfg: dict, cluster: list[str] | None = None,
        weather: bool = True, extra: list[str] | None = None, splits: bool = False) -> dict:
    cc = cfg["causal"]
    ctrl = [f"tr_{c}" for c in cc["weather_controls"]] if weather else []
    r = static_did(d, y, "pair", cluster or cfg["speed"]["cluster"], cc["pre_weeks"],
                   weights="n_used", controls=[*ctrl, *(extra or [])],
                   post_splits=cc["post_splits"] if splits else None)
    return r.to_dict()


def exclusions(p: pd.DataFrame) -> pd.DataFrame:
    m = p.assign(month=p["week_start"].dt.to_period("M").astype(str))
    g = m.groupby(["month", "category"])[["n_trips", "n_excl_duration", "n_excl_distance",
                                          "n_excl_speed", "n_used"]].sum().reset_index()
    for r in ("duration", "distance", "speed"):
        g[f"share_excl_{r}"] = g[f"n_excl_{r}"] / g["n_trips"]
    g["share_used"] = g["n_used"] / g["n_trips"]
    return g


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    cc, res = cfg["causal"], path("results", cfg)
    policy = cfg["data"]["policy_date"]
    p, wx, sets = load(cfg)
    LOG.info("speed panel: %d cells, %d trips", len(p), int(p["n_trips"].sum()))
    exclusions(p).to_csv(res / "speed_exclusions.csv", index=False, lineterminator="\n",
                         float_format="%.6g")

    a = pair_week(p)
    main_d = design(a, wx, "within_cbd", cfg)
    out: dict = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                 "pre_registration": "DECISIONS.md, Phase 4 (Amendment 2, B1-B3)",
                 "expected_direction": {"log_mean_speed_mph": "+", "log_mean_duration_min": "-"},
                 "zones": {"cbd": len(sets["cbd"]), "control": len(sets["control"]),
                           "control_group": cc["control"]},
                 "sample": {"pairs_treated": int(main_d.loc[main_d["treated"] == 1, "pair"]
                                                 .nunique()),
                            "pairs_control": int(main_d.loc[main_d["treated"] == 0, "pair"]
                                                 .nunique()),
                            "trips_used": int(main_d["n_used"].sum())},
                 "outcomes": {}}
    es_rows = []
    for y, label in OUTCOMES.items():
        o = {"label": label,
             "main": did(main_d, y, cfg),
             "persistence": did(main_d, y, cfg, splits=True),
             "cluster_pickup_zone_only": did(main_d, y, cfg, cluster=["pu_zone_id"]),
             "without_weather": did(main_d, y, cfg, weather=False),
             "distance_control": did(main_d, y, cfg, extra=["log_mean_distance_mi"]),
             "treated_seasonality_not_preregistered": did(main_d, y, cfg, extra=SEASONAL),
             "treated_seasonality_persistence_not_preregistered": did(
                 main_d, y, cfg, extra=SEASONAL, splits=True),
             "entering_cbd": did(design(a, wx, "entering", cfg), y, cfg),
             "leaving_cbd": did(design(a, wx, "leaving", cfg), y, cfg),
             "passing_through": "not identifiable from pickup and dropoff zones"}
        ctrl = [f"tr_{c}" for c in cc["weather_controls"]]
        for unit in ("month", "week"):
            t, info = event_study(main_d, y, "pair", cfg["speed"]["cluster"], policy, unit,
                                  weights="n_used", controls=ctrl)
            es_rows.append(t.assign(outcome=y, bins=unit))
            o[f"event_study_{unit}"] = info
        out["outcomes"][y] = o
        m = o["main"]["terms"]["treated_post"]
        LOG.info("%s: %.4f [%.4f, %.4f]; pre-trend p(F) = %.3f", y, m["coef"], m["ci_lo"],
                 m["ci_hi"], o["event_study_month"]["pretrend"]["p_F"])
    # B4: fare per minute (static only)
    fpm = main_d[main_d["n_fare"] > 0].assign(
        log_fare_per_min=lambda x: np.log(x["sum_fare"] / x["sum_duration_fare_min"]))
    out["outcomes"]["log_fare_per_min"] = {"label": "fare per minute (fare_amount / duration)",
                                           "main": did(fpm, "log_fare_per_min", cfg)}
    pd.concat(es_rows, ignore_index=True).to_csv(res / "speed_event_study.csv", index=False,
                                                 lineterminator="\n", float_format="%.6g")

    het = []
    for by, levels in (("dist_tercile", ["t1", "t2", "t3"]),
                       ("hour_band", sorted(p["hour_band"].unique()))):
        ab = pair_week(p, [by])
        for lv in levels:
            d = design(ab[ab[by] == lv], wx, "within_cbd", cfg)
            for y in OUTCOMES:
                r = did(d, y, cfg)
                het.append({"outcome": y, "cut": by, "level": lv, **r["terms"]["treated_post"],
                            "n_obs": r["n_obs"], "trips_used": int(d["n_used"].sum())})
    pd.DataFrame(het).to_csv(res / "speed_heterogeneity.csv", index=False, lineterminator="\n",
                             float_format="%.6g")

    # A2-style permutation placebo on pre-policy data: random fake week x 38 random Manhattan
    # zones as fake CBD; fake treated = pairs within the fake set, control = pairs within the rest
    pc = cc["permutation"]
    lo, hi = (pd.Timestamp(x) for x in pc["window"])
    man = a[a["pu_zone_id"].isin(sets["manhattan"]) & a["do_zone_id"].isin(sets["manhattan"])]
    pre = full_weeks(man, cfg)
    pre = pre[(pre["week_start"] >= lo) & (pre["week_start"] + pd.Timedelta(days=6) <= hi)]
    weeks = sorted(pre["week_start"].unique())
    k = int(pc["min_side_weeks"])
    fake_weeks = weeks[k:len(weeks) - k + 1]

    def assign(df: pd.DataFrame, fake: set[int]) -> pd.DataFrame:
        pu, do = df["pu_zone_id"].isin(fake), df["do_zone_id"].isin(fake)
        d = df[(pu & do) | (~pu & ~do)]
        return d.assign(treated=(d["pu_zone_id"].isin(fake)).astype(int))

    def estimate(df: pd.DataFrame) -> float:
        d = df[df["event_week"] >= -int(pc["pre_weeks"])]
        return quick_beta(d, "log_mean_speed_mph", "pair", weights="n_used")

    draws = permutation(pre, sets["manhattan"], len(sets["cbd"]), int(pc["draws"]), fake_weeks,
                        assign, estimate, cfg["seed"])
    draws.to_csv(res / "speed_placebo.csv", index=False, lineterminator="\n",
                 float_format="%.6g")
    beta = out["outcomes"]["log_mean_speed_mph"]["main"]["terms"]["treated_post"]["coef"]
    power = {"outcome": "log_mean_speed_mph", "real_beta": beta,
             "design": f"{pc['draws']} draws on pre-policy weeks {pc['window']}: fake policy "
                       f"week uniform over weeks with >= {k} weeks on each side, "
                       f"{len(sets['cbd'])} random Manhattan zones as fake CBD; fake treated = "
                       "pairs within the fake set, control = pairs within the other Manhattan "
                       f"zones; static window <= {pc['pre_weeks']} weeks before the fake week "
                       "to the end of the pre-policy data; pair + week FE, weighted by trips",
             **power_summary(draws["coef"], beta, pc["size"], pc["power"])}
    (res / "speed_power.json").write_text(json.dumps(power, indent=2, default=str) + "\n")
    (res / "speed_did.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    LOG.info("speed permutation: sd %.4f, MDE %.4f, share |placebo| >= |beta| %.3f",
             power["sd"], power["mde"], power["share_abs_ge_abs_beta"])


if __name__ == "__main__":
    main()
