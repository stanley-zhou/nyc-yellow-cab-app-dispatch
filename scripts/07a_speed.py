"""Phase 4 step 1 (Amendment 2, B1-B3) and Phase 4b C4 (Amendment 3): trip speed and duration.

Unit: pickup zone x dropoff zone ("pair") x panel week, from dbt `fct_weekly_pair_speed`.
Treated = pairs with pickup and dropoff in the CBD. Two controls, same design:
  donut  pairs with both zones in the primary control (`causal.control`): the pre-registered
         Amendment-2 comparison (results/speed_did.json)
  outer  pairs with both ends in Brooklyn or Queens outside the airports (`speed.outer_boroughs`;
         region 'outer' of the dbt sample): the C4 control, free of the Manhattan spillover
         (results/speed_did_outer.json)
Outcomes: log of the pair-week mean trip speed (mph) and mean trip duration (minutes), weighted
by trips used; pair FE + week FE; weather x treated; SEs two-way clustered by pickup and dropoff
zone (`speed.cluster`). Pre-specified direction: speed up / duration down.

Writes
    results/speed_did.json, results/speed_did_outer.json
                                    static DiD (+ persistence, one-way clusters, without weather,
                                    distance control, treated seasonality), entering / leaving
                                    trips (donut), the full Manhattan non-CBD control (donut
                                    file), fare per minute, placebo in time, pre-trend tests
    results/speed_event_study.csv   monthly and weekly event-study coefficients, column control
    results/speed_heterogeneity.csv distance terciles (B3) and pickup-hour bands (B2), by control
    results/speed_exclusions.csv    excluded share by month, category and reason (B3)
    results/speed_power.json        permutation-placebo summaries and MDEs for speed and
                                    duration, both controls (top-level keys: donut, speed)
    results/speed_placebo.csv       the placebo draws (columns control, outcome)

Resumable: each unit (the analysis and the permutation runs of each control) is cached in
data/forecasts/speed_units/<unit>.pkl with a fingerprint of this script, the causal library,
the config sections it uses and the panel size; a rerun skips units whose fingerprint matches
(`--force` recomputes). Writes are atomic.

Usage:
    python scripts/07a_speed.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import pickle
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from taxi_shock.causal.did import SEASONAL, add_seasonal, static_did
from taxi_shock.causal.event_study import event_study
from taxi_shock.causal.panel import control_zone_ids, full_weeks, pair_category
from taxi_shock.causal.placebo import (
    permutation,
    power_summary,
    quick_beta,
    with_fake_policy,
)
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("speed")
OUTCOMES = {"log_mean_speed_mph": "mean trip speed (mph)",
            "log_mean_duration_min": "mean trip duration (minutes)"}
CONTROLS = {"donut": "ctl_donut", "outer": "ctl_outer"}
FLAGS = ["within_cbd", "entering", "leaving", "ctl_donut", "ctl_outer", "ctl_mnc"]


def load(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Pair-week-band-tercile panel with pair flags, the weekly weather, and the zone sets."""
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    manhattan = zs[zs["borough"] == "Manhattan"]
    cbd = set(manhattan.loc[manhattan["is_cbd"], "zone_id"].astype(int))
    ctl = set(control_zone_ids(zs, cfg))
    mnc = set(control_zone_ids(zs, cfg, "manhattan_non_cbd"))
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        p = con.execute("select * from fct_weekly_pair_speed").df()
        wx = con.execute("""select week_start, any_value(mean_temp_f) as mean_temp_f,
                                   any_value(total_precip_in) as total_precip_in
                            from fct_weekly_zone_panel group by 1""").df()
    p["week_start"] = pd.to_datetime(p["week_start"])
    wx["week_start"] = pd.to_datetime(wx["week_start"])
    man = p["region"] == "manhattan"
    pu, do = p["pu_zone_id"], p["do_zone_id"]
    cat = pair_category(pu.isin(cbd), do.isin(cbd), pu.isin(ctl), do.isin(ctl))
    p["category"] = cat.where(man, "within_outer")
    p["within_cbd"] = cat.eq("within_cbd") & man
    p["entering"] = cat.eq("entering") & man
    p["leaving"] = cat.eq("leaving") & man
    p["ctl_donut"] = cat.eq("within_control") & man
    p["ctl_outer"] = ~man
    p["ctl_mnc"] = pu.isin(mnc) & do.isin(mnc) & man
    sets = {"cbd": sorted(cbd), "control": sorted(ctl),
            "manhattan": sorted(manhattan["zone_id"].astype(int))}
    return p, wx, sets


