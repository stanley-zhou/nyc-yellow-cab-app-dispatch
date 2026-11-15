# NYC Taxi Demand Under a Policy Shock — Implementation Plan

**Project working title:** *Forecasting Under a Policy Shock: NYC Taxi Demand Before and After Congestion Pricing*
**Owner:** Stanley (Yuxiang) Zhou · **Executor:** Claude Code · **Reviewer:** Stanley line by line afterwards
**Plan version:** 1.0 (2026-11-07) · Status: approved as tentative; every result below is to be produced, never assumed.

---

## 0. How to use this document

This is the full specification for Claude Code. Work through the phases in order. Each phase has a **Definition of Done (DoD)**; do not start the next phase until the current DoD passes. Rules that apply to the whole project:

1. **Never fabricate a number.** Every figure, metric and table is produced by code in this repo and saved under `results/`. If a step cannot run, write `BLOCKED: <reason>` in `DECISIONS.md` and stop.
2. **Record every judgement call** in `DECISIONS.md` as `[date] [phase] decision — reason — alternative rejected`. Every decision must be defensible.
3. **Stop and ask Stanley at every `⏸ CHECKPOINT`.** Report what was found, propose a choice, wait.
4. **No notebooks in the pipeline.** Notebooks live in `notebooks/` for exploration only; nothing in `results/` or `reports/` may depend on a notebook.
5. **Reproducibility:** `make all` on a clean machine must rebuild every figure and table from raw downloads (full run) and `make smoke` must do the same on one sample month in under 10 minutes.
6. **Honest scope wording everywhere** (README, docstrings, figures): "yellow taxi", the actual zone count, the actual date range. No "production", "deployed", "real-time".
7. Python ≥ 3.11, type hints, `ruff` clean, `pytest` green. Keep dependencies minimal and pinned in `pyproject.toml`.
8. **Quality over convenience (Stanley, 2026-11-07).** Where this plan offers a shortcut "if runtime/disk is tight", the shortcut is the last resort, taken only after reporting the cost at a checkpoint. Specifically: dbt stays (fix installation problems rather than replacing it); raw data is downloaded in full and kept on disk; the statistical baseline, Chronos-2 with daily origins, and conformal calibration are all mandatory, not optional.

---

## 1. The project in one paragraph

A probabilistic hourly demand forecasting system for NYC yellow-taxi pickups at the TLC-zone level (2022–2026), used as a measurement instrument for a real natural experiment: Manhattan congestion pricing, which began **2025-01-05** and charges taxis $0.75 and high-volume FHVs $1.50 per trip touching the Congestion Relief Zone (Manhattan south of and including 60th St). The project answers five questions in order: (1) what does demand look like, (2) how well can it be forecast before the shock, (3) where does the forecaster break after the shock, (4) how much did the policy change demand (difference-in-differences event study, cross-checked with a forecast-based counterfactual), and (5) which adaptation strategy restores forecast accuracy. Five figures, one storyline.

**What is new relative to published work** (do not overclaim; cite them in the report): the three existing studies cover ride-hailing or transit over ≤ 5 months. This project covers yellow taxis over ~20 post-policy months, compares the taxi ($0.75) and FHV ($1.50) responses if Phase 6 runs, and frames the shock from the forecasting-system side (detection delay, adaptation).

---

## 2. Facts established from the old course project (reference only, not reused as-is)

Source: `CIS5450 Final Project` shared drive (LoadData.ipynb, presentation script, proposal). Checked 2026-11-07.

| Item | Old project | Consequence for the new build |
|---|---|---|
| Scope | Yellow taxi only; **5 zones** (230, 261, 79, 237, 132); **hours 6–22 only**; 2019–2024; ≈183K rows | New build: all valid zones, all 24 hours. Old scope must not be described as "zone-level NYC" anywhere. |
| Aggregation | pandas per-month `read_parquet`, groupby zone × hour | Replace with DuckDB + dbt over Parquet; complete zone × hour grid with explicit zeros |
| Weather | Open-Meteo archive, one point (40.7128, −74.006), hourly, °F / mph / inch | Keep Open-Meteo; same point; document that weather is city-wide |
| Features | hour/dow/month cyclical, lags 1h / 24h / 168h, 4h rolling mean, weather, holiday, zone one-hot | **1-hour lag makes next-hour forecasting trivially easy.** New task = day-ahead 24-hour horizon with lags ≥ 24h |
| Models | Linear, RF, XGBoost; R² ≈ 0.94, RMSE ≈ 32; train 2019–2023, test 2024 | Rebuild with proper baselines and probabilistic metrics |
| Regimes | KMeans **3** levels (Low/Med/High); RF classifier acc ≈ 89%, macro-F1 ≈ 0.90; a parallel target, not a forecasting feature | Dropped from the new build (no decision use). |

---

## 3. Repository layout

```
nyc-yellow-cab-app-dispatch/
├── README.md                  # problem, storyline, 5 figures, how to run, limitations
├── DECISIONS.md               # decision log (see §0.2)
├── pyproject.toml             # deps pinned; [tool.ruff], [tool.pytest]
├── Makefile                   # smoke | data | dbt | forecast | causal | adapt | figures | report | all
├── config/
│   ├── project.yaml           # date ranges, zone filters, horizons, quantiles, seeds, paths
│   └── zones_cbd.csv          # zone_id, is_cbd, source note (see Phase 1)
├── data/                      # git-ignored except .gitkeep and small lookups
│   ├── raw/tlc/yellow/        # yellow_tripdata_YYYY-MM.parquet
│   ├── raw/tlc/hvfhv/         # (Phase 6)
│   ├── raw/weather/           # open-meteo hourly csv
│   ├── raw/lookup/            # taxi_zone_lookup.csv, taxi_zones.shp (+ .dbf .shx .prj)
│   └── warehouse.duckdb       # dbt target
├── dbt/                       # dbt-duckdb project
│   ├── dbt_project.yml  profiles.yml
│   └── models/
│       ├── staging/      stg_yellow_trips.sql  stg_weather.sql  stg_zones.sql
│       ├── intermediate/ int_trips_valid.sql  int_hour_grid.sql
│       └── marts/        fct_hourly_zone_demand.sql  dim_zones.sql  features_demand.sql  fct_weekly_zone_panel.sql
│       └── schema.yml    (tests)
├── src/taxi_shock/
│   ├── config.py  io.py  download.py
│   ├── features.py            # leakage-safe feature builder (python side, horizon-aware)
│   ├── models/
│   │   ├── base.py  seasonal_naive.py  stat_baselines.py  lgbm_quantile.py  chronos.py
│   ├── backtest.py            # rolling-origin engine, metrics
│   ├── metrics.py             # wape, mase, pinball, coverage, interval width
│   ├── causal/
│   │   ├── panel.py  did.py  event_study.py  placebo.py  counterfactual.py
│   ├── drift.py               # CUSUM / rolling error monitors
│   ├── adapt.py               # adaptation strategies
│   └── viz/
│       ├── style.py           # mplstyle, palette, policy-line helper
│       ├── maps.py            # choropleths
│       └── figures.py         # F1–F7 builders, one function per figure
├── scripts/                   # thin CLI wrappers: 01_download.py … 08_report.py
├── tests/                     # pytest: leakage, grid completeness, metric sanity, dbt tests via `dbt test`
├── results/                   # json/csv outputs, git-tracked (small)
├── reports/
│   ├── figures/               # F1_….png/.svg, one interactive .html
│   └── analysis.md            # ~2,000 words, the main write-up
└── notebooks/                 # exploration only
```

---

## 4. Global configuration (`config/project.yaml`) — initial values

