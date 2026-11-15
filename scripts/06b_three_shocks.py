"""Phase 4b, three shocks, one monitor (PLAN Amendment 3, C5): the Phase-3 frozen-model
procedure and both drift monitors run for three events.

Reads fct_hourly_zone_demand and the weather/holiday inputs from data/warehouse.duckdb,
results/lgbm_params.json, results/modeled_zones.json, results/zone_summary.csv and config
`shocks`, `shock`.

For each event in `shocks.events` (COVID 2020-03-01, the metered-fare increase 2022-12-19,
congestion pricing 2025-01-05), identically:
  - frozen LightGBM (tuned Phase-2 parameters, early stopping on the last 4 weeks) trained on
    the `train_months` before the event day, day-ahead forecasts for `monitor_months` from it;
  - calibration: two-fold cross-fit inside the training year (a model on each half forecasts
    the other half) -> one year of out-of-sample daily residuals;
  - monitored series per group (CBD, non-CBD, all modeled zones): daily log(sum actual / sum
    forecast), source-outage days (taxi_shock.outages) left out, standardized with the
    calibration mean/sd; two-sided CUSUM (k, h rule and grid
    of `shock.cusum`: smallest h with <= 1 alarm over the calibration year) and the rolling-bias
    rule (`shock.rolling_bias`), monitoring from the event day.
Writes results/shock_comparison.json (per event and group: calibration, first alarm on or after
the event for both monitors, post-event level change) and results/shock_daily.csv (the daily
series, calibration and monitoring, per event and group).

Resumable: the forecasts of each event part (fold_a, fold_b, frozen) are cached in
data/forecasts/shocks/<event>__<part>.parquet (atomic writes; `--force` recomputes).

Usage:
    python scripts/06b_three_shocks.py [--force]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.config import load_config, path
from taxi_shock.drift import calibrate_h, cusum, rolling_bias_alarms
from taxi_shock.io import read_exog, read_modeled_panel
from taxi_shock.models.lgbm_quantile import GlobalLGBMQuantile
from taxi_shock.outages import outage_days
from taxi_shock.shock import forecast_frozen

LOG = logging.getLogger("three_shocks")


def model(cfg: dict, exog: pd.DataFrame) -> GlobalLGBMQuantile:
    mc = cfg["models"]
    tuned = json.loads((path("results", cfg) / "lgbm_params.json").read_text())
    return GlobalLGBMQuantile(exog, cfg["forecast"]["quantiles"], tuned["params"],
                              {float(k): v for k, v in tuned["rounds"].items()},
                              seed=cfg["seed"], threads=mc["threads"],
                              predict_history_days=mc["lgbm"]["predict_history_days"],
                              early_stopping=mc["lgbm"]["refit_early_stopping"])


def windows(event: pd.Timestamp, cfg: dict) -> dict:
    sc = cfg["shocks"]
    t0 = event - pd.DateOffset(months=int(sc["train_months"]))
    mid = t0 + (event - t0) / 2
    mid = mid.normalize()
    return {"train": (t0, event), "fold_a": (t0, mid), "fold_b": (mid, event),
            "monitor": (event, event + pd.DateOffset(months=int(sc["monitor_months"])))}


def part(name: str, event_key: str, cfg: dict, force: bool, compute) -> pd.DataFrame:
    f = path("forecasts", cfg) / "shocks" / f"{event_key}__{name}.parquet"
    if not force and f.exists():
        LOG.info("%s %s: cached", event_key, name)
        return pd.read_parquet(f)
    fc = compute()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.tmp")
    fc.to_parquet(tmp, index=False)
    os.replace(tmp, f)
    return fc


def run_event(key: str, date: str, cfg: dict, zones: list[int], force: bool
              ) -> pd.DataFrame:
    """Forecasts (calibration year out-of-sample + monitoring year frozen) of one event."""
    event = pd.Timestamp(date)
    w = windows(event, cfg)
    qs = cfg["forecast"]["quantiles"]
    lo = w["train"][0] - pd.Timedelta(days=cfg["models"]["feature_history_days"])
    hi = w["monitor"][1]
    db = path("warehouse", cfg)
    panel = read_modeled_panel(db, zones, lo.date().isoformat(), hi.date().isoformat(), cfg)
    panel = panel.sort_values(["hour_ts", "zone_id"], kind="stable").reset_index(drop=True)
    exog = read_exog(db, lo.date().isoformat(), hi.date().isoformat(), cfg)

    def fit_predict(train: tuple, target: tuple) -> pd.DataFrame:
        m = model(cfg, exog).fit(panel[panel["hour_ts"] < train[1]], train_start=train[0])
        LOG.info("%s: fitted on %s..%s %s", key, train[0].date(), train[1].date(),
                 m.fit_info_["rounds"])
        origins = pd.date_range(target[0], target[1] - pd.Timedelta(days=1), freq="D")
        return forecast_frozen(m, panel, origins, qs).assign(fit_rounds=json.dumps(
            m.fit_info_["rounds"]))

    a = part("fold_a", key, cfg, force, lambda: fit_predict(w["fold_a"], w["fold_b"]))
    b = part("fold_b", key, cfg, force, lambda: fit_predict(w["fold_b"], w["fold_a"]))
    fz = part("frozen", key, cfg, force, lambda: fit_predict(w["train"], w["monitor"]))
    return pd.concat([a.assign(stage="calibration"), b.assign(stage="calibration"),
                      fz.assign(stage="monitoring")], ignore_index=True)


def daily(fc: pd.DataFrame, groups: dict[str, list[int]]) -> pd.DataFrame:
    d = fc[fc["y"].notna() & fc["point"].notna()].assign(day=fc["target_ts"].dt.normalize())
    out = []
    for g, zs in groups.items():
        s = d[d["zone_id"].isin(zs)].groupby(["stage", "day"])[["y", "point"]].sum()
        out.append(s.reset_index().assign(group=g))
    t = pd.concat(out, ignore_index=True)
    t["log_ratio"] = np.log(t["y"] / t["point"])
    return t


def monitor(dd: pd.DataFrame, event: pd.Timestamp, cfg: dict) -> dict:
    sh, sc = cfg["shock"], cfg["shocks"]
    dd_all_min, dd_all_max = dd["day"].min(), dd["day"].max()
    cu, rb = sh["cusum"], sh["rolling_bias"]
    grid = np.arange(cu["h_grid"][0], cu["h_grid"][1] + 1e-9, cu["h_grid"][2])
    gaps = outage_days(cfg)                   # source outages: not demand, left out
    dd = dd[~dd["day"].isin(gaps)]
    cal = dd[dd["stage"] == "calibration"].set_index("day")["log_ratio"].sort_index()
    mon = dd[dd["stage"] == "monitoring"].set_index("day")["log_ratio"].sort_index()
    mu, sd = float(cal.mean()), float(cal.std(ddof=1))
    zc, zm = (cal - mu) / sd, (mon - mu) / sd
    h, n_cal = calibrate_h(zc.to_numpy(), cu["k"], cu["max_false_alarms"], grid)
    alarms = cusum(zm.to_numpy(), cu["k"], h)[2]
    rb_cal = rolling_bias_alarms(zc.to_numpy(), rb["n_sigma"], rb["consecutive_days"])
    rb_mon = rolling_bias_alarms(zm.to_numpy(), rb["n_sigma"], rb["consecutive_days"])

    def first(al):
        if not al:
            return None
        t = zm.index[al[0].position]
        return {"date": str(t.date()), "side": al[0].side, "delay_days": int((t - event).days),
                "n_alarms": len(al)}

    level = {}
    for n in sc["level_windows_days"]:
        x = mon[mon.index < event + pd.Timedelta(days=int(n))]
        level[f"first_{n}_days"] = {"mean_log_ratio": float(x.mean()),
                                    "pct": float(np.expm1(x.mean())), "n_days": len(x)}
    return {"source_outage_days_left_out": sorted(str(d.date()) for d in gaps
                                                   if dd_all_min <= d <= dd_all_max),
            "calibration": {"n_days": len(cal), "mean": mu, "sd": sd,
                            "period": [str(cal.index.min().date()), str(cal.index.max().date())]},
            "cusum": {"k": cu["k"], "h": h, "false_alarms_in_calibration": n_cal,
                      "first_alarm": first(alarms)},
            "rolling_bias": {"false_alarms_in_calibration": len(rb_cal),
                             "first_alarm": first(rb_mon)},
            "post_event_level": level}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--events", nargs="+", default=None,
                    help="run only these events; their results are merged into the existing "
                         "results files (one event per run, committed in between)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    zones = json.loads((res / "modeled_zones.json").read_text())["zone_ids"]
    zs = pd.read_csv(res / "zone_summary.csv").set_index("zone_id").loc[zones]
    groups = {"cbd": zs.index[zs["is_cbd"]].tolist(), "non_cbd": zs.index[~zs["is_cbd"]].tolist(),
              "all": list(zones)}
    groups = {g: groups[g] for g in cfg["shocks"]["groups"]}
    jf, cf = res / "shock_comparison.json", res / "shock_daily.csv"
    out = json.loads(jf.read_text()) if args.events and jf.exists() else {"events": {}}
    out.update({"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "procedure": "DECISIONS.md, Phase 4b (C5 specification)"})
    days = []
    old = pd.read_csv(cf, parse_dates=["day"]) if args.events and cf.exists() else None
    for key, date in cfg["shocks"]["events"].items():
        if args.events and key not in args.events:
            continue
        fc = run_event(key, date, cfg, zones, args.force)
        dd = daily(fc, groups)
        days.append(dd.assign(event=key))
        ev = {"date": date, "windows": {k: [str(a.date()), str(b.date())] for k, (a, b) in
                                         windows(pd.Timestamp(date), cfg).items()},
              "fit_rounds": {s: json.loads(fc.loc[fc["stage"] == s, "fit_rounds"].iloc[0])
                             for s in ("monitoring",)},
              "groups": {g: monitor(dd[dd["group"] == g], pd.Timestamp(date), cfg)
                         for g in groups}}
        out["events"][key] = ev
        LOG.info("%s: %s", key, {g: (v["cusum"]["first_alarm"], round(
            v["post_event_level"]["first_28_days"]["pct"], 4)) for g, v in ev["groups"].items()})
    out["events"] = {k: out["events"][k] for k in cfg["shocks"]["events"] if k in out["events"]}
    jf.write_text(json.dumps(out, indent=2) + "\n")
    new = pd.concat(days, ignore_index=True)
    if old is not None:
        new = pd.concat([old[~old["event"].isin(new["event"].unique())], new],
                        ignore_index=True)
    new.to_csv(cf, index=False, lineterminator="\n", float_format="%.6g")


if __name__ == "__main__":
    main()
