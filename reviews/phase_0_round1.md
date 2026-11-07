# Phase 0 review — skeleton and smoke pipeline

Reviewer: phase-reviewer · Date: 2026-11-07 · Commit reviewed: `41e9a94 phase 0: skeleton, dbt-duckdb warehouse and one-month smoke pipeline`

## Verdict

**FIX** — every DoD item is MET and I reproduced the clean-clone smoke run myself. One results file was written by hand rather than by code, and there are smaller hygiene, decision-log and figure-palette defects. Each one is listed below.

## DoD table

| DoD item | Status | Evidence |
|---|---|---|
| `make smoke` passes on a clean clone in < 10 min | MET | I ran `git clone` into a scratch dir, then `make setup` (1.3 s with a warm uv cache) and `make smoke`, which exited 0. `results/smoke/smoke_run.json` in the clone: `total_seconds` 25.0, `limit_seconds` 600.0, `passed` true. `backtest_smoke.csv`, `forecasts_smoke.parquet` and the PNG came out byte-identical to the committed copies, so the run is deterministic. The committed evidence file `results/smoke/smoke_run_clean_clone.json` was not written by code (see Fix 1). |
| `ruff` clean | MET | `ruff check .` → `All checks passed!` |
| `pytest` green | MET | 27 passed, 0 skipped (`test_grid.py` ran against `data/smoke.duckdb`) |
| `DECISIONS.md` has its first entries | MET | 37 Phase-0 lines in the required format. Some rules are still missing (Fix 3). |
| Task 1: §3 layout and pinned deps, `[chronos]` extra | MET | Every §3 path exists. Later-phase modules are docstring-only stubs (DECISIONS records this). `pyproject.toml` pins every listed package with `==`. `uv pip list` matches the pins and `uv pip check` reports all compatible. `torch` and `chronos-forecasting` are only in `[chronos]`. |
| Task 2: download with resume, size check, retry, `--months`, lookups and shapefile | MET | `src/taxi_shock/download.py`. `tests/test_download.py::test_resume_after_truncated_transfer` and `::test_existing_complete_file_is_skipped` cover these paths. |
| Task 3: Open-Meteo, 9 variables, yearly chunks | MET (documented deviation) | The code requests GMT unixtime and converts to local time in `stg_weather`. I confirmed the Builder's claim myself: `timezone=America/New_York` for 2024-07-01 returns `utc_offset_seconds: -18000` and a first timestamp of 1719810000 (= 05:00 UTC = 01:00 EDT). The deviation is therefore correct. `assert_weather_covers_grid` passes. |
| Task 4: dbt wired to DuckDB via `read_parquet` sources | MET | `dbt/models/sources.yml` uses `external_location`. In the clone, `dbt build` gave PASS=19 (6 models + 13 tests). |
| Task 5: `make smoke` = download → dbt run+test → seasonal-naive backtest → placeholder figure | MET | `scripts/00_smoke.py` runs these stages in order. Output: 107,304 forecast rows (= 263 zones × 24 h × 17 origins), from `results/smoke/forecasts_smoke.parquet`. |
| §7: `make verify PHASE=N` exists | MET | `scripts/verify.py` and `config/phase_outputs.yaml` |
| §7: CLAUDE.md at the root, reviewer agent, `reviews/` | MET | `CLAUDE.md` is identical to the source copy. `.claude/agents/phase-reviewer.md` and `reviews/.gitkeep` exist. |

## Test output

- `ruff check .` → `All checks passed!` (rc 0)
- `pytest -q` → 27 passed. `tests/test_leakage.py` run alone in the clean clone → 4 passed.
- `dbt test` by hand from `dbt/` (default profile) → `ERROR=13`, `Catalog Error: Table with name stg_zones does not exist!`. This is expected in Phase 0: the default profile points at the full `data/warehouse.duckdb`, which is only built in Phase 1. The run creates an empty `data/warehouse.duckdb` and an untracked `dbt/.user.yml`. I deleted both afterwards; see Fix 4.
- `dbt test` by hand with `TAXI_SHOCK_WAREHOUSE=../data/smoke.duckdb` → `PASS=13 WARN=0 ERROR=0`.
- `make verify PHASE=0` → ruff PASS, pytest PASS, dbt_test PASS (13/13 on the smoke warehouse), outputs PASS (6/6). The same result in the clean clone.

## Number trace

| Number (where) | Source | OK? |
|---|---|---|
| Figure title "2024-10-15 to 2024-10-31" | `results/smoke/forecasts_smoke.parquet` `target_ts` min/max (2024-10-15 00:00 / 2024-10-31 23:00). Config `smoke.backtest_origins`. | yes |
| README: "Python 3.12", "3.14", "2025-01-05" | Environment facts / `config/project.yaml` `data.policy_date` | yes |
| Commit message | contains no numbers | n/a |
| `reports/analysis.md` | does not exist yet (Phase 7) | n/a |
| Checkpoint-0 facts: yellow 93/93 months, 5.45 GB, largest 0.116 GB; hvfhv 33/33, 16.33 GB | `results/download_plan_summary.json`. I recomputed these from `results/download_plan.csv` and they match. | yes |
| 12 CPUs, 8.23 GB RAM, C: 88.7 GB free | `results/machine_resources.json`. `df -h /mnt/c` shows 83G avail (GiB), which is consistent. | yes (but see Fix 5) |
| Clean-clone run: 18.5 s | `results/smoke/smoke_run_clean_clone.json`, which was written by hand. The value is plausible: my own run took 25.0 s. | provenance defect (Fix 1) |

