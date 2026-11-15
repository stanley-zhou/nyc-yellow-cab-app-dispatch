"""Phase 3: where the forecaster breaks (PLAN Phase 3).

Reads fct_hourly_zone_demand and the weather/holiday inputs from data/warehouse.duckdb,
results/lgbm_params.json, results/modeled_zones.json, results/zone_summary.csv, the Phase-2
backtest forecasts (data/forecasts/lgbm_quantile__expanding__test.parquet), the imported Chronos-2
forecasts (results/chronos_forecasts*.parquet) and config `shock`. Writes the files named below,
plus results/drift_calibration_series.csv (the calibration-period monitor series).

1. Frozen models (`shock.frozen_train_end` = 2024-12-31):
   - LightGBM (primary window `expanding` from model_start), fitted ONCE with the same procedure
     as every Phase-2 refit (tuned parameters, early stopping on the last 4 weeks of the
     training window) -> boosters in data/models/ (git-ignored), record results/frozen_model.json
   - SeasonalNaive with its residual quantiles frozen on the same training window
   - Chronos-2 zero-shot: the imported forecasts (main run; both weather variants)
2. Day-ahead forecasts for every origin in `shock.forecast_window` (2024-07-01 -> 2026-09-30),
   no retraining; features use the actuals up to each origin as always.
   The frozen LightGBM's 2024-H2 forecasts are in-sample (its training window ends 2024-12-31);
   they are kept as series `frozen` and flagged. The reference series for monitoring and F3,
   `monitored`, is out-of-sample throughout: the Phase-2 backtest forecasts (expanding window,
   monthly refits) up to `shock.monitor_start` - 1 day, then the frozen model.
3. Rolling 4-week (`shock.rolling_days`) WAPE, mean signed error (forecast - actual, the
   project's `bias` convention) and log(actual / forecast) per zone group, plus the daily
   values -> results/shock_errors.csv
4. Drift monitors on the daily log(actual / forecast) of each monitored group (`monitored`
   series), standardized with 2024 (out-of-sample) moments: two-sided CUSUM with h calibrated
   to <= 1 false alarm over 2024, and the rolling-bias rule -> results/drift_detection.json

Resumable: data/models/frozen_lgbm_q*.txt and data/forecasts/frozen/<model>.parquet are reused
when present (`--force` recomputes); every write is atomic.

Usage:
    python scripts/06_shock.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from taxi_shock.chronos_runs import MAIN, with_run
from taxi_shock.config import load_config, path, repo_root
from taxi_shock.drift import (
    calibrate_h,
    cusum,
    rolling_bias_alarms,
    rolling_mean_z,
    standardize,
)
from taxi_shock.evaluation import sort_clip_quantiles
from taxi_shock.io import read_exog, read_modeled_panel
from taxi_shock.models.lgbm_quantile import GlobalLGBMQuantile
from taxi_shock.models.seasonal_naive import SeasonalNaive
from taxi_shock.outages import outage_days
from taxi_shock.shock import daily_table, forecast_frozen, rolling_table

LOG = logging.getLogger("shock")
QCOLS = ["q10", "q50", "q90"]
CAL_ROWS: list[pd.DataFrame] = []         # calibration-period daily series (drift monitors)
FC_COLS = ["model", "series", "zone_id", "origin", "target_ts", "horizon", "y", "point",
           *QCOLS]


def sha256_file(f: Path) -> str:
    h = hashlib.sha256()
    with f.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_parquet(df: pd.DataFrame, f: Path) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, f)


# ----------------------------------------------------------------------------- frozen models
def frozen_lgbm(cfg: dict, panel: pd.DataFrame, exog: pd.DataFrame, force: bool
                ) -> GlobalLGBMQuantile:
    mc, sh = cfg["models"], cfg["shock"]
    tuned = json.loads((path("results", cfg) / "lgbm_params.json").read_text())
    qs = cfg["forecast"]["quantiles"]
    model = GlobalLGBMQuantile(exog, qs, tuned["params"],
                               {float(k): v for k, v in tuned["rounds"].items()},
                               seed=cfg["seed"], threads=mc["threads"],
                               predict_history_days=mc["lgbm"]["predict_history_days"],
                               early_stopping=mc["lgbm"]["refit_early_stopping"])
    mdir = repo_root() / "data" / "models"
    files = {q: mdir / f"frozen_lgbm_q{round(q * 100):02d}.txt" for q in qs}
    record = path("results", cfg) / "frozen_model.json"
    if not force and record.exists() and all(f.exists() for f in files.values()):
        rec = json.loads(record.read_text())
        model.boosters_ = {q: lgb.Booster(model_file=str(f)) for q, f in files.items()}
        if "booster_files" not in rec:
            raise RuntimeError("results/frozen_model.json has no booster hashes (recorded from "
                               "the review-fix version on); refit with --force")
        for q, f in files.items():          # refuse boosters that are not the recorded ones
            b = rec["booster_files"][str(q)]
            if sha256_file(f) != b["sha256"] or model.boosters_[q].num_trees() != b["num_trees"]:
                raise RuntimeError(f"{f.name} does not match results/frozen_model.json "
                                   "(sha256 / num_trees); refit with --force")
        model.zones_ = rec["zones"]
        LOG.info("frozen LightGBM loaded (%s), rounds %s", record.name, rec["fit"]["rounds"])
        return model
    end = pd.Timestamp(sh["frozen_train_end"]) + pd.Timedelta(days=1)
    start = pd.Timestamp(cfg["data"]["model_start"])
    history = panel[panel["hour_ts"] < end]
    model.fit(history, train_start=start)
    mdir.mkdir(parents=True, exist_ok=True)
    for q, f in files.items():
        tmp = f.with_name(f".{f.name}.tmp")
        model.boosters_[q].save_model(str(tmp))
        os.replace(tmp, f)
    rec = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "model": "lgbm_quantile", "window": "expanding",
           "procedure": "one fit with the Phase-2 refit procedure: tuned parameters "
                        "(results/lgbm_params.json), early stopping on the last "
                        f"{mc['lgbm']['refit_early_stopping']['holdout_weeks']} weeks of the "
                        "training window (not boosted on), stopped boosters used as is",
           "params": tuned["params"], "fit": model.fit_info_, "zones": model.zones_,
           "boosters": {str(q): str(f.relative_to(repo_root())) for q, f in files.items()},
           "booster_files": {str(q): {"sha256": sha256_file(f),
                                      "num_trees": model.boosters_[q].num_trees()}
                             for q, f in files.items()},
           "in_sample_note": "forecasts for target days up to the training end are in-sample "
                             "(holdout weeks: used for early stopping, not boosted on)"}
    record.write_text(json.dumps(rec, indent=2) + "\n")
    LOG.info("frozen LightGBM fitted: %s", model.fit_info_)
    return model


def frozen_forecasts(cfg: dict, force: bool) -> dict[str, pd.DataFrame]:
    sh, mc = cfg["shock"], cfg["models"]
    zones = json.loads((path("results", cfg) / "modeled_zones.json").read_text())["zone_ids"]
    origins = pd.date_range(*sh["forecast_window"], freq="D")
    qs = cfg["forecast"]["quantiles"]
    fdir = path("forecasts", cfg) / "frozen"
    files = {m: fdir / f"{m}.parquet" for m in ("lgbm_quantile", "seasonal_naive")}
    if not force and all(f.exists() for f in files.values()):
        LOG.info("frozen forecasts exist, reused (--force recomputes)")
        return {m: pd.read_parquet(f) for m, f in files.items()}
    load0 = (pd.Timestamp(cfg["data"]["model_start"])
             - pd.Timedelta(days=mc["feature_history_days"])).date().isoformat()
    end = (origins[-1] + pd.Timedelta(days=1)).date().isoformat()
    db = path("warehouse", cfg)
    panel = read_modeled_panel(db, zones, load0, end, cfg)
    panel = panel.sort_values(["hour_ts", "zone_id"], kind="stable").reset_index(drop=True)
    exog = read_exog(db, load0, end, cfg)
    out = {}
    train_end = pd.Timestamp(sh["frozen_train_end"]) + pd.Timedelta(days=1)
    for m, f in files.items():
        if not force and f.exists():
            out[m] = pd.read_parquet(f)
            LOG.info("%s: %s exists, reused", m, f.name)
            continue
        if m == "lgbm_quantile":
            model = frozen_lgbm(cfg, panel, exog, force)
        else:
            model = SeasonalNaive().fit(panel[panel["hour_ts"] < train_end],
                                        train_start=pd.Timestamp(cfg["data"]["model_start"]))
        t0 = time.perf_counter()
        fc = forecast_frozen(model, panel, origins, qs,
                             history_days=int(cfg["shock"]["forecast_history_days"]))
        secs = time.perf_counter() - t0
        LOG.info("%s frozen: %d rows in %.0f s", m, len(fc), secs)
        rec_f = path("results", cfg) / "frozen_model.json"
        rec = json.loads(rec_f.read_text())
        rec.setdefault("forecast_runtime", {})[m] = {"origins": len(origins), "rows": len(fc),
                                                    "seconds": round(secs, 1)}
        rec_f.write_text(json.dumps(rec, indent=2) + "\n")
        _atomic_parquet(fc, f)
        out[m] = fc
    return out


# ------------------------------------------------------------------------------ the series
def build_series(cfg: dict, frozen: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """All forecast series of Phase 3 in one frame (FC_COLS + in_sample)."""
    sh = cfg["shock"]
    lo, hi = (pd.Timestamp(x) for x in sh["forecast_window"])
    cal_lo = pd.Timestamp(sh["calibration_period"][0])
    mon = pd.Timestamp(sh["monitor_start"])
    train_end = pd.Timestamp(sh["frozen_train_end"]) + pd.Timedelta(days=1)
    parts = []
    for m, fc in frozen.items():
        parts.append(fc.assign(model=m, series="frozen",
                               in_sample=(fc["target_ts"] < train_end) & (m == "lgbm_quantile")))
    # out-of-sample reference: Phase-2 backtest (calibration period onwards) then frozen model
    bt = pd.read_parquet(path("forecasts", cfg) / "lgbm_quantile__expanding__test.parquet")
    bt = bt[(bt["origin"] >= cal_lo) & (bt["origin"] < mon)]
    fz = frozen["lgbm_quantile"]
    parts.append(pd.concat([bt, fz[fz["origin"] >= mon]], ignore_index=True).assign(
        model="lgbm_quantile", series="monitored", in_sample=False))
    # Chronos-2 zero-shot (main run), same post-processing as in Phase 2
    root = repo_root()
    ch = pd.concat([with_run(pd.read_parquet(root / cfg["chronos"][k]))
                    for k in ("test_output", "post_output")], ignore_index=True)
    ch = ch[(ch["run"] == MAIN) & (ch["origin"] >= cal_lo) & (ch["origin"] <= hi)]
    ch = sort_clip_quantiles(ch.drop(columns="run"), QCOLS)
    ch["zone_id"] = ch["zone_id"].astype("int64")
    act = pd.concat([bt[["zone_id", "target_ts", "y"]], fz[["zone_id", "target_ts", "y"]]]
                    ).drop_duplicates(["zone_id", "target_ts"])
    ch = ch.merge(act, on=["zone_id", "target_ts"], how="left")
    for v, d in ch.groupby("variant"):
        parts.append(d.drop(columns="variant").assign(model=f"chronos2_{v}", series="zero_shot",
                                                      in_sample=False))
    allfc = pd.concat([p[FC_COLS + ["in_sample"]] for p in parts], ignore_index=True)
    allfc["zone_id"] = allfc["zone_id"].astype("int64")
    keep = (allfc["origin"] >= lo) | (allfc["series"].isin(["monitored", "zero_shot"]))
    return allfc[keep & (allfc["origin"] <= hi)].reset_index(drop=True)


def group_members(cfg: dict) -> dict[str, list[int]]:
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv").set_index("zone_id")
    zones = json.loads((path("results", cfg) / "modeled_zones.json").read_text())["zone_ids"]
    zs = zs.loc[zones]
    out = {}
    for g in cfg["shock"]["groups"]:
        if g == "all":
            out[g] = list(zones)
        elif g == "non_cbd":
            out[g] = zs.index[~zs["is_cbd"]].tolist()
        else:
            out[g] = zs.index[zs["zone_group"] == g].tolist()
        if not out[g]:
            raise ValueError(f"zone group {g} has no modeled zones")
    return out


# ------------------------------------------------------------------------------ monitors
def monitors(cfg: dict, daily: pd.DataFrame, model: str, series: str) -> dict:
    sh = cfg["shock"]
    cal_lo, cal_hi = (pd.Timestamp(x) for x in sh["calibration_period"])
    mon = pd.Timestamp(sh["monitor_start"])
    policy = pd.Timestamp(cfg["data"]["policy_date"])
    end = pd.Timestamp(sh["forecast_window"][1])
    cu, rb = sh["cusum"], sh["rolling_bias"]
    grid = np.arange(cu["h_grid"][0], cu["h_grid"][1] + 1e-9, cu["h_grid"][2])
    out = {}
    for g in sh["monitored_groups"]:
        d = daily[(daily["model"] == model) & (daily["series"] == series)
                  & (daily["zone_group"] == g)].set_index("day").sort_index()
        x = np.log(d["actual"] / d["forecast"])
        x = x[~x.index.isin(outage_days(cfg))]    # source outages are not demand
        cal = x[(x.index >= cal_lo) & (x.index <= cal_hi)]
        run = x[(x.index >= mon) & (x.index <= end)]
        if len(cal) != (cal_hi - cal_lo).days + 1 or run.index.to_series().diff().max() > \
                pd.Timedelta(days=1):
            raise ValueError(f"{model}/{series}/{g}: calibration or monitoring days missing")
        z_cal, mu, sd = standardize(cal, cal)
        z_run = (run - mu) / sd
        h, n_cal = calibrate_h(z_cal.to_numpy(), cu["k"], cu["max_false_alarms"], grid)
        _, _, al = cusum(z_run.to_numpy(), cu["k"], h)
        rb_cal = rolling_bias_alarms(z_cal.to_numpy(), rb["n_sigma"], rb["consecutive_days"])
        rb_run = rolling_bias_alarms(z_run.to_numpy(), rb["n_sigma"], rb["consecutive_days"])
        # calibration-period alarms, saved (Phase 3 review, fix 1): at h and one grid step below
        _, _, al_cal = cusum(z_cal.to_numpy(), cu["k"], h)
        _, _, al_cal_lo = cusum(z_cal.to_numpy(), cu["k"], h - cu["h_grid"][2])
        # rolling reading of the bias rule (fix 2): trailing-window mean of z, own 2024 sd
        rm_cal, rm_run, rm_sd = rolling_mean_z(z_cal.to_numpy(), z_run.to_numpy(),
                                               rb["rolling_window_days"])
        rm_cal_al = rolling_bias_alarms(np.nan_to_num(rm_cal), rb["n_sigma"],
                                        rb["consecutive_days"])
        rm_run_al = rolling_bias_alarms(np.nan_to_num(rm_run), rb["n_sigma"],
                                        rb["consecutive_days"])
        CAL_ROWS.append(pd.DataFrame({"model": model, "series": series, "zone_group": g,
                                      "day": z_cal.index, "log_actual_over_forecast":
                                      cal.to_numpy(), "z": z_cal.to_numpy()}))

        def cal_dates(alarms, z=z_cal):
            return [{"date": str(z.index[a.position].date()), "side": a.side} for a in alarms]

        def summary(alarms, z=z_run):
            dates = [(z.index[a.position], a.side) for a in alarms]
            before = [(str(t.date()), s) for t, s in dates if t < policy]
            after = [(t, s) for t, s in dates if t >= policy]
            first = after[0] if after else None
            return {"first_alarm_on_or_after_policy": None if first is None else
                    {"date": str(first[0].date()), "side": first[1],
                     "delay_days": int((first[0] - policy).days)},
                    "alarms_before_policy": [{"date": t, "side": s} for t, s in before],
                    "n_alarms_monitoring": len(dates),
                    "alarms": [{"date": str(t.date()), "side": s} for t, s in dates]}

        out[g] = {
            "series": "daily log(sum actual / sum forecast) over the group's modeled zones",
            "calibration": {"period": [str(cal_lo.date()), str(cal_hi.date())],
                            "n_days": len(cal), "mean": round(mu, 6), "sd": round(sd, 6)},
            "monitoring_period": [str(run.index.min().date()), str(run.index.max().date())],
            "cusum": {"k": cu["k"], "h": h, "h_rule": f"smallest h on the grid "
                      f"{cu['h_grid']} with <= {cu['max_false_alarms']} alarm(s) over the "
                      "calibration period", "false_alarms_in_calibration": n_cal,
                      "calibration_alarms": cal_dates(al_cal),
                      "calibration_alarms_one_grid_step_below_h": {
                          "h": round(h - cu["h_grid"][2], 6), "alarms": cal_dates(al_cal_lo)},
                      **summary(al)},
            "rolling_bias": {"n_sigma": rb["n_sigma"],
                             "consecutive_days": rb["consecutive_days"],
                             "false_alarms_in_calibration": len(rb_cal),
                             "reading": "daily z (pre-registered, primary)", **summary(rb_run)},
            "rolling_bias_rolling_mean": {
                "reading": f"trailing {rb['rolling_window_days']}-day mean of z, standardized "
                           "by its own calibration-period sd (review fix 2; secondary)",
                "rolling_mean_sd_calibration": round(rm_sd, 6), "n_sigma": rb["n_sigma"],
                "consecutive_days": rb["consecutive_days"],
                "false_alarms_in_calibration": len(rm_cal_al),
                "calibration_alarms": cal_dates(rm_cal_al), **summary(rm_run_al)},
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refit and re-forecast")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    sh, res = cfg["shock"], path("results", cfg)
    frozen = frozen_forecasts(cfg, args.force)
    allfc = build_series(cfg, frozen)
    daily = daily_table(allfc, group_members(cfg))
    table = rolling_table(daily, int(sh["rolling_days"]))
    lo = pd.Timestamp(sh["forecast_window"][0])
    table = table[table["date"] >= lo]
    table.to_csv(res / "shock_errors.csv", index=False, lineterminator="\n",
                 float_format="%.6g")
    LOG.info("shock_errors.csv: %d rows", len(table))
    det = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "policy_date": cfg["data"]["policy_date"],
           "primary": {"model": "lgbm_quantile", "series": "monitored",
                       "note": "Phase-2 out-of-sample backtest forecasts (expanding, monthly "
                               "refits) before monitor_start, the frozen model from it",
                       "groups": monitors(cfg, daily, "lgbm_quantile", "monitored")},
           "chronos2_primary_variant": {
               "model": f"chronos2_{cfg['chronos']['primary_variant']}", "series": "zero_shot",
               "groups": monitors(cfg, daily, f"chronos2_{cfg['chronos']['primary_variant']}",
                                  "zero_shot")}}
    (res / "drift_detection.json").write_text(json.dumps(det, indent=2) + "\n")
    pd.concat(CAL_ROWS, ignore_index=True).to_csv(
        res / "drift_calibration_series.csv", index=False, lineterminator="\n",
        float_format="%.6g")
    for g, r in det["primary"]["groups"].items():
        LOG.info("%s: CUSUM h=%.2f first alarm %s; rolling bias %s", g, r["cusum"]["h"],
                 r["cusum"]["first_alarm_on_or_after_policy"],
                 r["rolling_bias"]["first_alarm_on_or_after_policy"])


if __name__ == "__main__":
    main()
