# Forecasting Under a Policy Shock: NYC Yellow-Taxi Demand and Congestion Pricing

**Status: Phase 2 (forecasting before the shock), in progress.** No forecasting or causal findings yet. This README is rewritten in
Phase 7 with the summary, figures and limitations; until then it only explains how to run the code.

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
make data && make dbt && make figures   # full data
make verify PHASE=1
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
| `figures` | every figure whose phase is implemented (Phase 1: F1, F1b), built from `results/` only |
| `probes` | one-off evidence scripts behind DECISIONS.md entries: duplicates, negative fares, record formats, Open-Meteo offset |
| `verify PHASE=N` | ruff, pytest, dbt test, and presence of the phase's result files (`config/phase_outputs.yaml`) |
| `forecast`, `causal`, `adapt`, `report`, `all` | added in their phases; they fail with a message until then |

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
