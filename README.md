# Forecasting Under a Policy Shock: NYC Yellow-Taxi Demand and Congestion Pricing

**Status: Phase 4 (causal effect) built, at Checkpoint 4 (Stanley); Phase 3 escalated (open);
Phase 2 passed review.** Results are in `results/` (Phase 2: `backtest_2024.csv`; Phase 3:
`shock_errors.csv`, `drift_detection.json`; Phase 4: `speed_did.json`, `did_static.json`,
`metric_framework.csv`); no wording of findings before Checkpoint 4. This README
is rewritten in Phase 7 with the summary, figures and limitations; until then it only explains how
to run the code.

Scope (honest wording, PLAN §0.6): NYC TLC **yellow taxi** pickups at the TLC-zone level,
hourly, with Manhattan congestion pricing (from 2025-01-05) as a natural experiment. The
specification is [`PLAN.md`](PLAN.md); every judgement call is logged in
[`DECISIONS.md`](DECISIONS.md).

## Forecasting task

*At 00:00 each day, forecast pickups for each modeled zone for each of the next 24 hours.*
Horizon 1–24, direct multi-horizon (the horizon index is a feature; lags are measured from the
origin, so lag_24 at origin = yesterday's same hour). Modeled zones: the 103 zones with mean
hourly pickups ≥ 1.0 in 2024, which carry 99.04% of 2024 pickups (`results/modeled_zones.json`,
`share_2024_pickups_modeled` = 0.990412); the other zones stay in the panel for the causal work.

## Setup (WSL / Linux)

```bash
make setup        # uv: Python 3.12 venv in .venv, installs the package with [dev] extras
make smoke        # one sample month end to end: download -> dbt build+test -> backtest -> figure
make data && make dbt                   # full data and warehouse
make forecast && make chronos-import    # Phase 2 (Chronos-2 itself runs on Colab)
make figures
make verify PHASE=2                     # N = the phase to check
```

The system Python 3.14 is not supported (missing wheels); `make setup` uses `uv` to install 3.12.
Keep the repository and `data/` on the Linux filesystem, not under `/mnt/c/`.

## Make targets

| target | what it does |
|---|---|
| `smoke` | sample month (`smoke.month` in `config/project.yaml`) through the whole pipeline; writes `results/smoke/` and `reports/figures/smoke/`; fails if over `smoke.max_runtime_minutes` |
| `data` | full raw download (yellow months in config, zone lookups, weather) |
| `dbt` | build and test the full DuckDB warehouse in two stages around the CBD mapping (`scripts/03a_cbd_map.py`), then write the Phase-1 result files (`scripts/03b_data_results.py`) and the Checkpoint-1 checks: vendor series, trip-level CBD fee check, modeled zones (`scripts/03c_checks.py`) |
| `chronos-bundle`, `chronos-import` | Phase 2: export the Chronos-2 input bundle for Colab; validate the forecasts copied back into `results/` |
| `figures` | every figure whose phase is implemented (Phase 1: F1, F1b, F1c; Phase 2: F2, F2b; Phase 3: F3; Phase 4: F4, F4b (+ html), F4c, F4d, F4e, F4f), built from `results/` only |
| `probes` | one-off evidence scripts behind DECISIONS.md entries: duplicates, negative fares, record formats, Open-Meteo offset |
| `verify PHASE=N` | ruff, pytest, dbt test, and presence of the phase's result files (`config/phase_outputs.yaml`) |
| `causal` | Phase 4: trip speed/duration DiD and event study (Amendment 2), demand DiD, event study, placebo, leave-one-out, permutation MDE and heterogeneity, metric framework, trade-off table, forecast counterfactual, pre-trend test size simulation (`07a`–`07d`; dbt marts `fct_weekly_pair_speed`, `fct_weekly_zone_trip_stats`) |
| `shock` | Phase 3: LightGBM frozen on data to 2024-12-31 and seasonal naive, day-ahead 2024-07 → 2026-09 without retraining (with Chronos-2 zero-shot), rolling 4-week errors by zone group, CUSUM and rolling-bias drift monitors (`06_shock.py`) |
| `forecast` | Phase 2: LightGBM grid on 2023 (`04a_lgbm_tune.py`), rolling-origin backtests of every trained model for 2023 and 2024 (`04_backtest.py --full`), conformal calibration and metrics (`04b_evaluate.py`); Chronos-2 runs on Colab (`chronos-bundle` / `chronos-import`) |
| `adapt`, `report` | added in their phases; they fail with a message until then (`all` runs every target) |

## Chronos-2 on Colab

Chronos-2 runs only on a Colab GPU (T4/L4), from a bundle exported here; no credentials are
involved. Two runs use the same script (`scripts/05_chronos_colab.py`):

| Run | Origins | Bundle (`make chronos-bundle ...`) | Returned files go to |
|---|---|---|---|
| `main` | 2024-01-01 → 2026-09-30 | `data/processed/chronos_bundle.zip` | `results/` |
| `calib_2023` | 2023-10-01 → 2023-12-31 (calibration history only) | `RUN=calib_2023` → `data/processed/chronos_bundle_calib_2023.zip` | `data/chronos_inbox/calib_2023/` |

1. Upload the run's zip to Google Drive and unzip it there (one folder per run).
2. In a Colab GPU runtime: `!pip install chronos-forecasting==2.3.2`, mount Drive, then
   `!python <bundle>/05_chronos_colab.py --bundle <bundle> --out-dir <bundle>/out`
   (a separate `--out-dir` per run; after a disconnect the same command resumes from its chunks).
3. Download `chronos_forecasts.parquet`, `chronos_forecasts_post.parquet` and `chronos_run.json`
   from `<out-dir>` to the run's folder above, then `make chronos-import` (main) or
   `make chronos-import RUN=calib_2023`, which validates the run against its own manifest and
   merges it into the result files (column `run`, run record
   `results/chronos_run_calib_2023.json`). Then `python scripts/04b_evaluate.py && make figures`.

## Layout

`config/` (all dates, thresholds, paths) · `dbt/` (dbt-duckdb project over the raw Parquet) ·
`src/taxi_shock/` (library) · `scripts/` (thin CLI entry points) · `tests/` · `results/`
(git-tracked outputs; every reported number comes from here) · `reports/figures/`.

## Data

TLC trip records and the zone lookup/shapefile are public (NYC TLC); weather is from the
Open-Meteo archive API (one city-wide point). Raw files go to `data/raw/` (git-ignored);
`data/raw/manifest.csv` records each file's size and download date. The 60th Street geometry for
the CBD rule comes from OpenStreetMap (ODbL) via the Overpass API.

**Why models start in 2022.** Yellow-taxi volume has not returned to its pre-COVID level: mean
daily pickups in 2024 were 48% of 2019 (`results/citywide_yearly.csv`, `ratio_to_2019` = 0.4816;
2022 and 2023 were at 0.4635 and 0.4488). Training data therefore start at `model_start =
2022-01-01`, after the 2020–2021 recovery, so the models learn the current regime rather than
the pre-COVID level.
