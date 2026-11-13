# Orchestration (PLAN §3). Run `make setup` once, then any target below.
# Targets for later phases fail loudly until their phase implements them.
SHELL := /bin/bash
PY    := .venv/bin/python
PHASE ?= 0

.PHONY: help setup smoke smoke-clean data dbt probes chronos-bundle chronos-import forecast shock causal hvfhv channel fhv lyft-refresh tableau-extract adapt figures report all verify lint test clean-smoke

help:
	@echo "setup | smoke | smoke-clean | data | dbt | probes | forecast | shock | causal | hvfhv | channel | fhv | lyft-refresh | adapt | figures | report | all | verify PHASE=N | lint | test"

setup:            ## Python 3.12 venv via uv (system Python 3.14 is not supported)
	uv python install 3.12
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[dev]"

smoke:            ## one-month end-to-end pipeline, timed (< 10 min)
	$(PY) scripts/00_smoke.py

smoke-clean:      ## smoke on a clean export of HEAD; writes results/smoke/smoke_run_clean_clone.json
	$(PY) scripts/clean_clone_smoke.py

data:             ## full raw download: every yellow month in config + lookups + weather
	$(PY) scripts/01_download.py --all
	$(PY) scripts/02_weather.py --all

dbt:              ## build + test the full warehouse, derive is_cbd, write Phase-1 results
	$(PY) -m taxi_shock.calendar
	$(PY) scripts/03_dbt.py build --exclude "dim_zones+"
	$(PY) scripts/03a_cbd_map.py
	$(PY) scripts/03_dbt.py build --select "dim_zones+"
	$(PY) scripts/03b_data_results.py
	$(PY) scripts/03c_checks.py

probes:           ## one-off evidence scripts behind DECISIONS.md entries
	$(PY) scripts/probe_duplicates.py
	$(PY) scripts/probe_negative_fares.py
	$(PY) scripts/probe_record_formats.py
	$(PY) scripts/probe_open_meteo_offset.py

chronos-bundle:   ## Phase 2: export a Chronos-2 input bundle for Colab (RUN=calib_2023 for the 2023 run)
	$(PY) scripts/05a_chronos_export.py $(if $(RUN),--run $(RUN))

chronos-import:   ## Phase 2: validate Chronos-2 outputs in results/ (RUN=calib_2023: merge its inbox first)
	$(PY) scripts/05b_chronos_import.py $(if $(RUN),--run $(RUN))

figures:          ## every figure whose phase is implemented, from results/ only
	$(PY) scripts/09_figures.py --all

forecast:         ## Phase 2: LGBM grid (2023), rolling-origin backtests (2023 + 2024), evaluation
	$(PY) scripts/04a_lgbm_tune.py
	$(PY) scripts/04_backtest.py --full
	$(PY) scripts/04b_evaluate.py

shock:            ## Phase 3: frozen models 2024-07 -> 2026-09, rolling errors, drift monitors
	$(PY) scripts/06_shock.py
	$(PY) scripts/06b_three_shocks.py

causal:           ## Phase 4: speed/duration DiD (B1-B3), demand DiD + MDE + heterogeneity, A1/A3/A5, counterfactual
	$(PY) scripts/07a_speed.py
	$(PY) scripts/07b_demand.py
	$(PY) scripts/07c_metrics.py
	$(PY) scripts/07d_pretrend_size.py
	$(PY) scripts/07e_app_dispatch.py
	$(PY) scripts/07f_synth_control.py

hvfhv:            ## Amendment 4: stream HVFHV months -> aggregates (raw files deleted; manifest kept)
	$(PY) scripts/11_hvfhv_stream.py

channel:          ## Amendment 4 / 4a: D0 label, CMT block, D1 decomposition, D2 DML, D3 Lyft, D5, D5b, D4
	$(PY) scripts/10a_channel_label.py
	$(PY) scripts/10b_cmt_block.py
	$(PY) scripts/10c_channel_decomposition.py
	$(PY) scripts/12_incrementality.py
	$(PY) scripts/13_lyft_entry.py
	$(PY) scripts/14_did_by_channel.py
	$(PY) scripts/15_app_share_step.py
	$(PY) scripts/17_cross_platform.py

fhv:              ## Phase 6 (C6): congestion pricing and HVFHV demand (needs `make hvfhv`)
	$(PY) scripts/16_fhv_did.py

lyft-refresh:     ## D3: re-run the Lyft entry estimate after extending data.yellow_months to new TLC months
	$(PY) scripts/01_download.py --all
	$(PY) scripts/03_dbt.py build --select "stg_yellow_trips+"
	$(PY) scripts/13_lyft_entry.py
	$(PY) scripts/09_figures.py --all

tableau-extract:  ## E2: tidy CSV / GeoJSON extracts for the Tableau Public dashboard (reports/tableau/)
	$(PY) scripts/18_tableau_extract.py

adapt:            ## Phase 5 (D6): S1 / S6 monthly refits (long, resumable per month), then evaluation
	$(PY) scripts/08_adapt.py --run s1
	$(PY) scripts/08_adapt.py --run s6
	$(PY) scripts/08_adapt.py --run s1e
	$(PY) scripts/08_adapt.py --evaluate

report:           ## Phase 7: runtimes (results/runtimes.json), Tableau extracts, dead-link check of README / analysis.md
	$(PY) scripts/20_runtimes.py
	$(PY) scripts/18_tableau_extract.py
	$(PY) scripts/21_check_links.py

all: data dbt forecast shock causal hvfhv channel fhv adapt figures report   ## hvfhv: a long re-stream unless the aggregates exist (verified months are skipped)

verify:           ## make verify PHASE=N
	$(PY) scripts/verify.py --phase $(PHASE)

lint:
	.venv/bin/ruff check .

test:
	.venv/bin/pytest -q

clean-smoke:
	rm -f data/smoke.duckdb data/smoke.duckdb.wal
	rm -rf results/smoke reports/figures/smoke
