"""Rolling-origin backtest (PLAN Phase 2).

Reads fct_hourly_zone_demand and the weather/holiday inputs from data/warehouse.duckdb
(data/smoke.duckdb with --smoke), results/modeled_zones.json and results/lgbm_params.json, and
config `forecast`, `forecast_eval`, `models`. Smoke run writes results/smoke/forecasts_smoke.parquet
and results/smoke/backtest_smoke.csv; the full run writes the files below.

    --smoke   Phase 0: seasonal naive on the sample month (results/smoke/)
    --full    every trained model x training window x period:
                models  seasonal_naive, stat_ets_profile, lgbm_quantile (--models to subset)
                windows forecast.backtest.windows (expanding, sliding_24m)
                periods validation (models.validation_year: split-conformal calibration) and
                        test (forecast.backtest.pre_shock_test)
              daily origins, refit forecast.backtest.refit (monthly). Forecasts (with actuals and
              the MASE scale) go to data/forecasts/<model>__<window>__<period>.parquet
              (git-ignored, large); metrics are computed by scripts/04b_evaluate.py.

Resumable: a (model, window, period) whose forecast file already exists is skipped (logged);
`--force` recomputes it. Each file is written only when its run has finished.

Run records in results/: every LightGBM refit (rows, rounds, wall time) -> lgbm_refits.csv; per
AutoETS run the number of refits, zone fits, failed fits and weekly-naive fallbacks ->
stat_runs.csv.

A window whose training start equals model_start at every origin of a period (sliding_24m in the
validation year, while fewer than 24 months exist) trains the same models as `expanding`; its
forecasts are copied from the expanding run instead of being recomputed, and the copy is logged.

Usage:
    python scripts/04_backtest.py --smoke
    python scripts/04_backtest.py --full [--models M ...] [--periods P ...] [--windows W ...]
                                         [--force]
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import time

import pandas as pd

from taxi_shock.backtest import BacktestSpec, daily_origins, evaluate, run_backtest, window_start
from taxi_shock.config import load_config, path
from taxi_shock.io import read_exog, read_hourly_demand, read_modeled_panel
from taxi_shock.models.lgbm_quantile import GlobalLGBMQuantile
from taxi_shock.models.seasonal_naive import SeasonalNaive
from taxi_shock.models.stat_baselines import ETSDailyProfile

MODELS = ["seasonal_naive", "stat_ets_profile", "lgbm_quantile"]


def smoke(cfg: dict) -> None:
    sm = cfg["smoke"]
    panel = read_hourly_demand(path("smoke_warehouse", cfg), cfg=cfg)
    spec = BacktestSpec(
        origins=daily_origins(*sm["backtest_origins"]),
        quantiles=tuple(cfg["forecast"]["quantiles"]),
        window="expanding",
        refit=cfg["forecast"]["backtest"]["refit"],
        model_start=None,  # the smoke panel holds one month only
    )
    fc = run_backtest(panel, SeasonalNaive, spec)
    ev = cfg["forecast_eval"]
    table = evaluate(fc, spec.quantiles, ev["horizon_buckets"], interval=tuple(ev["interval"]))
    out = path("smoke.results_dir", cfg)
    out.mkdir(parents=True, exist_ok=True)
    fc.to_parquet(out / "forecasts_smoke.parquet", index=False)
    table.to_csv(out / "backtest_smoke.csv", index=False)
    logging.info("smoke backtest: %d forecast rows, %d metric rows -> %s",
                 len(fc), len(table), out)


FIT_LOG: list[dict] = []   # one entry per LightGBM refit (rows, rounds, wall time)
STAT_FITS: list[ETSDailyProfile] = []   # every AutoETS refit of the current run


def factories(cfg: dict, exog: pd.DataFrame) -> dict:
    mc = cfg["models"]
    sc = mc["stat"]

    def stat():
        m = ETSDailyProfile(sc["daily_season_length"], sc["profile_weeks"], sc["residual_weeks"])
        STAT_FITS.append(m)   # fallbacks are counted on the instance during predict
        return m

    class LoggedLGBM(GlobalLGBMQuantile):
        def fit(self, history, train_start=None):
            super().fit(history, train_start)
            FIT_LOG.append(dict(self.fit_info_))
            logging.info("lgbm refit: %s", self.fit_info_)
            return self

    def lgbm():
        tuned = json.loads((path("results", cfg) / "lgbm_params.json").read_text())
        return LoggedLGBM(exog, cfg["forecast"]["quantiles"], tuned["params"],
                          {float(k): v for k, v in tuned["rounds"].items()},
                          seed=cfg["seed"], threads=mc["threads"],
                          predict_history_days=mc["lgbm"]["predict_history_days"],
                          early_stopping=mc["lgbm"].get("refit_early_stopping"))

    return {"seasonal_naive": SeasonalNaive, "stat_ets_profile": stat, "lgbm_quantile": lgbm}


def forecast_path(cfg: dict, model: str, window: str, period: str):
    return path("forecasts", cfg) / f"{model}__{window}__{period}.parquet"


def full(cfg: dict, models: list[str], periods: list[str], windows: list[str],
         force: bool = False) -> None:
    mc = cfg["models"]
    ms = pd.Timestamp(cfg["data"]["model_start"])
    period_range = {"validation": mc["validation_year"],
                    "test": cfg["forecast"]["backtest"]["pre_shock_test"]}
    end = max(pd.Timestamp(period_range[p][1]) for p in periods) + pd.Timedelta(days=1)
    load0 = (ms - pd.Timedelta(days=mc["feature_history_days"])).date().isoformat()
    zones = json.loads((path("results", cfg) / "modeled_zones.json").read_text())["zone_ids"]
    db = path("warehouse", cfg)
    panel = read_modeled_panel(db, zones, load0, end.date().isoformat(), cfg)
    exog = read_exog(db, load0, end.date().isoformat(), cfg)
    make = factories(cfg, exog)
    path("forecasts", cfg).mkdir(parents=True, exist_ok=True)
    for model in models:
        for period in periods:
            origins = daily_origins(*period_range[period])
            for window in windows:
                out = forecast_path(cfg, model, window, period)
                if out.exists() and not force:
                    logging.info("%s %s %s: %s exists, skipped (--force recomputes)", model,
                                 window, period, out.name)
                    continue
                same = window != "expanding" and all(
                    window_start(o, window, ms) == ms for o in origins)
                if same and forecast_path(cfg, model, "expanding", period).exists():
                    fc = pd.read_parquet(forecast_path(cfg, model, "expanding", period))
                    fc["window"] = window
                    write_atomic(fc, out)
                    logging.info("%s %s %s: identical training sets -> copied from expanding",
                                 model, window, period)
                    continue
                t0 = time.perf_counter()
                spec = BacktestSpec(origins=origins,
                                    quantiles=tuple(cfg["forecast"]["quantiles"]),
                                    window=window, refit=cfg["forecast"]["backtest"]["refit"],
                                    model_start=ms, scale_start=ms)
                n_log = len(FIT_LOG)
                STAT_FITS.clear()
                fc = run_backtest(panel, make[model], spec)
                fc["model"] = model
                write_atomic(fc, out)
                if model == "lgbm_quantile":
                    write_fit_log(cfg, FIT_LOG[n_log:], window, period)
                if model == "stat_ets_profile":
                    write_run_record(cfg, "stat_runs.csv", pd.DataFrame([stat_record(
                        STAT_FITS, window, period)]))
                logging.info("%s %s %s: %d rows in %.0fs -> %s", model, window, period, len(fc),
                             time.perf_counter() - t0, out.name)


def write_atomic(fc: pd.DataFrame, out) -> None:
    """Write via a temporary file + rename, so a killed run never leaves a partial file that a
    rerun would take as finished."""
    tmp = out.with_name(f".{out.name}.tmp")
    fc.to_parquet(tmp, index=False)
    os.replace(tmp, out)


def stat_record(fits: list[ETSDailyProfile], window: str, period: str) -> dict:
    """One AutoETS run: refits, zone fits, failed fits (weekly-naive fallback for the whole
    refit period) and forecast-day fallbacks (ETS fit or forward failed for a zone-day)."""
    return {"model": "stat_ets_profile", "window": window, "period": period,
            "refits": len(fits), "zone_fits": sum(len(m.models_) for m in fits),
            "zone_fit_failures": sum(v is None for m in fits for v in m.models_.values()),
            "zone_day_fallbacks": sum(m.fallbacks_ for m in fits)}


def write_fit_log(cfg: dict, entries: list[dict], window: str, period: str) -> None:
    """Replace this run's rows of results/lgbm_refits.csv (one row per LightGBM refit)."""
    rows = pd.DataFrame([{**{k: v for k, v in e.items() if k != "rounds"},
                          **{f"rounds_q{k}": v for k, v in e["rounds"].items()},
                          "window": window, "period": period} for e in entries])
    write_run_record(cfg, "lgbm_refits.csv", rows)


def write_run_record(cfg: dict, name: str, rows: pd.DataFrame) -> None:
    """Replace the (window, period) rows of results/<name>; locked, as runs may be parallel."""
    f = path("results", cfg) / name
    with open(f.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if f.exists():
            old = pd.read_csv(f)
            keys = rows[["window", "period"]].drop_duplicates()
            old = old.merge(keys, how="left", indicator=True)
            old = old[old.pop("_merge") == "left_only"]
            rows = pd.concat([old, rows], ignore_index=True)
        rows.sort_values(["period", "window"], kind="stable").to_csv(f, index=False,
                                                                      lineterminator="\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--full", action="store_true")
    ap.add_argument("--models", nargs="+", default=MODELS, choices=MODELS)
    ap.add_argument("--periods", nargs="+", default=["validation", "test"],
                    choices=["validation", "test"])
    ap.add_argument("--windows", nargs="+", default=None,
                    help="subset of forecast.backtest.windows (default: all)")
    ap.add_argument("--force", action="store_true", help="recompute existing forecast files")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if args.smoke:
        smoke(cfg)
    else:
        windows = args.windows or cfg["forecast"]["backtest"]["windows"]
        full(cfg, args.models, args.periods, windows, args.force)


if __name__ == "__main__":
    main()