SUMS = ["n_trips", "n_excl_duration", "n_excl_distance", "n_excl_speed", "n_used",
        "sum_duration_min", "sum_distance_mi", "sum_speed_mph", "n_fare", "sum_fare",
        "sum_duration_fare_min"]


def pair_week(p: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Aggregate to pair x week (x `by`) and form the outcomes."""
    keys = ["pu_zone_id", "do_zone_id", "region", "category", *FLAGS, "week_start",
            "event_week", *(by or [])]
    a = p.groupby(keys, observed=True)[SUMS].sum().reset_index()
    a = a[a["n_used"] > 0].copy()
    a["mean_speed_mph"] = a["sum_speed_mph"] / a["n_used"]
    a["mean_duration_min"] = a["sum_duration_min"] / a["n_used"]
    a["log_mean_speed_mph"] = np.log(a["mean_speed_mph"])
    a["log_mean_duration_min"] = np.log(a["mean_duration_min"])
    a["log_mean_distance_mi"] = np.log(a["sum_distance_mi"] / a["n_used"])
    a["pair"] = a["pu_zone_id"] * 1000 + a["do_zone_id"]
    return a


def design(a: pd.DataFrame, wx: pd.DataFrame, treated: str, control: str, cfg: dict
           ) -> pd.DataFrame:
    """Pairs flagged `treated` vs pairs flagged `control`, full weeks, weather x treated."""
    d = a[a[treated] | a[control]].copy()
    d = full_weeks(d, cfg).merge(wx, on="week_start", how="left")
    d["treated"] = d[treated].astype(int)
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


def placebo_in_time(d: pd.DataFrame, y: str, cfg: dict) -> dict:
    cc = cfg["causal"]
    lo, hi = (pd.Timestamp(x) for x in cc["placebo_window"])
    pdat = d[(d["week_start"] >= lo) & (d["week_start"] + pd.Timedelta(days=6) <= hi)]
    return {"fake_policy_week": cc["placebo_week"], "data": cc["placebo_window"],
            **did(with_fake_policy(pdat, pd.Timestamp(cc["placebo_week"])), y, cfg)}


def exclusions(p: pd.DataFrame) -> pd.DataFrame:
    m = p.assign(month=p["week_start"].dt.to_period("M").astype(str))
    g = m.groupby(["month", "category"])[["n_trips", "n_excl_duration", "n_excl_distance",
                                          "n_excl_speed", "n_used"]].sum().reset_index()
    for r in ("duration", "distance", "speed"):
        g[f"share_excl_{r}"] = g[f"n_excl_{r}"] / g["n_trips"]
    g["share_used"] = g["n_used"] / g["n_trips"]
    return g


def analyse(p: pd.DataFrame, a: pd.DataFrame, wx: pd.DataFrame, sets: dict, control: str,
            cfg: dict) -> tuple[dict, list, list]:
    cc, policy = cfg["causal"], cfg["data"]["policy_date"]
    flag = CONTROLS[control]
    main_d = design(a, wx, "within_cbd", flag, cfg)
    out: dict = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                 "control": control,
                 "control_definition": {"donut": f"pairs within {cc['control']} zones "
                                                 "(pre-registered, Amendment 2)",
                                        "outer": "pairs with both ends in "
                                                 f"{'/'.join(cfg['speed']['outer_boroughs'])} "
                                                 "outside the airports (Amendment 3, C4)"}[control],
                 "pre_registration": "DECISIONS.md, Phase 4 (Amendment 2, B1-B3)" if control
                 == "donut" else "DECISIONS.md, Phase 4b (Amendment 3, C4)",
                 "expected_direction": {"log_mean_speed_mph": "+", "log_mean_duration_min": "-"},
                 "zones": {"cbd": len(sets["cbd"]), "control": len(sets["control"]),
                           "control_group": cc["control"]},
                 "sample": {"pairs_treated": int(main_d.loc[main_d["treated"] == 1, "pair"]
                                                 .nunique()),
                            "pairs_control": int(main_d.loc[main_d["treated"] == 0, "pair"]
                                                 .nunique()),
                            "trips_used": int(main_d["n_used"].sum())},
                 "outcomes": {}}
    es_rows, het = [], []
    ctrl = [f"tr_{c}" for c in cc["weather_controls"]]
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
             "placebo_in_time": placebo_in_time(main_d, y, cfg)}
        if control == "donut":
            o["entering_cbd"] = did(design(a, wx, "entering", flag, cfg), y, cfg)
            o["leaving_cbd"] = did(design(a, wx, "leaving", flag, cfg), y, cfg)
            o["passing_through"] = "not identifiable from pickup and dropoff zones"
            o["control_manhattan_non_cbd"] = did(design(a, wx, "within_cbd", "ctl_mnc", cfg),
                                                 y, cfg)
        # weekly bins only for the donut design: with the outer control (~1.2M pair-weeks x
        # ~195 weekly dummies) the dense design matrix alone is ~1.9 GB and pyfixest's copies
        # exhausted the WSL memory (DECISIONS.md, Phase 4b); the monthly study is the test
        for unit in ("month", "week") if control == "donut" else ("month",):
            t, info = event_study(main_d, y, "pair", cfg["speed"]["cluster"], policy, unit,
                                  weights="n_used", controls=ctrl)
            es_rows.append(t.assign(outcome=y, bins=unit, control=control))
            o[f"event_study_{unit}"] = info
        out["outcomes"][y] = o
        m = o["main"]["terms"]["treated_post"]
        LOG.info("%s %s: %.4f [%.4f, %.4f]; pre-trend p(F*) = %.3g", control, y, m["coef"],
                 m["ci_lo"], m["ci_hi"], o["event_study_month"]["pretrend"]["p_F_hotelling"])
    fpm = main_d[main_d["n_fare"] > 0].assign(
        log_fare_per_min=lambda x: np.log(x["sum_fare"] / x["sum_duration_fare_min"]))
    out["outcomes"]["log_fare_per_min"] = {"label": "fare per minute (fare_amount / duration)",
                                           "main": did(fpm, "log_fare_per_min", cfg)}
    for by, levels in (("dist_tercile", ["t1", "t2", "t3"]),
                       ("hour_band", sorted(p["hour_band"].unique()))):
        ab = pair_week(p, [by])
        for lv in levels:
            d = design(ab[ab[by] == lv], wx, "within_cbd", flag, cfg)
            for y in OUTCOMES:
                r = did(d, y, cfg)
                het.append({"control": control, "outcome": y, "cut": by, "level": lv,
                            **r["terms"]["treated_post"], "n_obs": r["n_obs"],
                            "trips_used": int(d["n_used"].sum())})
    return out, es_rows, het


def power(a: pd.DataFrame, sets: dict, control: str, results: dict, cfg: dict
          ) -> tuple[dict, pd.DataFrame]:
    """A2-style permutation placebo on pre-policy data: random fake week x 38 random Manhattan
    zones as fake CBD (pairs within the fake set) vs pairs within the other Manhattan zones
    (donut design) or the fixed outer-borough pairs (outer design); speed and duration."""
    pc = cfg["causal"]["permutation"]
    lo, hi = (pd.Timestamp(x) for x in pc["window"])
    keep = (a["region"] == "manhattan") | (a["ctl_outer"] if control == "outer" else False)
    pre = full_weeks(a[keep], cfg)
    pre = pre[(pre["week_start"] >= lo) & (pre["week_start"] + pd.Timedelta(days=6) <= hi)]
    weeks = sorted(pre["week_start"].unique())
    k = int(pc["min_side_weeks"])
    fake_weeks = weeks[k:len(weeks) - k + 1]

    def assign(df: pd.DataFrame, fake: set[int]) -> pd.DataFrame:
        pu, do = df["pu_zone_id"].isin(fake), df["do_zone_id"].isin(fake)
        man = df["region"] == "manhattan"
        tr = pu & do & man
        ctl = (df["region"] == "outer") if control == "outer" else (~pu & ~do & man)
        d = df[tr | ctl]
        return d.assign(treated=tr[tr | ctl].astype(int))

    summaries, frames = {}, []
    for y in OUTCOMES:
        def estimate(df: pd.DataFrame, y: str = y) -> float:
            return quick_beta(df[df["event_week"] >= -int(pc["pre_weeks"])], y, "pair",
                              weights="n_used")

        draws = permutation(pre, sets["manhattan"], len(sets["cbd"]), int(pc["draws"]),
                            fake_weeks, assign, estimate, cfg["seed"])
        beta = results["outcomes"][y]["main"]["terms"]["treated_post"]["coef"]
        summaries[y] = {"real_beta": beta, **power_summary(draws["coef"], beta, pc["size"],
                                                           pc["power"])}
        frames.append(draws.assign(control=control, outcome=y))
        LOG.info("%s %s permutation: sd %.4f, MDE %.4f, share %.3f", control, y,
                 summaries[y]["sd"], summaries[y]["mde"], summaries[y]["share_abs_ge_abs_beta"])
    design_txt = (f"{pc['draws']} draws on pre-policy weeks {pc['window']}: fake policy week "
                  f"uniform over weeks with >= {k} weeks on each side, {len(sets['cbd'])} random "
                  "Manhattan zones as fake CBD (pairs within the fake set); control = "
                  + ("pairs within the other Manhattan zones" if control == "donut" else
                     "the outer-borough pairs") + f"; static window <= {pc['pre_weeks']} weeks "
                  "before the fake week to the end of the pre-policy data; pair + week FE, "
                  "weighted by trips")
    return {"design": design_txt, "outcomes": summaries}, pd.concat(frames)


def fingerprint(cfg: dict, p: pd.DataFrame) -> str:
    root = Path(__file__).resolve().parents[1]
    code = [Path(__file__), *sorted((root / "src" / "taxi_shock" / "causal").glob("*.py"))]
    payload = {"code": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in code},
               "cfg": {k: cfg[k] for k in ("speed", "causal", "data", "seed")},
               "panel": [len(p), int(p["n_trips"].sum()), int(p["n_used"].sum())]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def cached(name: str, fp: str, unit_dir: Path, force: bool, compute):
    """Return the cached unit `name` if its fingerprint matches, else compute and store it."""
    f = unit_dir / f"{name}.pkl"
    if not force and f.exists():
        with f.open("rb") as fh:
            stored = pickle.load(fh)
        if stored.get("fingerprint") == fp:
            LOG.info("unit %s: done earlier, skipped", name)
            return stored["value"]
    value = compute()
    unit_dir.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.tmp")
    with tmp.open("wb") as fh:
        pickle.dump({"fingerprint": fp, "value": value}, fh)
    os.replace(tmp, f)
    return value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="recompute every unit")
    ap.add_argument("--only", choices=["analyse_donut", "power_donut", "analyse_outer",
                                       "power_outer"],
                    help="compute (or load) this unit, write its partial result, and stop")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    unit_dir = path("forecasts", cfg) / "speed_units"
    p, wx, sets = load(cfg)
    fp = fingerprint(cfg, p)
    LOG.info("speed panel: %d cells, %d trips (%s)", len(p), int(p["n_trips"].sum()),
             p.groupby("region")["n_trips"].sum().to_dict())
    exclusions(p).to_csv(res / "speed_exclusions.csv", index=False, lineterminator="\n",
                         float_format="%.6g")
    a = pair_week(p)
    es_all, het_all, pw, draws = [], [], {}, []
    for control, fname in (("donut", "speed_did.json"), ("outer", "speed_did_outer.json")):
        if args.only and args.only not in (f"analyse_{control}", f"power_{control}"):
            continue
        out, es, het = cached(f"analyse_{control}", fp, unit_dir, args.force,
                              lambda c=control: analyse(p, a, wx, sets, c, cfg))
        (res / fname).write_text(json.dumps(out, indent=2, default=str) + "\n")
        if args.only == f"analyse_{control}":
            LOG.info("unit %s written to %s; stopping (--only)", args.only, fname)
            return
        es_all += es
        het_all += het
        pw[control], d = cached(f"power_{control}", fp, unit_dir, args.force,
                                lambda c=control, o=out: power(a, sets, c, o, cfg))
        draws.append(d)
        if args.only == f"power_{control}":
            LOG.info("unit %s cached; stopping (--only)", args.only)
            return
    pd.concat(es_all, ignore_index=True).to_csv(res / "speed_event_study.csv", index=False,
                                                lineterminator="\n", float_format="%.6g")
    pd.DataFrame(het_all).to_csv(res / "speed_heterogeneity.csv", index=False,
                                 lineterminator="\n", float_format="%.6g")
    pd.concat(draws, ignore_index=True).to_csv(res / "speed_placebo.csv", index=False,
                                               lineterminator="\n", float_format="%.6g")
    donut_speed = pw["donut"]["outcomes"]["log_mean_speed_mph"]
    (res / "speed_power.json").write_text(json.dumps(
        {"outcome": "log_mean_speed_mph (top level: donut control, pre-registered)",
         "design": pw["donut"]["design"], **donut_speed, "by_control": pw},
        indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
