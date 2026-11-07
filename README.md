# Forecasting Under a Policy Shock: NYC Yellow-Taxi Demand and Congestion Pricing

**Status: Phase 0 (skeleton and smoke pipeline).** No findings yet. This README is rewritten in
Phase 7 with the summary, figures and limitations; until then it only explains how to run the code.

Scope (honest wording, PLAN §0.6): NYC TLC **yellow taxi** pickups at the TLC-zone level,
hourly, with Manhattan congestion pricing (from 2025-01-05) as a natural experiment. The
specification is [`PLAN.md`](PLAN.md); every judgement call is logged in
[`DECISIONS.md`](DECISIONS.md).

## Setup (WSL / Linux)

```bash
make setup        # uv: Python 3.12 venv in .venv, installs the package with [dev] extras
make smoke        # one sample month end to end: download -> dbt build+test -> backtest -> figure
make verify PHASE=0
```

The system Python 3.14 is not supported (missing wheels); `make setup` uses `uv` to install 3.12.
Keep the repository and `data/` on the Linux filesystem, not under `/mnt/c/`.

## Make targets

| target | what it does |
|---|---|
| `smoke` | sample month (`smoke.month` in `config/project.yaml`) through the whole pipeline; writes `results/smoke/` and `reports/figures/smoke/`; fails if over `smoke.max_runtime_minutes` |
| `data` | full raw download (yellow months in config, zone lookups, weather) |
| `dbt` | build and test the full DuckDB warehouse |
| `verify PHASE=N` | ruff, pytest, dbt test, and presence of the phase's result files (`config/phase_outputs.yaml`) |
| `forecast`, `causal`, `adapt`, `figures`, `report`, `all` | added in their phases; they fail with a message until then |

## Layout

`config/` (all dates, thresholds, paths) · `dbt/` (dbt-duckdb project over the raw Parquet) ·
`src/taxi_shock/` (library) · `scripts/` (thin CLI entry points) · `tests/` · `results/`
(git-tracked outputs; every reported number comes from here) · `reports/figures/`.

## Data

TLC trip records and the zone lookup/shapefile are public (NYC TLC); weather is from the
Open-Meteo archive API (one city-wide point). Raw files go to `data/raw/` (git-ignored);
`data/raw/manifest.csv` records each file's size and download date.
