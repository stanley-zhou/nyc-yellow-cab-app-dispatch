# Where the Growth Came From: App Dispatch and NYC Yellow Cabs, 2023–2026

From 2023 to 2025, NYC yellow-taxi pickups grew 27.3% (703,268 → 895,177 a week). App-dispatched
trips account for all of that growth (+199,068 a week); street hails changed by −7,159 (−1.1%)
([channel_decomposition.csv](results/channel_decomposition.csv),
[presentation_numbers.json](results/presentation_numbers.json)). App dispatch means an e-hail app
(Uber, Lyft, Curb, Arro) sends the cab. The full report is
[`reports/analysis.md`](reports/analysis.md), with details in
[`reports/appendix.md`](reports/appendix.md).

[![Citywide weekly yellow-taxi pickups, street hail and app dispatch stacked, 2023 to 2026](reports/figures/F0_citywide_channels.png)](reports/figures/F0_citywide_channels.png)

| | |
|---|---|
| [![Where it happened](reports/figures/F4g_app_dispatch_map.png)](reports/figures/F4g_app_dispatch_map.png) | [![The −35% artefact](reports/figures/F4d_counterfactual_vs_did.png)](reports/figures/F4d_counterfactual_vs_did.png) |
| **Where it happened.** Zones where Uber and Lyft send yellow cabs are the zones where yellow pickups grew most. | **The −35% artefact.** A textbook difference-in-differences found a 35% drop that a forecast model did not see. |
| [![Incrementality not identified](reports/figures/F6c_incrementality.png)](reports/figures/F6c_incrementality.png) | [![Forecasting through the shift](reports/figures/F5_adaptation.png)](reports/figures/F5_adaptation.png) |
| **Are app trips additional?** Five estimators disagree beyond their intervals, so the data cannot say. | **Forecasting through the shift.** Every strategy errs at the same times; monthly retraining is slightly ahead. |

## Key results

- **Growth came from app dispatch.** Mean weekly yellow pickups +27.3% from 2023 to 2025; app
  trips +199,068 a week, street hails −7,159
  ([channel_decomposition.csv](results/channel_decomposition.csv)).
- **The app share rose in steps.** In the congestion zone (CBD) it went from 2.3% (January 2023)
  to 29.6% (January 2026) ([channel_restatement.json](results/channel_restatement.json)). At the
  largest step, in January 2025, app pickups rose 2.1- to 2.7-fold within two weeks in every area
  while street hails changed by −2.7% to +7.8%
  ([presentation_numbers.json](results/presentation_numbers.json)).
- **More cabs, not busier cabs.** From 2023 to 2025 trips per day rose 25.6% and active cabs per
  day 24.0%; trips per cab-day stayed between 14.0 and 15.0
  ([presentation_numbers.json](results/presentation_numbers.json)).
- **The −35% artefact.** The pre-registered difference-in-differences gave −34.6% for CBD pickups
  after congestion pricing; weighting zones by volume gives −5.2%, and the frozen forecast model
  +2.0% ([did_static.json](results/did_static.json),
  [figure_stats_phase4.json](results/figure_stats_phase4.json)).
- **The forecaster held up.** From February 2025 to September 2026, WAPE was 16.4% for the model
  frozen in December 2024, 16.2% with monthly retraining and 23.7% for a seasonal naive; the two
  2026 monitor alarms followed snowstorms ([adaptation_summary.json](results/adaptation_summary.json),
  [alarm_weather_check.csv](results/alarm_weather_check.csv)).

## What was tested and could not be identified

- Whether app trips are additional: estimates range from 0.52 to 2.62 across estimators in the CBD,
  and the lead placebo fails in Manhattan outside the CBD
  ([incrementality_dml.json](results/incrementality_dml.json)).
- What congestion pricing did to yellow demand, Uber and Lyft demand, or trip speed: every
  difference-in-differences fails its pre-trend test, and the synthetic control fails its
  fake-date check.