## Method sanity

- **Grid completeness and DST.** I ran the `int_hour_grid` SQL by hand. 2024-03 gives 743 hours, with 23 on 03-10. 2024-11 gives 720 hours, with 24 on 11-03 (the fall-back hour is merged). The smoke grid has n_rows = n_zones × n_hours and contains zeros (`tests/test_grid.py`). No test exercises the SQL on a DST month, because the smoke month has none. Add one in Phase 1, when full data exists.
- **Leakage.** `tests/test_leakage.py` is real, not a placeholder:
  - It poisons values at and after the origin with 1e6 and NaN and asserts bit-identical forecasts.
  - Its power check confirms that poisoning the past changes the forecasts.
  - The engine cuts history positionally (`hour_ts < origin`).
  - No `lag_1`, `shift(1)` or `rolling(4)` appears in `src/`, `scripts/` or `dbt/`.
- **Backtest outputs are sane** (`results/smoke/backtest_smoke.csv`, all/all rows): `n` all = y_zero + y_pos (107,304 = 56,637 + 50,667), and `train_end < origin` for every row. WAPE and MASE are left out of the y_zero subset, as intended.
- **Checkpoint 0 caution.** `repo_filesystem.free_gb` = 993.0 is the nominal size of the WSL virtual disk. That disk lives on C:, so the real ceiling is C: free = 88.7 GB. That covers yellow (5.45 GB) plus the optional hvfhv download (16.33 GB). The Checkpoint-0 message must quote C:, not 993 GB.

## Figures

`reports/figures/smoke/F0_smoke_placeholder.png` (the placeholder):
- Axis labels carry units, the plot is readable at 7 in, direct end labels replace a legend, the y-axis starts at 0, and the title is descriptive, not a finding.
- The policy line is correctly suppressed because the policy date is outside the x-range.

Defects:
- **Palette.** The observed series ("actual") uses `PALETTE["model"]` (#1F5F8B). That colour is reserved for models, and F2b in Phase 2 needs actual and model on the same axes.
- **Hard-coded colours.** `#6B7078` (the naive label and the footnote) is hard-coded in `viz/figures.py` instead of coming from `style.py`.
- **Low contrast.** The seasonal-naive line (#B0B4BA) is almost invisible on its own grey band.

## Decisions check

`DECISIONS.md` covers the thresholds, straggler window, DST, weather timezone, downloads, refit and window rules, metrics, smoke window, DuckDB settings and the verify rule. These rules are visible in code or config but have no `DECISIONS.md` line:

- `is_airport = service_zone in ('Airports','EWR')` in `dbt/models/staging/stg_zones.sql`. Note that this counts Newark (NJ) as an airport zone.
- Weather units °F / mph / inch (`sources.weather_units`).
- `http_timeout_seconds: 120`.
- dbt profile `threads: 1` (`dbt/profiles.yml`).
- SeasonalNaive's fallback when a zone has no residual quantiles: `fillna(0.0)`, which gives a degenerate interval (`models/seasonal_naive.py`).

## Fix list

1. Replace the hand-written `results/smoke/smoke_run_clean_clone.json` with one produced by code. Either add a script or make target (e.g. `scripts/00_smoke.py --clean-clone` or `make smoke-clean`) that exports the tracked tree to a temp dir, runs `make setup && make smoke` there, and writes this file with its context field, or drop the file from `config/phase_outputs.yaml` and from the repo. PLAN §0.1 requires every `results/` file to come from code.
2. Remove the stale row `data/raw/weather/open_meteo_2024-10-01_2024-10-31.csv,33595,...` from `data/raw/manifest.csv`. That file is no longer on disk and no code produces it any more. Better still, make `update_manifest` in `src/taxi_shock/download.py` drop rows whose file no longer exists under `data/raw/`, so the committed manifest lists only files the pipeline fetches.
3. Add `DECISIONS.md` lines for each of the five rules listed under Decisions check.
4. Add `dbt/.user.yml` to `.gitignore`. dbt writes it with a per-machine id whenever dbt is run by hand from `dbt/`.
5. In `scripts/checkpoint0.py`, write an explicit `effective_ceiling` field (C: free space) into `results/machine_resources.json`, with a note that the WSL virtual disk grows on C:. Then the 993 GB "repo_filesystem" figure cannot be misread as headroom.
6. In `src/taxi_shock/viz/style.py`, add an `actual` colour (and a `muted_text` colour) to `PALETTE`. Use them in `src/taxi_shock/viz/figures.py::smoke_placeholder` instead of `PALETTE["model"]` and the hard-coded `#6B7078`. Draw the seasonal-naive point line in a darker shade of the baseline grey so it stays visible on its band. Regenerate the placeholder figure.

## Escalation reasons

None.

## Amendments made

None.