```yaml
seed: 20260107
timezone: America/New_York
data:
  yellow_months: ["2019-01", "2026-09"]      # downloaded; EDA uses all
  model_start: "2022-01-01"                  # post-COVID recovery; see DECISIONS
  policy_date: "2025-01-05"
  pre_period:  ["2024-01-06", "2025-01-04"]  # 52 weeks
  post_period: ["2025-01-05", "2026-09-30"]
  event_study_window: ["2023-01-01", "2026-09-30"]
zones:
  valid_ids: [1, 263]                         # 264/265 = unknown → drop
  min_mean_hourly_pickups_2024: 1.0           # forecast-modeled zones threshold; see Phase 2
forecast:
  horizon_hours: 24
  origin: "00:00"                             # forecast issued at midnight for the next 24h
  min_lag_hours: 24
  quantiles: [0.1, 0.5, 0.9]
  backtest:
    pre_shock_test: ["2024-01-01", "2024-12-31"]
    refit: monthly
    windows: ["expanding", "sliding_24m"]
causal:
  outcome: "log1p_pickups"
  unit: "zone_week"                           # primary; zone_day for heterogeneity
  control: "manhattan_non_cbd"                # primary; outer_boroughs robustness
  cluster_se: "zone"
```

---

## 5. Phases

### Phase 0 — Skeleton and smoke pipeline (1 session)

**Goal:** the whole pipeline runs end-to-end on **one month** (2024-10) so every later phase only adds data.

Tasks
1. Create the layout in §3; `pyproject.toml` with: `duckdb`, `dbt-duckdb`, `polars` or `pandas`, `pyarrow`, `lightgbm`, `statsforecast`, `pyfixest`, `geopandas`, `matplotlib`, `plotly`, `holidays`, `requests`, `pyyaml`, `pytest`, `ruff`. Chronos deps in an optional extra `[chronos]` (`torch`, `chronos-forecasting`).
2. `scripts/01_download.py`: downloads TLC Parquet from `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_YYYY-MM.parquet` with resume, checksum of size, retry; `--months` arg; also `misc/taxi_zone_lookup.csv` and `misc/taxi_zones.zip` (shapefile).
3. `scripts/02_weather.py`: Open-Meteo archive, hourly, variables: `temperature_2m, apparent_temperature, precipitation, rain, snowfall, weathercode, cloudcover, windspeed_10m, relativehumidity_2m`, timezone America/New_York, yearly chunks, saved to `data/raw/weather/`.
4. dbt project wired to `data/warehouse.duckdb` reading Parquet via `read_parquet` sources.
5. `make smoke` = download 2024-10 → dbt run + test → tiny backtest (seasonal naive only) → one placeholder figure.

**DoD:** `make smoke` passes on a clean clone in < 10 min; `ruff` clean; `pytest` green; `DECISIONS.md` has its first entries.

⏸ **CHECKPOINT 0:** report disk/RAM of the machine and estimated full download size (yellow 2019-01→2026-09 ≈ 93 files, roughly 4–6 GB). Confirm with Stanley before the full download.

---

### Phase 1 — Data foundation (dbt)

**Goal:** a trusted, complete zone × hour panel plus the weekly panel for causal work, with schema-level guarantees.

dbt models
- `stg_yellow_trips`: column projection only (`tpep_pickup_datetime, tpep_dropoff_datetime, PULocationID, DOLocationID, trip_distance, fare_amount, total_amount, passenger_count, payment_type, cbd_congestion_fee` — the last exists only from 2025 files; use `try_cast`/union with NULL for earlier years). Add `source_month` from the file name.
- `int_trips_valid`: filters, each with a counted reason in `results/data_quality.json`:
  - pickup within `[source_month − 1 day, source_month + 1 month + 1 day]` (TLC files contain stragglers)
  - duration between 1 min and 3 h; `trip_distance` in (0, 100]; `fare_amount` > 0; `PULocationID` in 1–263
  - duplicate rows removed (exact duplicates)
  - Record the share filtered per month; **this replaces the unverified "≈3% invalid" claim with a measured number.**
- `stg_zones` / `dim_zones`: `zone_id, zone_name, borough, service_zone, is_cbd, is_airport, geometry_available`.
  - **`is_cbd` derivation (two-step, documented):** (a) geometric: Manhattan zones whose centroid lies south of 60th St (use the shapefile; 60th St ≈ latitude 40.7648 at 5th Ave but it is diagonal — use a line through the two endpoints of 60th St rather than a flat latitude); (b) validation from data: for 2025-02 → 2025-06, compute share of pickups per zone with `cbd_congestion_fee > 0`; zones with share > 0.8 → CBD, < 0.2 → not CBD; report disagreements with (a) and resolve manually. Save to `config/zones_cbd.csv` with the source column. Exclude the FDR/West Side Highway through-routes only if the data makes them ambiguous (note it).
- `int_hour_grid`: every hour from min to max × every valid zone (DST: timestamps are local; the duplicated fall-back hour is merged by flooring; the missing spring-forward hour is left absent and documented).
- `fct_hourly_zone_demand`: grid LEFT JOIN counts → `pickups` (0 when none), `dropoffs`, `revenue`, `mean_distance`, `n_cbd_fee_trips`. Grain: one row per (zone_id, hour_ts).
- `features_demand`: calendar (`hour, dow, dom, month, year, is_weekend, is_holiday` via `holidays.US(state='NY')`), weather joined on hour, and **lag/rolling features only at lags ≥ 24 h** computed with window functions: `lag_24, lag_48, lag_168, lag_336, mean_same_hour_prev_7d, mean_same_hour_prev_28d, mean_prev_day`. Anything shorter is forbidden by design (see Phase 2).
- `fct_weekly_zone_panel`: zone × ISO-week pickups, plus splits by hour band (`0–6, 6–10, 10–16, 16–20, 20–24`), weekday/weekend, and by `trip_distance` tercile, and by `dropoff_in_cbd`. Also zone × day variant.

dbt tests (`schema.yml`): `unique` + `not_null` on (zone_id, hour_ts); `accepted_values` for borough; `dbt_utils.expression_is_true` pickups ≥ 0; a custom test that `count(*) = n_zones × n_hours`; `is_cbd` not null for Manhattan.

Python tests: `tests/test_grid.py` (grid completeness), `tests/test_cbd_map.py` (geometric vs fee-based agreement ≥ 95% of Manhattan zones).

**Outputs:** `results/data_quality.json`, `results/zone_summary.csv`, `reports/figures/F1_demand_map.png` (log pickups per zone, 2024, CBD boundary drawn) + `F1b_citywide_weekly.png` (2019–2026 weekly pickups, COVID and policy annotated).

**DoD:** `dbt test` green on full data; F1 renders; `DECISIONS.md` records the filter thresholds, DST handling, model_start choice, CBD mapping outcome.

⏸ **CHECKPOINT 1:** show F1, the data-quality table, the CBD zone list and how many zones pass the forecasting threshold. Stanley confirms the modeled-zone set.

---

### Phase 2 — Probabilistic forecasting before the shock

**Goal:** a defensible baseline-to-model comparison on 2024 (pre-shock), with calibrated intervals.