- Eight of ten pre-registered designs stopped at their pass/fail check; one passed and one passed
  on three of four outcomes, and neither identifies an effect ([presentation_numbers.json](results/presentation_numbers.json); report
  [section 4](reports/analysis.md#4-what-the-data-could-not-identify)).

## Methods and stack

- **SQL:** dbt on DuckDB, window functions; the panels, the channel split and every
  heterogeneity cut are SQL models, not pandas.
- **Snowflake:** the dbt models downstream of the cleaning run on Snowflake (dbt-snowflake,
  dialect macros) over the cleaned trips loaded with PUT / `COPY INTO`; 89/89 build steps and
  tests pass, and nine weekly, daily and hourly marts match DuckDB exactly on the days both cover
  ([dbt_targets.json](results/dbt_targets.json)).
- **Python 3.12**, managed with uv.
- **Forecasting:** LightGBM quantile regression, Chronos-2 (zero-shot, on a Colab GPU), conformal
  prediction intervals.
- **Causal designs:** difference-in-differences and event studies (pyfixest), synthetic control
  (pysyncon), double machine learning (DoubleML).
- **Monitoring:** CUSUM drift detection.
- **Engineering:** pytest, ruff, GitHub Actions.
- **Dashboard:** Tableau.

## How the work was controlled

- Expected directions and pass/fail checks were written in [`PLAN.md`](PLAN.md) before each
  analysis.
- An independent review of every phase, with its fix rounds, is in [`reviews/`](reviews/), with
  the Checkpoint 7 advisor review.
- Every judgement call is logged in [`DECISIONS.md`](DECISIONS.md) (237 entries).
- 136 tests (pytest), dbt data tests and ruff run before every review (counts:
  [presentation_numbers.json → repository](results/presentation_numbers.json)).

## Dashboard

**[Open the Tableau Public dashboard](https://public.tableau.com/app/profile/stanley.zhou7746/viz/WheretheGrowthCameFrom-NYCYellowCabsandAppDispatch/Overview)** (version 1, one page: the headline tiles, citywide
weekly pickups by channel, the app share by area and a zone map of the app share). Specification and
what version 1 includes: [`reports/dashboard_spec.md`](reports/dashboard_spec.md); extracts:
`make tableau-extract`.

## Reproduce

### Setup (WSL / Linux)

```bash
make setup        # uv: Python 3.12 venv in .venv, installs the package with [dev] extras
make smoke        # one sample month end to end: download -> dbt build+test -> backtest -> figure
make all          # everything below, in order (long: see Runtimes)
make verify PHASE=N
```

The system Python 3.14 is not supported (missing wheels); `make setup` uses `uv` to install 3.12.
Keep the repository and `data/` on the Linux filesystem, not under `/mnt/c/`. Long steps were run
under a memory cap (`systemd-run --user --scope -p MemoryMax=10G -p MemorySwapMax=0 ...`); DuckDB
uses `memory_limit = 5GB`, 10 threads.

### Make targets

| target | what it does |
|---|---|
| `smoke` | sample month (`smoke.month` in `config/project.yaml`) through the whole pipeline; writes `results/smoke/` and `reports/figures/smoke/`; fails if over `smoke.max_runtime_minutes` |
| `data` | full raw download (yellow months in config, zone lookups, weather) |
| `dbt` | build and test the DuckDB warehouse in two stages around the CBD mapping (`03a`), then the Phase-1 result files (`03b`) and Checkpoint-1 checks (`03c`) |
| `probes` | one-off evidence scripts behind DECISIONS.md entries (duplicates, negative fares, record formats, Open-Meteo offset) |
| `forecast` | Phase 2: LightGBM grid on 2023 (`04a`), rolling-origin backtests for 2023 and 2024 (`04`), conformal calibration and metrics (`04b`) |
| `chronos-bundle`, `chronos-import` | Phase 2: export the Chronos-2 input bundle for Colab; validate the forecasts copied back |
| `shock` | Phase 3: frozen LightGBM, day-ahead 2024-07 → 2026-09 without retraining, CUSUM and rolling-bias monitors (`06`); C5: the same monitor for three shocks (`06b`); daily weather for the storm check (`06c` → `results/weather_daily.csv`) |
| `causal` | Phase 4 / 4b: speed and demand DiD with checks and placebos, MDE, heterogeneity, counterfactual, test-size simulation, app-dispatch share, synthetic control (`07a`–`07f`) |
| `hvfhv` | Amendment 4: stream the high-volume FHV months (download → DuckDB aggregates → verify → delete; manifest `data/raw/hvfhv_manifest.csv`; stops below `hvfhv.min_free_gb` free on the drive named by `TAXI_SHOCK_DISK_GUARD`) (`11`) |
| `channel` | Amendment 4 / 4a: label validation D0 (`10a`), CMT contracted block (`10b`), channel decomposition D1 (`10c`), incrementality D2 (`12`), Lyft entry D3 (`13`), by-channel DiD D5 (`14`), app-share step D5b (`15`), cross-platform D4 (`17`), experiment design (`19`) |
| `fhv` | C6: congestion pricing and FHV demand, pre-trend gate first (`16`) |
| `lyft-refresh` | D3: re-download, rebuild and re-estimate once later TLC months are added to the config |
| `adapt` | Phase 5: S1 / S6 monthly refits and the S1e sensitivity (S1 on an expanding window), resumable per month; then evaluation of S0, S1, S4, S6, S1e and the seasonal-naive reference (`08`) |
| `figures` | descriptive report numbers from `results/` plus repository counts (`23` → `results/presentation_numbers.json`), then every figure from `results/`; the maps also read the TLC zone shapefile, a lookup (`09`) |
| `tableau-extract` | E2: CSV / GeoJSON extracts for the dashboard (`18`) |
| `snowflake` | E3: load the cleaned trips and HVFHV aggregates to Snowflake (`24`), `dbt build --target snowflake`, DuckDB tests, per-target row counts / tests / parity (`25`); needs `source ~/.snowflake/taxi.env` (outside the repository) and `uv pip install -e ".[snowflake]"` |
| `report` | runtimes (`20` → `results/runtimes.json`), dashboard extracts, dead-link check of README and report (`21`) |
| `verify PHASE=N` | ruff, pytest, dbt test, and presence of the phase's result files (`config/phase_outputs.yaml`) |

### Hardware and runtimes

Local: WSL2 on Windows, 12 cores, 11.68 GiB RAM
([machine_resources.json](results/machine_resources.json)). Chronos-2 ran on a Colab NVIDIA L4.
From [runtimes.json](results/runtimes.json) (`measured` = compute time the pipeline recorded;
`log_span` = wall time of runs that went start to finish once):

| Step | Time |
|---|---|
| `make smoke` (one month, end to end) | 47.6 s |
| LightGBM hyperparameter grid on 2023 | 31.8 min |
| LightGBM rolling-origin backtests, both training windows | 194.3 min wall |
| Seasonal-naive and statistical backtests | 78.6 min wall |
| Chronos-2 inference, 2024-01 → 2026-09 daily origins, two variants (Colab L4) | 269.8 min |
| Frozen-model fit | 10.9 min |
| Monthly refits, 23 per strategy (monthly retrain / with app-share features / expanding window) | 166.1 / 137.4 / 301.7 min |
| Incrementality, double machine learning with 25 repetitions | 3.4 min wall |
| Snowflake load: export, PUT, `COPY INTO` ([snowflake_load.json](results/snowflake_load.json)) | 16.0 min |
| `dbt build` on Snowflake, X-Small ([dbt_targets.json](results/dbt_targets.json)) | 63.3 s |

The raw download and the HVFHV stream ran over several resumed sessions and have no single
runtime.

### Chronos-2 on Colab

Chronos-2 runs only on a Colab GPU (T4/L4), from a bundle exported here; no credentials are
involved. Two runs use the same script (`scripts/05_chronos_colab.py`):

| Run | Origins | Bundle (`make chronos-bundle ...`) | Returned files go to |
|---|---|---|---|
| `main` | 2024-01-01 → 2026-09-30 | `data/processed/chronos_bundle.zip` | `results/` |
| `calib_2023` | 2023-10-01 → 2023-12-31 (calibration history only) | `RUN=calib_2023` → `data/processed/chronos_bundle_calib_2023.zip` | `data/chronos_inbox/calib_2023/` |

1. Upload the run's zip to Google Drive and unzip it there (one folder per run).
2. In a Colab GPU runtime: `!pip install chronos-forecasting==2.3.2`, mount Drive, then
   `!python <bundle>/05_chronos_colab.py --bundle <bundle> --out-dir <bundle>/out`
   (a separate `--out-dir` per run; after a disconnect the same command resumes from its chunks;
   `--profile N` times the stages at several batch sizes).
3. Download `chronos_forecasts.parquet`, `chronos_forecasts_post.parquet` and `chronos_run.json`
   to the run's folder above, then `make chronos-import` (main) or
   `make chronos-import RUN=calib_2023`, which validates the run against its own manifest.

### Layout

`config/` (all dates, thresholds, paths) · `dbt/` (dbt-duckdb project over the raw Parquet) ·
`src/taxi_shock/` (library) · `scripts/` (thin CLI entry points) · `tests/` · `results/`
(git-tracked outputs; every reported number comes from here) · `reports/` (analysis, figures,
dashboard specification and extracts) · `reviews/` (independent phase reviews).

## Limitations

- **Yellow taxis only for demand.** Uber and Lyft enter only as aggregates; no FHV forecasting.
- **Weather.** One city-wide Open-Meteo point; observed weather is used as if it had been known
  at the forecast origin.
- **Channel label.** Before 2026-06 "app" rests on the Flex Fare flag; platform-level results
  exist only from 2026-06; two `request_source` codes (A, CC) are undetermined.
- **Supply.** No driver- or vehicle-level data; the supply view uses TLC monthly aggregates.
- **Causal claims.** No design identified an effect (eight of ten pre-registered designs stopped at
  their pass/fail check, and the other two do not measure one); nothing here
  states a causal effect of app dispatch or of congestion pricing.

## Data and licences

- **NYC TLC trip records** (yellow taxi; high-volume FHV as aggregates), the zone lookup and
  shapefile, and the TLC monthly industry reports: public data published by the NYC Taxi &
  Limousine Commission. Raw files go to `data/raw/` (git-ignored); `data/raw/manifest.csv` and
  `data/raw/hvfhv_manifest.csv` record what was fetched so `make data` / `make hvfhv` can
  re-fetch it.
- **Weather**: Open-Meteo historical archive API (CC BY 4.0).
- **60th Street geometry** for the CBD rule: OpenStreetMap contributors (ODbL), via Overpass.

**Why models start in 2022.** Yellow-taxi volume has not returned to its pre-COVID level: mean
daily pickups in 2024 were 48% of 2019 (`results/citywide_yearly.csv`, `ratio_to_2019` = 0.4816;
2022 and 2023 were at 0.4635 and 0.4488). Training data therefore start at `model_start =
2022-01-01`, after the 2020–2021 recovery, so the models learn the current regime.
