# Orchestration (PLAN §3). Run `make setup` once, then any target below; `make help` lists them.
SHELL := /bin/bash
PY    := .venv/bin/python
PHASE ?= 0

.PHONY: help setup smoke smoke-clean data dbt snowflake probes chronos-bundle chronos-import forecast shock causal hvfhv channel fhv lyft-refresh tableau-extract adapt figures report all verify lint test clean-smoke

help:             ## list every target with a one-line description
	@awk 'BEGIN {FS = ":[^#]*## "} /^[a-z][a-z0-9-]*:[^#]*## / {printf "  %-16s %s\n", $$1, $$2}' $(firstword $(MAKEFILE_LIST))

setup:            ## Python 3.12 environment in .venv via uv, packages from requirements-dev.lock, the package itself editable
	uv python install 3.12
	uv venv --python 3.12 .venv
	uv pip sync --python $(PY) requirements-dev.lock
	uv pip install --python $(PY) --no-deps -e .

smoke:            ## one sample month through the whole pipeline (download, dbt, backtest, figure); fails if over the time limit in config
	$(PY) scripts/00_smoke.py

smoke-clean:      ## smoke run on a clean export of HEAD in a temporary directory; writes results/smoke/smoke_run_clean_clone.json
	$(PY) scripts/clean_clone_smoke.py

data:             ## full raw download: every yellow-taxi month in config, the zone lookup and shapefile, hourly weather (01, 02)
	$(PY) scripts/01_download.py --all
	$(PY) scripts/02_weather.py --all

dbt:              ## build and test the DuckDB warehouse around the CBD zone mapping (03, 03a), then the data-quality results and Checkpoint-1 checks (03b, 03c)
	$(PY) -m taxi_shock.calendar
	$(PY) scripts/03_dbt.py build --exclude "dim_zones+"
	$(PY) scripts/03a_cbd_map.py
	$(PY) scripts/03_dbt.py build --select "dim_zones+"
	$(PY) scripts/03b_data_results.py
	$(PY) scripts/03c_checks.py

probes:           ## one-off evidence scripts behind DECISIONS.md entries: duplicates, negative fares, record formats, weather time offset
	$(PY) scripts/probe_duplicates.py
	$(PY) scripts/probe_negative_fares.py
	$(PY) scripts/probe_record_formats.py
	$(PY) scripts/probe_open_meteo_offset.py

chronos-bundle:   ## export the Chronos-2 input bundle for Colab (05a); RUN=calib_2023 for the 2023 calibration run
	$(PY) scripts/05a_chronos_export.py $(if $(RUN),--run $(RUN))

chronos-import:   ## validate the Chronos-2 forecasts copied back from Colab (05b); RUN=calib_2023 merges that run first
	$(PY) scripts/05b_chronos_import.py $(if $(RUN),--run $(RUN))

figures:          ## report numbers and repository counts (23, results/presentation_numbers.json), then every figure from results/ (09)
	$(PY) scripts/23_presentation_numbers.py
	$(PY) scripts/09_figures.py --all

forecast:         ## LightGBM grid on 2023 (04a), rolling-origin backtests for 2023 and 2024 (04), conformal calibration and metrics (04b)
	$(PY) scripts/04a_lgbm_tune.py
	$(PY) scripts/04_backtest.py --full
	$(PY) scripts/04b_evaluate.py

shock:            ## frozen LightGBM day-ahead 2024-07 to 2026-09 with drift monitors (06), the same monitor for three shocks (06b), daily weather (06c)
	$(PY) scripts/06_shock.py
	$(PY) scripts/06b_three_shocks.py
	$(PY) scripts/06c_weather_daily.py

causal:           ## speed and demand difference-in-differences with placebos, detectable effect sizes, heterogeneity, counterfactual, app-dispatch share, synthetic control (07a-07f)
	$(PY) scripts/07a_speed.py
	$(PY) scripts/07b_demand.py
	$(PY) scripts/07c_metrics.py
	$(PY) scripts/07d_pretrend_size.py
	$(PY) scripts/07e_app_dispatch.py
	$(PY) scripts/07f_synth_control.py

hvfhv:            ## stream the high-volume FHV months: download, aggregate in DuckDB, verify, delete the raw file; manifest kept (11)
	$(PY) scripts/11_hvfhv_stream.py

channel:          ## app vs street-hail label check, contracted-trip block, growth decomposition, incrementality, Lyft entry, by-channel DiD, app-share steps, cross-platform view, experiment design (10a-19)
	$(PY) scripts/10a_channel_label.py
	$(PY) scripts/10b_cmt_block.py
	$(PY) scripts/10c_channel_decomposition.py
	$(PY) scripts/12_incrementality.py
	$(PY) scripts/13_lyft_entry.py
	$(PY) scripts/14_did_by_channel.py
	$(PY) scripts/15_app_share_step.py
	$(PY) scripts/17_cross_platform.py
	$(PY) scripts/19_experiment_design.py

fhv:              ## congestion pricing and high-volume FHV demand, pre-trend gate first (16; needs make hvfhv)
	$(PY) scripts/16_fhv_did.py

lyft-refresh:     ## re-download, rebuild and re-estimate the Lyft entry after later TLC months are added to the config (01, 03, 13, 09)
	$(PY) scripts/01_download.py --all
	$(PY) scripts/03_dbt.py build --select "stg_yellow_trips+"
	$(PY) scripts/13_lyft_entry.py
	$(PY) scripts/09_figures.py --all

tableau-extract:  ## CSV and GeoJSON extracts for the Tableau Public dashboard in reports/tableau/ (18)
	$(PY) scripts/18_tableau_extract.py

adapt:            ## adaptation strategies: monthly retrain (S1), channel-aware forecaster (S6) and S1 on an expanding window (S1e), resumable per month, then their evaluation (08)
	$(PY) scripts/08_adapt.py --run s1
	$(PY) scripts/08_adapt.py --run s6
	$(PY) scripts/08_adapt.py --run s1e
	$(PY) scripts/08_adapt.py --evaluate

snowflake:        ## load the cleaned trips to Snowflake (24), dbt build and tests there, DuckDB tests, per-target comparison (25); needs the Snowflake environment
	$(PY) scripts/24_snowflake_load.py
	$(PY) scripts/03_dbt.py build --target snowflake --target-path target/snowflake
	$(PY) scripts/03_dbt.py test --target-path target/duckdb
	$(PY) scripts/25_dbt_targets.py

report:           ## runtimes (20, results/runtimes.json), dashboard extracts (18), dead-link check of the documents (21)
	$(PY) scripts/20_runtimes.py
	$(PY) scripts/18_tableau_extract.py
	$(PY) scripts/21_check_links.py

all: data dbt forecast shock causal hvfhv channel fhv adapt figures report   ## every step in order: data, dbt, forecast, shock, causal, hvfhv, channel, fhv, adapt, figures, report (long; hvfhv skips months already verified)

verify:           ## make verify PHASE=N: ruff, pytest, dbt tests and presence of the phase's result files (config/phase_outputs.yaml)
	$(PY) scripts/verify.py --phase $(PHASE)

lint:             ## ruff over the repository
	.venv/bin/ruff check .

test:             ## pytest
	.venv/bin/pytest -q

clean-smoke:      ## delete the smoke warehouse and smoke outputs (regenerated by make smoke)
	rm -f data/smoke.duckdb data/smoke.duckdb.wal
	rm -rf results/smoke reports/figures/smoke
