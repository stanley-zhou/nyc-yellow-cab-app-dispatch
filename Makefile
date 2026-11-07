# Orchestration (PLAN §3). Run `make setup` once, then any target below.
# Targets for later phases fail loudly until their phase implements them.
SHELL := /bin/bash
PY    := .venv/bin/python
PHASE ?= 0

.PHONY: help setup smoke data dbt forecast causal adapt figures report all verify lint test clean-smoke

help:
	@echo "setup | smoke | data | dbt | forecast | causal | adapt | figures | report | all | verify PHASE=N | lint | test"

setup:            ## Python 3.12 venv via uv (system Python 3.14 is not supported)
	uv python install 3.12
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[dev]"

smoke:            ## one-month end-to-end pipeline, timed (< 10 min)
	$(PY) scripts/00_smoke.py

data:             ## full raw download: every yellow month in config + lookups + weather
	$(PY) scripts/01_download.py --all
	$(PY) scripts/02_weather.py --all

dbt:              ## build + test the full warehouse
	$(PY) scripts/03_dbt.py build

forecast causal adapt figures report:
	@echo "make $@: not implemented yet (added in its phase, see PLAN.md §5)"; exit 1

all: data dbt forecast causal adapt figures report

verify:           ## make verify PHASE=N
	$(PY) scripts/verify.py --phase $(PHASE)

lint:
	.venv/bin/ruff check .

test:
	.venv/bin/pytest -q

clean-smoke:
	rm -f data/smoke.duckdb data/smoke.duckdb.wal
	rm -rf results/smoke reports/figures/smoke
