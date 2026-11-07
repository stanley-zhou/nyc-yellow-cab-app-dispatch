"""Rolling-origin backtest.

Phase 0 supports `--smoke` only (seasonal naive on the sample month). The full Phase-2 backtest
(all models, both windows, 2024 test year) is added in Phase 2.

Usage:
    python scripts/04_backtest.py --smoke
"""

from __future__ import annotations

import argparse
import logging

from taxi_shock.backtest import BacktestSpec, daily_origins, evaluate, run_backtest
from taxi_shock.config import load_config, path
from taxi_shock.io import read_hourly_demand
from taxi_shock.models.seasonal_naive import SeasonalNaive


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--smoke", action="store_true", required=True,
                    help="(Phase 0) run the sample-month seasonal-naive backtest")
    ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    smoke(load_config())


if __name__ == "__main__":
    main()
