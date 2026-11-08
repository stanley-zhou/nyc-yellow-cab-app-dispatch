"""Rolling-origin backtest (PLAN Phase 2).

    --smoke   Phase 0: seasonal naive on the sample month (results/smoke/)
    --full    every trained model x training window x period:
                models  seasonal_naive, stat_ets_profile, lgbm_quantile (--models to subset)
                windows forecast.backtest.windows (expanding, sliding_24m)
                periods validation (models.validation_year: split-conformal calibration) and
                        test (forecast.backtest.pre_shock_test)
              daily origins, refit forecast.backtest.refit (monthly). Forecasts (with actuals and
              the MASE scale) go to data/forecasts/<model>__<window>__<period>.parquet
              (git-ignored, large); metrics are computed by scripts/04b_evaluate.py.

A window whose training start equals model_start at every origin of a period (sliding_24m in the
validation year, while fewer than 24 months exist) trains the same models as `expanding`; its
forecasts are copied from the expanding run instead of being recomputed, and the copy is logged.

Usage:
    python scripts/04_backtest.py --smoke
    python scripts/04_backtest.py --full [--models lgbm_quantile] [--periods test]
"""

from __future__ import annotations

import argparse
import json
import logging
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


def factories(cfg: dict, exog: pd.DataFrame) -> dict:
    mc = cfg["models"]
    sc = mc["stat"]

    def stat():
        return ETSDailyProfile(sc["daily_season_length"], sc["profile_weeks"],
                               sc["residual_weeks"])

    def lgbm():
        tuned = json.loads((path("results", cfg) / "lgbm_params.json").read_text())
        return GlobalLGBMQuantile(exog, cfg["forecast"]["quantiles"], tuned["params"],
                                  {float(k): v for k, v in tuned["rounds"].items()},
                                  seed=cfg["seed"], threads=mc["threads"])

    return {"seasonal_naive": SeasonalNaive, "stat_ets_profile": stat, "lgbm_quantile": lgbm}


def forecast_path(cfg: dict, model: str, window: str, period: str):
    return path("forecasts", cfg) / f"{model}__{window}__{period}.parquet"


def full(cfg: dict, models: list[str], periods: list[str]) -> None:
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
    windows = cfg["forecast"]["backtest"]["windows"]
    for model in models:
        for period in periods:
            origins = daily_origins(*period_range[period])
            for window in windows:
                out = forecast_path(cfg, model, window, period)
                same = window != "expanding" and all(
                    window_start(o, window, ms) == ms for o in origins)
                if same and forecast_path(cfg, model, "expanding", period).exists():
                    fc = pd.read_parquet(forecast_path(cfg, model, "expanding", period))
                    fc["window"] = window
                    fc.to_parquet(out, index=False)
                    logging.info("%s %s %s: identical training sets -> copied from expanding",
                                 model, window, period)
                    continue
                t0 = time.perf_counter()
                spec = BacktestSpec(origins=origins,
                                    quantiles=tuple(cfg["forecast"]["quantiles"]),
                                    window=window, refit=cfg["forecast"]["backtest"]["refit"],
                                    model_start=ms, scale_start=ms)
                fc = run_backtest(panel, make[model], spec)
                fc["model"] = model
                fc.to_parquet(out, index=False)
                logging.info("%s %s %s: %d rows in %.0fs -> %s", model, window, period, len(fc),
                             time.perf_counter() - t0, out.name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--full", action="store_true")
    ap.add_argument("--models", nargs="+", default=MODELS, choices=MODELS)
    ap.add_argument("--periods", nargs="+", default=["validation", "test"],
                    choices=["validation", "test"])
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if args.smoke:
        smoke(cfg)
    else:
        full(cfg, args.models, args.periods)


if __name__ == "__main__":
    main()