Task definition (write this verbatim into README): *At 00:00 each day, forecast pickups for each modeled zone for each of the next 24 hours.* Horizon 1–24, direct multi-horizon (the horizon index is a feature; lags are measured from the origin, so lag_24 at origin = yesterday's same hour). This is the operational problem (dispatch planning happens the day before) and it removes the 1-hour-lag shortcut.

Modeled zones: zones with mean hourly pickups ≥ 1.0 in 2024 (expected ≈ 80–120 zones, almost all Manhattan + airports). Other zones are kept in the panel for the causal work but not forecast individually; report their share of total pickups.

Models (all through one `BaseForecaster.fit/predict_quantiles` interface)
1. `SeasonalNaive`: value at lag 168 (same hour last week). Intervals from empirical residual quantiles on the training window.
2. `StatBaseline` (mandatory): `statsforecast` AutoETS or Theta per zone with weekly seasonality, giving a three-tier comparison naive → statistical → ML.
3. `GlobalLGBMQuantile`: one LightGBM per quantile (`objective='quantile'`), global across zones with `zone_id` as categorical, features from `features_demand` + `horizon`. Modest tuning only (learning rate, leaves, min_data) by a small grid on a 2023 validation year — **no Optuna unless it changes the ranking**; record the grid.
4. `Chronos2ZeroShot` (mandatory): `amazon/chronos-2` with past covariates (weather) and known-future covariates (calendar) if the API allows. Context 2048 h, **daily origins**, run as one standalone script on Colab (T4 or L4) that reads the small panel Parquet and writes `results/chronos_forecasts.parquet` back into the repo. Note the model is zero-shot: no training on our data.

Backtest engine (`backtest.py`)
- Rolling origin, daily origins across the test year, **monthly refit** for trained models; two training windows: expanding from `model_start` and sliding 24 months. Report both; choose one as primary in `DECISIONS.md`.
- Metrics per (model, zone group, horizon bucket): **WAPE** (primary point metric; sum |e| / sum y), **MASE** scaled by in-sample seasonal-naive MAE, **pinball loss** at each quantile, **80% interval coverage** and mean width. Zone groups: CBD, Manhattan non-CBD, airports, other. Never report MAPE as primary (zeros and small counts); if reported, apply it only to hours with y ≥ 10 and say so.
- Also report the metrics on hours with y = 0 handled explicitly.

Calibration (mandatory): apply split-conformal adjustment to the LGBM intervals using 2023 residuals (per zone group) and report 80% coverage and mean width **before and after** for every model that produces intervals. The report states which intervals were calibrated and by how much.

**Outputs:** `results/backtest_2024.csv` (long format), `reports/figures/F2_model_comparison.png` (WAPE by model and zone group, baseline grey, model accent) + `F2b_fan_chart.png` (one CBD zone, one week: actual vs q10/q50/q90 for LGBM).

**DoD:** every model beats or is compared against `SeasonalNaive` with a number; coverage reported; `tests/test_leakage.py` proves no feature uses information after the origin (construct a synthetic series where future values are poisoned and assert predictions are unchanged).

⏸ **CHECKPOINT 2:** show F2/F2b and the metrics table. Decide primary window, whether Chronos stays, and whether conformal is needed.

---

### Phase 3 — Where the forecaster breaks (the shock)

**Goal:** show the structural break as a forecasting failure, separated by CBD vs non-CBD.

Tasks
1. Freeze the Phase-2 primary LGBM trained through **2024-12-31** ("frozen model"). Also freeze `SeasonalNaive` (needs no training) and Chronos (zero-shot) for comparison.
2. Run day-ahead forecasts from 2024-07-01 through 2026-09-30 without retraining.
3. Compute rolling 4-week WAPE and mean signed error (bias) per zone group. Bias is the key diagnostic: a level shift shows as persistent negative bias in CBD only.
4. Drift detection: a CUSUM on daily standardized CBD-aggregate residuals (threshold calibrated so the false-alarm rate on 2024 is ≤ 1 per year); record the **detection date and delay in days** after 2025-01-05. Also a simple rolling-bias rule (bias beyond 2σ for 7 consecutive days) as a second monitor.

**Outputs:** `results/shock_errors.csv`, `results/drift_detection.json`, `reports/figures/F3_error_over_time.png` (two lines, CBD accent / non-CBD grey, policy line, detection date marked).

**DoD:** F3 renders; detection delays recorded for both monitors; `DECISIONS.md` notes the CUSUM parameters and the false-alarm calibration.

---

### Phase 4 — How much did demand change (causal)

**Goal:** one clean DiD event study on the weekly zone panel, with the standard checks, plus a forecast-based counterfactual as the single robustness cross-check.

Design
- Panel: `fct_weekly_zone_panel`, 2023-01 → 2026-09. Outcome `log1p(pickups)`; also report `pickups` in levels for interpretability.
- Treatment: `is_cbd`. Primary control *(amended 2026-11-07, human-approved — see Amendments (human-approved))*: Manhattan non-CBD zones **excluding the six zones that straddle the 60th St line** (43, 140, 141, 142, 143, 237; "donut"; `causal.control: manhattan_non_cbd_donut`). Robustness: the full Manhattan non-CBD control (the originally approved primary); Brooklyn + Queens zones (excluding airports).
- Specification: `y_it = α_i + λ_t + Σ_k β_k · 1[t − t0 = k] · CBD_i + X_it γ + ε_it`, zone FE, week FE, weather controls (weekly mean temp, total precip), standard errors clustered by zone. Reference period: the week before 2025-01-05. Monthly event-time bins to keep the figure readable; weekly bins in the appendix table. Library: `pyfixest` (`feols`), formula string recorded.
- Static DiD: pre = 52 weeks before, post = all post weeks; report β with 95% CI; also post split into 2025-H1, 2025-H2, 2026 to show persistence.
- Checks (each a saved number, not a sentence): pre-trend joint test (all pre coefficients = 0); placebo in time (pretend policy on 2024-01-07 using 2023–2024 only); leave-one-zone-out stability of β (plot distribution); alternative control groups (full Manhattan non-CBD; Brooklyn + Queens); *(Checkpoint 1)* the static DiD on vendors present throughout the window (CMT + Curb) and on PLAN's literal filters, next to the main estimate.
- Heterogeneity (static DiD on sub-panels): hour band; weekday vs weekend; dropoff-in-CBD vs pickup-only-in-CBD; *(amended 2026-11-07)* pickup-in-CBD vs dropoff-only-in-CBD trips (the latter = control-zone pickups ending in the CBD, which pay the fee); trip-distance tercile (short trips expected to respond more, as the TR Part A paper found for ride-hailing); airports excluded/included.
- Confounders to discuss, not solve: citywide trends absorbed by week FE; weather controlled; any 2025 taxi fare rule changes — **Claude Code to search TLC industry notices for 2025 and list them in `DECISIONS.md`**; spillover (riders switching from private cars to taxis) biases β toward zero — say so.
- Forecast counterfactual: aggregate CBD daily pickups; frozen-LGBM q50 forecast as counterfactual; implied effect = mean (actual − forecast) / forecast over post-period by month; plot against the event-study path. Agreement or disagreement is reported as found.

**Outputs:** `results/did_static.json`, `results/event_study.csv`, `results/heterogeneity.csv`, `results/placebo.json`, `reports/figures/F4_event_study.png` (the core figure: monthly coefficients ± 95% CI, zero line, policy line, nothing else), `F4b_effect_map.png` (zone-level post/pre log change relative to control mean; diverging palette centered at 0; CBD boundary), `F4c_heterogeneity.png` (small multiples), `F4d_counterfactual_vs_did.png`.

**DoD:** pre-trend test and placebo saved; all four figures render; report text states effect size with CI and the design in one sentence.

⏸ **CHECKPOINT 4:** show F4 and the heterogeneity table. Stanley decides what goes into the summary wording; nothing is written until he approves.

---

### Phase 5 — How the system should adapt

**Goal:** compare adaptation strategies on 2025-02 → 2026-09 with the same metrics as Phase 2.

Strategies
- S0 frozen (Phase 3)
- S1 monthly retrain, sliding 24 m window
- S2 monthly retrain + feature `post_policy × is_cbd` (and `post_policy` alone)
- S3 frozen + level correction: multiply CBD forecasts by exp(β̂) from Phase 4 (uses the causal estimate directly)
- S4 Chronos-2 zero-shot (adapts through its context window) — if it stayed in Phase 2
- S5 (optional) frozen + online bias correction (exponentially weighted mean of last 14 days' residuals per zone)

Report: WAPE and coverage per strategy per zone group per quarter; the error-recovery curve (rolling 4-week WAPE, CBD only) for S0–S3 on the Phase-3 axes.

**Outputs:** `results/adaptation.csv`, `reports/figures/F5_adaptation.png`.

**DoD:** table and figure produced; one paragraph in the report says which strategy to recommend and why (cost of retraining vs gain).

---

### Phase 6 (optional, after Phase 5 is complete) — High-volume FHV comparison

Only if disk and time allow. HVFHV files are ~10× larger. Restrict to **2024-01 → 2026-09**. Columns: `pickup_datetime, PULocationID, DOLocationID, hvfhs_license_num (HV0003 Uber, HV0005 Lyft), shared_request_flag, shared_match_flag, trip_miles, base_passenger_fare, cbd_congestion_fee`. Repeat Phase 4 for FHV with platform as a split (Lyft's January 2025 rider credit is a known confounder: report January separately). The one new figure: taxi ($0.75) vs FHV ($1.50) event-study paths on one axis. Do **not** add forecasting for FHV.

---

### Phase 7 — Figures, README, report

Figure system (`viz/style.py`)
- One `.mplstyle`: white background, no top/right spines, light grey grid, 9–11 pt labels, consistent figure sizes (single 7×4.2 in, map 7×7 in, small multiples 10×6 in), PNG at 200 dpi + SVG.
- Semantic palette, fixed for the whole project: `CBD = #B23A48` (accent), `non-CBD = #8A8F98` (grey), `model = #1F5F8B`, `baseline = #B0B4BA`, `pre = lighter tint of the series colour`, `post = full colour`, diverging map = blue–white–red centred at 0, sequential map = single-hue blues on log scale.
- `policy_line(ax)` helper: same dashed vertical line and label "Congestion pricing starts 2025-01-05" on every time axis.
- Direct labels at line ends instead of legends where possible; title = the finding ("CBD forecast error doubled after congestion pricing; non-CBD unchanged" — but only once the data say so).
- One interactive figure: Plotly version of F4b (hover: zone name, pre mean, post mean, change, CI) saved as `reports/figures/F4b_effect_map.html`.

Figure list (final names): `F1_demand_map`, `F1b_citywide_weekly`, `F2_model_comparison`, `F2b_fan_chart`, `F3_error_over_time`, `F4_event_study`, `F4b_effect_map(.png/.html)`, `F4c_heterogeneity`, `F4d_counterfactual_vs_did`, `F5_adaptation`, (`F6_taxi_vs_fhv` if Phase 6).

`reports/analysis.md` (~2,000 words): Question → Data → Forecast baseline → The break → Effect size and checks → Adaptation → Limitations → What I would do next. Every number links to a `results/` file. Cite the three prior studies and state plainly what overlaps and what is new.

README: 150-word summary, the five figures inline, `make` targets, hardware used and runtime, data licence note (TLC data is public), limitations (yellow taxi only unless Phase 6; weather city-wide; actual weather used as if known in advance; no supply-side data).

**DoD:** `make all` reproduces every figure from `results/`; README renders on GitHub; CI (`.github/workflows/ci.yml`) runs `ruff`, `pytest`, and `make smoke` on the sample month.

---

## 6. Known risks and the agreed response

| Risk | Response |
|---|---|
| Full yellow download too large for the machine | Download in full regardless (quality rule §0.8); free disk or use an external drive; report at Checkpoint 0 |
| LightGBM on ~100 zones × 4 years × 24 h ≈ 3.5M rows × ~25 features | Fine on 16 GB RAM; if not, report at a checkpoint before any subsampling |
| Chronos runtime | Always on Colab GPU (T4/L4), daily origins; never CPU |
| dbt-duckdb installation trouble on Windows | Fix it (use a venv or WSL); do not replace dbt |
| Event study shows significant pre-trends | Report it; switch the primary control group; do not hide it |
| DiD and forecast counterfactual disagree | Report both; explain plausible reasons (spillover, model drift unrelated to policy) |
| Effect is small or zero for taxis | Still a finding (the $0.75 fee is small relative to fares); the forecasting storyline stands on its own |

---

## 7. Checkpoints and the review loop

Human checkpoints (always stop and wait for Stanley):
0. After `make smoke`: machine resources and download plan.
4. After Phase 4: F4 and heterogeneity → summary wording decisions.

Reviewer-gated (the `phase-reviewer` subagent decides; Stanley gets a summary only): Phases 1, 2, 3, 5, 7. The loop, the verdicts and the amendment bounds are defined in `CLAUDE.md` and `.claude/agents/phase-reviewer.md`. Any `BLOCKED` or `ESCALATE` stops the run.

`make verify PHASE=N` must exist from Phase 0 and check: `ruff`, `pytest`, `dbt test` (phases ≥ 1), and that every result file listed under "Outputs" for phase N exists and is non-empty. The reviewer runs it first.

Setup for the loop (Phase 0 task): copy `CLAUDE.md` to the repo root and `phase-reviewer.md` to `.claude/agents/phase-reviewer.md`; create `reviews/` and `DECISIONS.md`.

**Kickoff prompt for Claude Code (Stanley pastes this once):**
> Read PLAN.md and CLAUDE.md in this folder completely. Create the repository `nyc-taxi-policy-shock` as specified, move CLAUDE.md to its root and phase-reviewer.md to `.claude/agents/`. Then execute Phase 0. Follow the phase protocol in CLAUDE.md for every phase: build, `make verify`, phase-reviewer, act on the verdict. Stop only at Checkpoint 0, Checkpoint 4, ESCALATE or BLOCKED. Report numbers only with their results/ file names.

---

## Amendments

- [2026-11-07] [phase 1] **Directed by Stanley at Checkpoint 0 (not a reviewer amendment).** The five Phase-1 follow-ups in `reviews/phase_0.md` ("Observations for Phase 1") are mandatory items of the Phase 1 Definition of Done, reviewed as such:
  1. Record the pickup-window boundary choice in `int_trips_valid` (PLAN writes a closed bracket; code uses half-open `pickup_ts < source_month + 1 month + 1 day`) in `DECISIONS.md`, consistent with the filter counts in `results/data_quality.json`.
  2. Overlapping weather chunks: keep exactly one source file per hour, or add a test proving overlapping rows are identical; no silent averaging of revised Open-Meteo values.
  3. `tests/test_grid.py` runs against the full warehouse `data/warehouse.duckdb`, includes at least one DST month (both a spring-forward and a fall-back day), and cannot be skipped inside `make verify PHASE>=1` (a skip counts as a failure there).
  4. Machine/disk sizes reported to Stanley state their unit explicitly (decimal GB vs GiB).
  5. `results/data_quality.json` counts the trips dropped by the grid join: edge stragglers outside the downloaded calendar span, and pickups stamped in the non-existent spring-forward 02:00 hour.
- [2026-11-07] [all phases ≥ 1] **Directed by Stanley at Checkpoint 0.** Reviews run as the registered `phase-reviewer` subagent (`.claude/agents/phase-reviewer.md`) with a fresh context, not as a general-purpose agent handed the reviewer text.
- [2026-11-07] [phase 1] **Checkpoint 0 decisions (Stanley).** Download all 93 yellow months (2019-01 → 2026-09) in full to `data/raw/`; WSL memory raised to 12 GB before the download starts; HVFHV data not downloaded until Phase 6 is approved.

- [2026-11-07] [phases 1–7] **Checkpoint 1 decisions (Stanley; directed, not a reviewer amendment).**
  1. Panel weeks start on Sunday (approved); filter exemptions for Flex Fare and Helix records (approved); CBD validation accepted; the 103 forecast-modeled zones (`results/zone_summary.csv`) approved.
  2. (a) Before Phase 4: weekly trip counts by VendorID 2023-01 → 2026-09, CBD vs non-CBD, stating whether Helix volume replaced other vendors' volume or added to it → `results/vendor_series.csv` + a small figure. (b) Before Phase 4: share of Flex Fare and Helix trips by treatment group over time. **Phase 4 robustness result:** the static DiD re-estimated using only vendors present throughout the window, reported next to the main estimate and the original-filter (PLAN-literal) estimate.
  3. Trip-level CBD fee check over all zones: share of trips with `cbd_congestion_fee > 0` for (i) pickup and dropoff both outside the CBD (60th St rule) and (ii) pickup or dropoff inside it, monthly 2025-02 → 2026-09 → `results/cbd_validation_trips.json`.
  4. Phase 2 reports the 103 modeled zones' share of total 2024 pickups.
  5. README and `reports/analysis.md` note that yellow-taxi volume in 2024 was 48% of 2019 and that this motivates `model_start = 2022-01-01`.
  6. Phase 7 cleanup item: evaluate making staging models views over Parquet instead of tables, and rebuild the warehouse into a fresh file to reclaim space.
  7. Order: items 2a, 3, 4 first, then Phase 2; stop when the Chronos script is ready and give Stanley the exact Colab steps.

## Amendments (human-approved)

**Amendment 1 — 2026-11-07 — product-DS additions (Stanley approved; mandatory for the Phase 4 and Phase 7 Definition of Done).** Motivation: experimentation and metric design are central to product and analytics data science. These additions reuse existing data; the storyline is unchanged.

- **A1. Metric framework (Phase 4).** Report results as: primary metric = CBD pickups (log1p and levels); guardrail metrics = non-CBD pickups (spillover), mean fare per trip (price effect), weekly congestion-fee revenue computed from `cbd_congestion_fee`; secondary = heterogeneity by hour band, weekday/weekend, distance tercile. Save `results/metric_framework.csv`; present it as one table in the report. The framework includes the pickup-in-CBD vs dropoff-only-in-CBD split (pass-through trips; Stanley 2026-11-09, Checkpoint 1 item 3).
- **A2. Power analysis via permutation placebo (Phase 4).** Using pre-policy data only (2023-01 → 2025-01-04), draw 500 placebo assignments: a random fake policy date in the pre-period and a random set of 38 Manhattan zones as fake treatment. Estimate the static DiD each time. Report the placebo distribution, the share of |placebo| ≥ |β̂|, and the minimum detectable effect at 80% power / 5% size. Save `results/power_mde.json` and `reports/figures/F4e_placebo_distribution.png`. This is the primary placebo check; the single placebo-in-time test is kept as well.
- **A3. Implied elasticity and trade-off table (Phase 4).** Implied price elasticity = (% change in CBD trips from the main DiD) / (% change in trip price = $0.75 / pre-period mean fare of CBD trips). Quarterly trade-off table: fee revenue collected (sum of `cbd_congestion_fee`) vs estimated fare revenue lost (effect × counterfactual trips × mean fare), with assumptions stated. Save `results/elasticity_tradeoff.json`.
- **A4. Experiment-design section and executive summary (Phase 7).** `reports/analysis.md` gets (i) a section "Why this could not be an A/B test, and how it would be designed": non-randomizable geography, spillover, interference; candidate designs (time switchback, staggered rollout, geo-experiment with synthetic control); required sample size derived from the A2 MDE; design only, no new data. (ii) A one-page executive summary at the top: three sentences of findings with numbers and one recommendation. README states in one line that the panel and all heterogeneity cuts are SQL in dbt (window functions), not pandas.
- **A5. Vendor robustness (Phase 4; Checkpoint 1 item 2b).** Re-estimate the main DiD on vendors present throughout 2023-01 → 2026-09 and report it beside the main estimate and the original-filter estimate.

Dated human-approved changes:

- [2026-11-07] [phase 4] **Primary control = "donut" (Stanley).** The primary DiD control is the Manhattan non-CBD zones minus the six zones that straddle the 60th St line (43 Central Park, 140 Lenox Hill East, 141 Lenox Hill West, 142 Lincoln Square East, 143 Lincoln Square West, 237 Upper East Side South); Roosevelt Island (202) stays (its overlap with the line is a straight-line artefact, fee share 0.059344). The originally approved full Manhattan non-CBD control is reported as a robustness run; Brooklyn + Queens (excluding airports) remains a robustness run. Evidence: treatment assignment only — `results/cbd_validation_trips.json → manhattan_zones` (area south of the line, fee shares of trips with both ends outside the CBD); decided before any DiD, event-study or treatment-vs-control outcome comparison was computed. Config: `causal.control: manhattan_non_cbd_donut`, `causal.control_groups`, `causal.control_robustness`.
- [2026-11-07] [phase 4] Helix worst-case bound (−0.004 log points against the full control; `results/vendor_summary.json → detectability`) and the CMT + Curb vendor-restricted static DiD approved as planned; F1c kept.
- [2026-11-07] [phase 4] Pass-through trips: the dropoff-in-CBD heterogeneity cut stays; additionally report the pickup-in-CBD vs dropoff-only-in-CBD split inside the A1 metric framework ("A1" = Amendment 1 item A1, confirmed by Stanley 2026-11-09).
- [2026-11-07] [phase 7] Fee-recording variation by vendor (`results/cbd_validation_trips.json → by_vendor_month`) goes into the analysis limitations; no correction.
- [2026-11-08] [phase 2] **Calibration method detail (Stanley).** Primary calibration of forecast intervals = rolling split-conformal: for each forecast origin, calibrate on the trailing 12 weeks of residuals, per zone group and per quantile. The pre-specified 2023-residual split-conformal stays in the results table beside it (it under-covers in 2024 because 2024 errors are larger — a year-to-year shift, reported as found).
- [2026-11-08] [phase 2] **LightGBM runtime handling (Stanley).** If a refit exceeds ~3 minutes: early stopping on a held-out last-4-weeks slice of the training window, num_threads=10, float32 features, histogram bins ≤ 255; the origin set and the refit frequency are not reduced.
- [2026-11-09] [phases 2–3] **Chronos-2 2023 run (Stanley; calibration parity only).** A second Colab run with the same script covers origins 2023-10-01 → 2023-12-31 (both weather variants), so Chronos-2's rolling 12-week calibration can start on 2024-01-01 like the trained models'. The import merges both runs into the existing Chronos result files with one run record per run. Phase 3 does not wait for it; the Phase-2 Chronos calibration table is re-run when the 2023 files arrive.
- [2026-11-09] [phase 5] Chronos-2 zero-shot matching the tuned LightGBM before the shock (Phase 2) is a finding carried into Phase 5: does the zero-shot model, which adapts through its context window, adapt better after the shock?

**Amendment 2 — 2026-11-09 — second pre-specified outcome: trip speed and duration ("faster, not fewer") (Stanley approved; mandatory for the Phase 4 and Phase 7 DoD).**

Context: Phase 3 found no CBD-specific break in the demand forecaster (reviews/phase_3.md). This amendment is written **before any speed or duration analysis has been run**, so the speed outcome is a second pre-registered outcome, not a post-hoc search. Hypothesis and expected direction come from prior work: the NBER study (w33584) measured an ≈11% rise in CBD speeds from Google Maps data, largest in the afternoon. Our trip records allow an independent, trip-level measurement.

- **B1. Second primary outcome (Phase 4).** Alongside demand (pickups), analyse **trip duration** (dropoff − pickup, minutes) and **speed** (trip_distance / duration, mph) with the same identification: DiD static + monthly event study, zone/pair FE, week FE, SE clustered by zone, donut control, placebo and alternative-control robustness, A2-style permutation power analysis. Pre-specified direction: speed up / duration down in the CBD.
- **B2. Unit and groups for the speed outcome.** Trip-level definition, not pickup-zone: treated = trips with pickup **and** dropoff in the CBD; control = trips with pickup and dropoff both in Manhattan non-CBD (donut zones excluded); report separately trips entering the CBD, leaving it, and (if identifiable) passing through. Aggregate to zone-pair × week (or origin-zone × week) means; weight by trips. Also report an hourly-band split (overnight / AM peak / midday / PM peak / evening) because the prior literature predicts the largest effect in the afternoon.
- **B3. Composition control.** Mean speed moves with trip mix. Estimate within trip-distance terciles (fixed on 2024 quantiles) and with distance as a control; report both. Exclude from the speed analysis trips with duration < 1 min or missing (Helix rows with dropoff = pickup) and trips with distance = 0 (Flex Fare rows), using the Phase 1 flags; report the excluded share by month and group.
- **B4. Metric framework extension (A1).** Add duration, speed and fare per minute as outcome rows; primary metrics are now demand (quantity) and speed (service quality); guardrails unchanged.
- **B5. Trade-off table extension (A3).** Replace the lost-fare calculation with the rider trade-off: minutes saved per CBD trip (from B1) × a range of values of time ($20, $30, $40/h) vs the $0.75 charge; report the break-even value of time. Keep fee revenue collected. Compare with the NBER break-even figures and state the differences in data and assumptions.
- **B6. Storyline and title (Phase 7).** Working title: *Faster, Not Fewer: What Congestion Pricing Did to NYC Taxi Demand and Speed*. Executive summary leads with the speed effect, then the demand null with its MDE, then the forecasting result (the forecaster held because demand held), then the adaptation result under ordinary drift. Final wording is settled at Checkpoint 4 after the numbers exist.
- **B7. Order of work in Phase 4.** (1) Speed/duration DiD and event study; (2) demand DiD with MDE; (3) demand heterogeneity where an effect is most plausible (distance and fare terciles, dropoff-in-CBD from outside, within-CBD, hour bands); (4) A1/A3/A5; (5) F4 figures. Checkpoint 4 presents both outcomes together.
- **B8. Phase 6 (FHV) remains conditional**, decided at Checkpoint 4 with the Phase 4 results in hand.

**Amendment 3 — 2026-11-09 — re-plan after Checkpoint 4 (Stanley approved). Supersedes Amendment 2's title and storyline; keeps its pre-registered outcomes.**

Evaluation that led here (reviews/phase_4.md, Checkpoint 4): (i) the pre-registered equal-weight log1p demand DiD (−0.43) is an artifact of small uptown control zones whose yellow pickups grew several-fold 2023→2025; the pre-volume-weighted estimate is −5% [−14%, +3%], the placebo-in-time is significant and pre-trends fail — the design captures differential trends, not the policy. (ii) The speed effect (+1.9%) is seasonal and below MDE **with the Manhattan non-CBD control**, which NBER w33584 shows received spillover speed gains itself (+1–6%); that control is contaminated toward zero. (iii) External evidence: Uber dispatched ≈20% of yellow trips by March 2025 (TLC hearing), and from the June 2026 files TLC publishes a `request_source` field (HV0003 Uber, HV0005 Lyft) on yellow trips. The yellow market was being reshaped by app dispatch while congestion pricing began.

Storyline (working): *A small toll in a changing market — measuring congestion pricing's effect on NYC taxis while app dispatch reshaped demand.* Final title at Checkpoint 6.

Expected directions are written here **before** any of C1, C3, C4, C5, C6 is run.

- **C1. Mechanism check with `request_source` (new; Phase 4b).** For yellow files 2026-06 → 2026-09, compute per pickup zone the share of trips with `request_source` in {HV0003, HV0005} (confirm the field name and codes against the TLC data dictionary; report what the files actually contain). Join to `results/zone_growth.csv`. Outputs: `results/app_dispatch_share.csv`, correlation and a scatter of 2023→2025 growth vs app share, map `F4g_app_dispatch_map.png`. **Expected:** the fast-growing uptown control zones have a markedly higher app-dispatch share than CBD zones. If the field is absent from our files, record it and download the affected months again.
- **C2. Demand wording (Phase 4, replaces Checkpoint 4 item 1).** Primary = pre-volume-weighted DiD, stated as "no detectable change; 95% CI [−14%, +3%]; permutation MDE for the weighted spec = X%". Never "no effect". Equal-weight estimate reported as the pre-registered spec with the artifact explanation. Add zone-specific linear trends as a labelled, not-pre-registered robustness. Control group unchanged.
- **C3. Synthetic control for CBD demand (new; Phase 4b).** Outcome: weekly total CBD pickups (log). Donor pool: non-CBD zones with 2024 mean ≥ 1,000 pickups/week, donut zones excluded. Pre-period 2023-01 → 2024-12-28; post to 2026-09. Report: pre-period RMSPE, donor weights, post/pre RMSPE ratio, in-space placebos over all donors (rank of the CBD), and a 2024-01 in-time placebo. Library: `pysyncon` or an equivalent; record the choice. **Expected:** small negative or zero post-period gap; if pre-fit is poor (RMSPE ratio not distinguishable from donors), report that the method cannot resolve the question. `results/synth_control.json`, `F4h_synth_control.png`.
- **C4. Speed re-estimation with an uncontaminated control (Phase 4, extends B1).** Treated = within-CBD trips; **control = trips with both ends inside Brooklyn or Queens, airports excluded** (NBER: minimal spillover). Keep pair FE, week FE, two-way clustering, distance terciles, the treated × calendar-month seasonality control, hour bands, and the permutation MDE. Keep the Manhattan non-CBD result beside it as the pre-registered comparison. **Expected:** within-CBD speed +3% to +8%, largest in the PM band and in 2025-H1. `results/speed_did_outer.json`, update F4f.
- **C5. Three shocks, one monitor (new; extends Phase 3).** Run the Phase 3 frozen-model procedure and both monitors for three events, each with training on the 12 months before the event and monitoring for 12 months after: COVID 2020-03-01 (train 2019-03 → 2020-02), the 23% metered-fare increase 2022-12-19 (train 2021-12 → 2022-11; confirm the date from TLC), congestion pricing 2025-01-05 (existing). Report detection delay, direction and the post-event level change for each. **Expected:** COVID detected within days; the fare increase within weeks with a measurable demand drop; congestion pricing not detected. `results/shock_comparison.json`, `F3b_three_shocks.png`.
- **C6. Phase 6 (FHV) — GO, as approved at Checkpoint 4.** Demand only; platform split; Lyft January 2025 separate; shared flags; weighted and equal-weight; pre-trend test first and stop if it rejects. **Expected:** Uber −3% to −6%; Lyft confounded by the credit; shared trips larger decline.
- **C7. Checkpoint 6 (new human checkpoint).** After C1–C6: present all results together; decide the final title, the executive summary and the headline numbers. Phase 5 and Phase 7 follow.
- **C8. Methods note (Phase 7).** `reports/analysis.md` gets a section "How a textbook DiD produced a 42% effect that was not there, and how it was caught", written so it can stand alone.

Order of work: C1 → C4 → C5 → C2 finalisation → C3 → C6 → Checkpoint 6 → Phase 5 → Phase 7. Not done: changing the demand control group (other than C3), new outcome variables, a full causal study of the 2022 fare increase.

**Amendment 4 — 2026-11-12 — re-centre the project on channel incrementality (app dispatch of yellow cabs); DS stack additions; HVFHV disk decision (Stanley approved; direction is tentative until the D0 gate passes). Supersedes Amendment 3's working title; all Amendment 3 results stay and are re-used.**

Why. After C1–C5 and the Phase 4 ruling, the project's policy outcomes are null or unidentified, so its summary cannot state a measurable outcome. The largest measured change in our own data is not congestion pricing but app dispatch. From `results/record_format_shares.csv` (advisor's monthly aggregation; the Builder reproduces and saves it in D1): Flex Fare share of yellow pickups, CBD 2.3% (2023-01) → 10.3% (2024-04) → 17.8% (2025-01) → 29.6% (2026-01); `other` zone group 8.5% → 31.8% → 59.9% → 65.1%; `other` monthly pickups 54,622 (2023-01) → 261,242 (2026-01) while CBD pickups went 1,963,754 → 1,815,527. Implied: in the CBD app trips rose while non-Flex trips fell by about a third; outside Manhattan both rose. External facts: Uber began auto-dispatching yellow cabs to UberX requests in August 2023 (amNY 2023-08-29); Lyft announced NYC yellow-cab dispatch through Curb on 2026-07-16, and `request_source` = HV0005 appears from 2026-08 (5.4%, then 10.5% in 2026-09) while HV0003 fell from 24.2% to 18.3% (`results/app_dispatch_summary.json`).

**Working question.** *When ride-hail apps began dispatching NYC yellow cabs, did the taxi business grow, or did trips move between channels?* Incrementality = the share of a channel's trips that would not have happened otherwise; its opposite is cannibalisation. Working title: *New Channel, New Trips? Measuring the Incrementality of App Dispatch for NYC Yellow Cabs.* Report chapters: (1) the market shift; (2) incrementality; (3) case study — evaluating congestion pricing in a shifting market (Phases 3–4, C1–C6); (4) forecasting through the shift (Phases 2, 3, C5, Phase 5). Final title and repository name at Checkpoint 6.

Expected directions below are written **before** any of D0–D6 is run.

- **D0. Validation gate for the channel label (first; about 2 hours).** Is Flex Fare (`payment_type = 0`) a usable label for app-dispatched trips before `request_source` exists? On 2026-06 → 2026-09 trips compute, by month and zone group: P(Flex | request_source ∈ {HV0003, HV0005}), P(app | Flex), and the same including the other populated codes (`A`, `EH0004`, `EH0010`, `CC` — establish what each means from the TLC data dictionary / e-hail licence list; report what cannot be established). Also by VendorID. **Gate:** if both rates are ≥ 0.85 overall and in every zone group with ≥ 1% of trips, use Flex as the app label for 2023-01 → 2026-05 and `request_source` from 2026-06; otherwise restrict channel analyses to 2026-06+ and show the earlier Flex series as indicative only. Also date the step changes in the Flex share (e.g. between 2024-01 and 2024-04) to the week and list candidate causes from TLC notices and news as hypotheses. **Expected:** high agreement (CBD 2026-06: Flex 26% vs app 24%). `results/channel_label_validation.json`. Report the gate result in one line and continue; stop only if it fails.
- **D1. Decomposition (descriptive).** Weekly and monthly pickups by channel (app vs street-hail) × zone × zone group, 2023-01 → 2026-09, as dbt models (`fct_weekly_zone_channel`). Growth accounting: change in pickups 2023 → 2025 and 2023 → 2026 split into app and street-hail contributions by zone group. **Expected:** outside Manhattan growth is mostly app; in the CBD app growth is largely offset by a street-hail decline. `results/channel_decomposition.csv`; F6a (stacked areas by channel, CBD vs outer boroughs, one axis style), F6b (map of app share over time, small multiples).
- **D2. Incrementality by geography (main estimate).** Zone × week panel. Estimand θ = change in total pickups per additional app pickup (1 = fully incremental, 0 = fully displacing); equivalently 1 + coefficient of street-hail on app. Estimator: partially linear double machine learning (`DoubleML` or `EconML`; record the choice) with LightGBM nuisance models, cross-fitting on time-blocked folds, clustering by zone; controls: weather, calendar, zone fixed effects or zone trends, lagged total pickups, citywide week effects. Report θ with 95% CI for CBD, Manhattan non-CBD, outer boroughs, airports. Robustness: first differences; TWFE; a lead of app pickups as placebo (should be ≈ 0); sensitivity to the D0 label. Supply view: from TLC's monthly aggregate report (`data_reports_monthly.csv`; confirm the URL and fields) trips per active medallion-day and hours per vehicle-day 2022 → 2026, because medallion supply is capped and an app trip can displace a street hail on the same cab. State plainly that this is observational. **Expected:** θ near 1 outside Manhattan; θ between 0 and 0.5 in the CBD. `results/incrementality_dml.json`, F6c.
- **D3. Lyft's entry (dated event, direct attribution).** First establish: the first date with HV0005 trips; whether HV0005 occurs only with the Curb vendor (VendorID = 2), as the Curb-only integration implies. **Primary design if that holds:** vendor-level difference-in-differences on zone × day pickups, 2026-06-01 → latest month — treated = Curb-equipped cabs (gain Lyft access), control = CMT/Arro-equipped cabs — with zone × vendor and zone × day fixed effects, clustering by zone; outcomes: total pickups, Uber-dispatched, street-hail; pre-trend check on June–July; prior-year same-week level as a covariate. Report the implied incrementality of Lyft trips = Δ total Curb pickups ÷ Lyft pickups, and the displacement of Uber-dispatched trips. If HV0005 is not Curb-only, fall back to zone exposure = pre-launch Curb share and say so. Label the result **preliminary** (two post-launch months); add `make lyft-refresh` to re-run when TLC publishes later months. **Expected:** Lyft trips are partly incremental (0.3–0.7) and displace some Uber-dispatched trips. `results/lyft_entry.json`, F6d.
- **D4. Cross-platform displacement (exploratory; uses HVFHV aggregates).** Zone × week 2023-01 → 2026-09: Uber FHV trips vs Uber-dispatched yellow trips; yellow app trips as a share of each platform's total (yellow + FHV) by zone group; same DML form as D2. **Expected:** small negative association; mainly descriptive. `results/cross_platform.json`.
- **D5. Congestion pricing by channel (exploratory, gated).** Re-run the Phase 4 weighted DiD separately for street-hail and app pickups. Gate: only interpret a channel whose pre-trend test does not reject. **Expected:** uncertain; recorded as exploratory. `results/did_by_channel.json`.
- **D6. Phase 5 re-scope: forecasting through the channel shift.** Strategies: S0 frozen; S1 monthly retrain; S4 Chronos-2; S6 channel-aware (forecast app and street-hail separately and sum, or lagged app share as a feature). No S3. **Expected:** S6 removes most of the post-2025 bias. Same metrics as Phase 2.
- **C6 stays** (FHV congestion-pricing estimate, platform split, pre-trend test first).

**Stack additions (price is not a criterion).**
- **E1. Double machine learning** — used in D2 and D4 (above).
- **E2. Tableau dashboard, built by Stanley.** The Builder provides `make tableau-extract` (tidy CSV/Parquet extracts from the marts: channel × zone × week, incrementality estimates, Lyft entry series, zone geometry) and a one-page specification `reports/dashboard_spec.md` with four views: app share over time by area; zone map of app share and growth; incrementality by area with intervals; Lyft entry before/after. Stanley builds and publishes it on Tableau Public himself; the README links it. The Builder does not fabricate screenshots.
- **E3. dbt on Snowflake.** Add a `snowflake` target beside `duckdb` in `dbt/profiles.yml` (credentials from environment variables only; never committed). Load cleaned yellow trips 2023-01 → 2026-09 and the HVFHV aggregates to Snowflake (internal stage, `COPY INTO`), run the intermediate → marts → channel models and all dbt tests there; keep SQL portable with dbt macros where dialects differ; record row counts and test results per target in `results/dbt_targets.json`. CI stays on DuckDB. Runs after Checkpoint 6, when Stanley supplies the account. BigQuery is not added.
- Not added: Spark, Airflow, Kubernetes, LLM features, deep-learning forecasters, R.

**HVFHV disk decision (human-approved exception to §0.8).** Do not keep raw HVFHV files. Stream month by month: download → aggregate with DuckDB → verify row counts → delete the raw file. Range **2023-01 → 2026-09** (extended for D4). Keep `data/raw/hvfhv_manifest.csv` (URL, bytes, sha256, rows, download date) so any month can be re-fetched. Design the aggregates once so no re-download is needed: (i) pickup zone × pickup hour × platform (`hvfhs_license_num`) × `shared_request_flag` × `shared_match_flag` × trip type (within CBD / into / out of / neither, by the 60th St rule) × distance tercile: trips, sum of miles, seconds, base fare, driver pay, count with `cbd_congestion_fee` > 0; (ii) pickup zone × dropoff zone × week × platform: trips. Peak extra disk ≈ one month's file. Before starting: report what consumed the 12 GB lost this session (`du` on `data/`, the warehouse and its temp directory, `~/.cache`, uv cache, logs), run `fstrim`, and delete nothing that is not a regenerable cache without listing it first. Stop if free space on C: falls below 15 GB.

**Order of work.** Disk report → D0 (gate) → D1 → HVFHV streaming aggregates → C6 → D2 → D3 → D4 → D5 → phase-reviewer on Phase 4b/6 → **Checkpoint 6** (all results together; Stanley decides title, executive summary, headline numbers) → Phase 5 (D6) → E3 → E2 extract and spec → Phase 7. Commit and push after each item.

**Amendment 4a — 2026-11-12 — decisions after the D0 gate (Stanley approved). Written after D0's validation data and before any D1–D6 outcome was computed.**

- **Channel definition (D0 ruling, option c).** "App channel" = any e-hail app, not only Uber/Lyft. Label: Flex Fare before 2026-06; `request_source` not NULL from 2026-06 (D0: the two agree at 0.9997–1.000, airports 0.953, so the gate passes everywhere under this definition). Reason: the business question is app dispatch vs street hail, and Curb's and Arro's own apps are app dispatch; the Uber/Lyft-only reading is an 88% label. Platform-specific results (Uber, Lyft, Curb app, Arro; codes A and CC reported as undetermined) exist only from 2026-06. D2's estimand is the incrementality of the app channel as a whole. Airports: report, but draw no app-channel conclusion (Flex 0.38% of pickups).
- **D3 timing.** Primary: clean windows — pre-period ends 2026-07-08, post-period starts 2026-08-10, and 2026-07-09 → 2026-08-09 is excluded, because Curb's code-A surge suggests (hypothesis) that Lyft trips were coded A before HV0005 existed. Outcomes that need only VendorID and the Flex flag (total, app, street-hail by vendor) use a long pre-period from 2025-06 for pre-trends and a prior-year seasonal comparison; Uber-specific displacement uses 2026-06 onward. Secondary: treatment from 2026-07-09 with Lyft trips = HV0005 + Curb code-A above its 2026-07-01 → 07-08 baseline, labelled as resting on the hypothesis. Scope: CBD and Manhattan non-CBD only (the CMT break below contaminates the control group in the outer boroughs; airports have no app channel).
- **CMT outer-borough block.** First diagnose, then apply the rule. Diagnose: weekly outer-borough pickups by every vendor around 2026-05-31 (did another vendor gain what CMT lost, or did the total fall?); the block's trip characteristics before the break (zones, hours, distance, fare, payment type, passenger count, rate code) against other outer-borough street hails. Rule: keep the block as its own series; D1 shows outer-borough results with and without it and restates Amendment 4's motivating numbers both ways; D2 primary excludes the block for the whole window, with a sensitivity run that includes it and ends at 2026-05-24. Add a test that flags any vendor × zone-group series dropping by more than half between consecutive weeks.
- **D5b. Did congestion pricing move trips into the app channel? (new, pre-specified).** D0 dated a +10.9 pp step in the Flex share to the week of 2025-01-19, two weeks after the policy began; the fee is $0.75 per taxi trip and $1.50 per high-volume FHV trip. Test: weekly app share of yellow pickups by trip type (within / into / out of the CBD vs neither), 2024-07 → 2025-06, as an event study around 2025-01-05, with the same split for the count of app and street-hail trips; from the HVFHV aggregates, the matching change in Uber/Lyft FHV trips touching the CBD. **Expected:** if the fee differential is the cause, the step is larger for CBD-touching trips than for trips touching neither end; if the step is the same across trip types, it is not attributable to the fee differential. `results/app_share_policy_step.json`, F6e.
- **Disk.** Proceed with HVFHV streaming under the 15 GB stop rule. No compaction of the WSL disk image now (it needs a WSL shutdown).

**Amendment 5 — 2026-11-13 — Checkpoint 6 decisions (Stanley approved). Fixes the storyline; no further re-centring of the project.**

- **Storyline (final).** The headline is the measured market shift and where the growth came from; causal questions are presented as tested under pre-registered gates and mostly not identified. No sentence in the README, report or figures may state that app dispatch *caused* growth, or that congestion pricing had or had no effect.
  1. *The shift* (D0, D1, C1, D4, supply view): app dispatch rose from 2.3% to 29.6% of CBD yellow pickups (2023-01 → 2026-01); mean weekly CBD pickups 2023 → 2025 +99,063 (+23.7%) = app +104,958, street hail −5,896; outer boroughs without the contracted block 8,277 → 51,803, almost all app; active cabs per day 7,036 → 8,722 with trips per cab-day flat (14.85 → 15.02); zone growth vs app share r = 0.92; yellow app trips 0.75% → 10.86% of the CBD app market. Every number is quoted from its results file.
  2. *What the trip records cannot identify, and how we know* (Phase 4, C2–C6, D2, D3, D5, D5b): the equal-weight DiD's −0.43 artefact and its diagnosis; designs stopped at their gates; D2 reported as a range across estimators with the lead placebo; D3 preliminary.
  3. *Forecasting through the shift* (Phases 2, 3, C5, Phase 5).
- **Working title:** *Where the Growth Came From: App Dispatch and NYC Yellow Cabs, 2023–2026.* Repository rename is a Phase 7 item for Stanley.
- **Accounting ratio (add to D1, descriptive only).** Net change in total pickups per app pickup added, by area and period (CBD 2023 → 2025: 99,063 / 104,958; Jan–Sep 2023 → 2026: 65,204 / 113,506), saved in `results/channel_decomposition.csv` and named "accounting net ratio". It must be labelled as arithmetic on observed changes, not an incrementality estimate, wherever it appears.
- **D2 wording.** "Estimates of the share of app trips that are additional range from 0.52 to 2.62 across estimators in the CBD; the primary DML gives 0.90 [0.74, 1.06]; the estimators disagree beyond their intervals and one lead placebo fails, so incrementality is not identified from these data."
- **D3.** No change of primary after seeing results. Report the pre-registered levels specification with the reason it is not credible, and the log specification as a labelled alternative; both under "preliminary, not identified". Keep `make lyft-refresh`.
- **Formal status.** Phase 3 and Phase 4 are closed: the reviewer's ESCALATE verdicts are resolved by Stanley's rulings (Phase 3: no CBD-specific break, reported as found; Phase 4: inconclusive / not identified, reported as found). Append a dated closing note to `reviews/phase_3.md` and `reviews/phase_4.md`; do not re-run those reviews.
- **Experiment-design section (A4) now has a concrete subject:** how a platform or the TLC could measure the incrementality of app dispatch with a designed experiment (switchback of dispatch eligibility by zone-hour; staggered rollout by vendor), with the sample size implied by the observed variance.
- **Executive summary (Phase 7):** four sentences — the shift; the supply fact; what is not identified and why; the forecasting result — and one recommendation: evaluations and forecasts of NYC taxi demand in 2023–2026 must model the dispatch channel.
- **Go-ahead:** Phase 5 (D6: S0, S1, S4, S6), then E2 (extract and dashboard specification), then Phase 7. E3 (dbt on Snowflake) starts when Stanley provides the account through environment variables.

**Amendment 6 — 2026-11-14 — Checkpoint 7 review (presentation only; takes effect when Stanley sends the merge message to the Builder).** The advisor's review of the Phase 7 draft is `reviews/checkpoint_7_advisor.md`; its sections A and B are part of the Phase 7 Definition of Done, section C is optional. It changes no analysis, no gate and no storyline. It changes three points of earlier amended text:

- **Executive summary (replaces the "four sentences" of Amendment 5).** Three findings (the shift, led by the citywide growth accounting; the supply fact; forecasting through the shift), then what was tested and could not be identified, then the one recommendation of Amendment 5. Sentences of 30 words or fewer.
- **Report structure.** A main text of about 1,800 words or fewer plus `reports/appendix.md`, in the order of item B1 of the review. No content is dropped.
- **D2 wording (replaces the sentence of Amendment 5).** "Estimates of the share of app trips that are additional range from 0.52 to 2.62 across estimators in the CBD; the primary DML gives 0.90 [0.74, 1.06]; the estimators disagree beyond their intervals and the lead placebo fails in Manhattan outside the CBD, so incrementality is not identified from these data."

New numbers introduced by the review (citywide accounting, the January 2025 step by area, bias by area, the CBD ride-market view, the weather check of the 2026 alarms) are descriptive, come from existing result files or the warehouse, and are saved under `results/` before they are quoted. Amendment 5's rule stands: no sentence may state that app dispatch caused growth, or that congestion pricing had or had no effect. The README section "How this project was built" is written by Stanley, not by the Builder.
