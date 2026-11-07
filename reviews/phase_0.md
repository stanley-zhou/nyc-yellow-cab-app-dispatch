# Phase 0 review — round 3

Reviewer: phase-reviewer · Date: 2026-11-07 · HEAD reviewed: `99630bd` (round-2 fixes in `c7152c8`)

## Verdict

**PASS.** Every DoD item is MET. Every traced number has a source in `results/`, and ruff, pytest, dbt test and `make verify PHASE=0` are all green. Both round-2 fixes and all six round-1 fixes are applied. I re-ran the smoke pipeline on a clean export of HEAD: 17.7 s, and the outputs are byte-identical to the committed copies.

One housekeeping slip remains: a stale review-file reference in a `DECISIONS.md` heading (see "Housekeeping"). It does not affect any DoD item, number, test or decision line, so it does not change the verdict. The Builder should still correct it.

## Earlier fixes: were they applied?

| Round | # | Fix | Status | Evidence |
|---|---|---|---|---|
| 1 | 1 | Clean-clone evidence produced by code | APPLIED | `scripts/clean_clone_smoke.py`, `make smoke-clean`. `results/smoke/smoke_run_clean_clone.json` records commit `b827625` with `working_tree_dirty_at_run: false`. `git diff --stat b827625 HEAD` touches only `DECISIONS.md`, that JSON and `reviews/`, so the tested code is the HEAD code. |
| 1 | 2 | Stale manifest row; prune the manifest | APPLIED | `data/raw/manifest.csv` has 4 rows, identical to the manifest my clean run produced. `test_manifest_drops_files_no_longer_on_disk` passes. |
| 1 | 3 | Five missing decision lines | APPLIED | `DECISIONS.md` lines 45–49 |
| 1 | 4 | Ignore `dbt/.user.yml` | APPLIED | `.gitignore` |
| 1 | 5 | `effective_ceiling` | APPLIED | `results/machine_resources.json` |
| 1 | 6 | Palette `actual` / `muted_text`; no hex literals in figure code | APPLIED | `viz/style.py`. `grep '#[0-9A-F]{6}' viz/figures.py` finds nothing. |
| 2 | 1 | Decision line for the deferred §3 paths | APPLIED | `DECISIONS.md` line 57 (dim_zones, features_demand, fct_weekly_zone_panel, zones_cbd.csv, analysis.md, each with reason and rejected alternative) |
| 2 | 2 | Round-1 heading points to `phase_0_round1.md` | APPLIED | `DECISIONS.md` line 43. The *new* round-2 heading (line 55) repeats the same kind of slip; see Housekeeping. |

## DoD table

| DoD item | Status | Evidence |
|---|---|---|
| `make smoke` passes on a clean clone in < 10 min | MET | I ran `git archive HEAD` into an empty scratch dir and deleted `results/smoke`, `reports/figures/smoke` and `data/smoke.duckdb`; only `data/raw/manifest.csv` was present under `data/raw/`. Then `make setup && make smoke`: rc 0. The run downloaded everything fresh (64,346,071-byte Parquet, lookups, weather), and `dbt build` gave PASS=19. My clone's `smoke_run.json`: `total_seconds` 17.7, `limit_seconds` 600.0, `passed` true. `cmp`: `backtest_smoke.csv`, `forecasts_smoke.parquet` and `F0_smoke_placeholder.png` are identical to the committed files. |
| `ruff` clean | MET | `.venv/bin/ruff check .` → `All checks passed!` |
| `pytest` green | MET | 28 passed, 0 skipped, 0 failed |
| `DECISIONS.md` has its first entries | MET | 45 Phase-0 lines in the required format |
| Task 1: §3 layout, pinned deps, `[chronos]` extra | MET | Every package is pinned with `==`. `uv pip check`: "All installed packages are compatible". torch and chronos-forecasting are only in `[chronos]`. The deferred §3 paths are now logged (line 57). `requires-python = ">=3.11,<3.13"`. |
| Task 2: download with resume, size check, retry, `--months`; lookup and shapefile | MET | `src/taxi_shock/download.py`. `tests/test_download.py` covers resume, skip, identity encoding, upsert and prune. |
| Task 3: Open-Meteo, 9 variables, America/New_York, yearly chunks | MET (documented deviation) | GMT unixtime is converted to local time in `stg_weather` (DECISIONS line 18). `assert_weather_covers_grid` passes. |
| Task 4: dbt → `data/warehouse.duckdb`, `read_parquet` sources | MET | `dbt/models/sources.yml`, `dbt/profiles.yml` |
| Task 5: smoke = download 2024-10 → dbt run+test → seasonal-naive backtest → placeholder figure | MET | `scripts/00_smoke.py`. Clone log: build PASS=19; 107,304 forecast rows and 140 metric rows; figure written. |
| §7: `make verify PHASE=N` | MET | `scripts/verify.py`, `config/phase_outputs.yaml` |
| §7: CLAUDE.md at the root, reviewer agent, `reviews/` | MET | `diff` against `nyc-taxi-start/` is empty for `CLAUDE.md` and `PLAN.md`; `reviews/.gitkeep` is tracked |

## Test output

- `.venv/bin/ruff check .` → `All checks passed!` (rc 0)
- `.venv/bin/pytest -rA` → `28 passed in 1.74s`. The logged "size 34133 != Content-Length 102400" warning is the intended truncated-transfer case in `test_resume_after_truncated_transfer`.
- `.venv/bin/pytest -q tests/test_leakage.py` → 4 passed
- `make verify PHASE=0` → ruff PASS, pytest PASS, dbt_test PASS (`PASS=13 WARN=0 ERROR=0 SKIP=0`, smoke warehouse), outputs PASS (6/6 OK)
- I did not run `dbt test` against the default profile. It targets the full warehouse, which does not exist until Phase 1. The smoke-warehouse run covers every Phase-0 dbt test.
- `git status --short` was empty after all my runs.

## Number trace

| Number (where) | Source | OK? |
|---|---|---|
| F0 title "2024-10-15 to 2024-10-31" | `results/smoke/forecasts_smoke.parquet` `target_ts` range; `config/project.yaml` `smoke.backtest_origins` | yes |
| README "Python 3.12", "3.14", "2025-01-05" | environment facts; `config/project.yaml` `data.policy_date` | yes |
| Commits `99630bd`, `c7152c8` | No numeric claims ("round 2" is a label) | n/a |
| `reports/analysis.md` | Phase 7; not yet produced | n/a |
| Checkpoint 0: yellow 93/93, 5.45 GB, largest 0.116 GB; hvfhv 33/33, 16.33 GB, largest 0.538 GB | `results/download_plan_summary.json`. I recomputed from `results/download_plan.csv`: 5.450 / 0.116 / 16.328 / 0.538. | yes |
| Checkpoint 0: 12 CPUs, 8.23 GB RAM, C: 88.4 GB free | `results/machine_resources.json`. `nproc` = 12; `df -h /mnt/c` = 84G, which is GiB (88.4e9 B ≈ 82–84 GiB, consistent). | yes (see Observation 4) |
| Clean-clone 18.3 s | `results/smoke/smoke_run_clean_clone.json` (code-written). My independent run took 17.7 s. | yes |

## Method sanity

- **Leakage.** `tests/test_leakage.py` is a real test, not a placeholder:
  - it poisons values at or after the origin with 1e6 and NaN at 3 origins and asserts identical forecasts;
  - its power test shows that poisoning the past changes the forecasts;
  - the engine cuts history positionally (`np.searchsorted`, `side="left"`).
- **No short lags.** `grep -E 'lag_1\b|shift\(1\)|rolling\(4\)|lag\(1\)'` over `src scripts dbt/models tests` finds nothing.
- **Grid.** `tests/test_grid.py` and `dbt/tests/assert_grid_complete.sql` check n_rows = n_zones × n_hours, zeros present and no duplicates. 107,304 = 263 zones × 24 h × 17 origins.
- **Backtest.** `evaluate` reports WAPE, MASE, pinball at each quantile, coverage_80 and width_80 for the subsets all / y_zero / y_pos. WAPE and MASE are correctly omitted for y_zero. `train_end < origin` is tested.
- **No machine paths or secrets in tracked files.** `grep` over `results`, `config`, `reports`, `data/raw/manifest.csv` and the dbt yml files finds no home-directory path. Absolute paths exist only at run time in the git-ignored warehouse (DECISIONS line 15).

## Figures

`reports/figures/smoke/F0_smoke_placeholder.png` (opened):

- Axes carry units: "Yellow-taxi pickups per hour (all zones)" and "Local time (America/New_York)".
- The y-axis starts at 0.
- Direct end labels are used instead of a legend.
- Colours: actual is near-black (`PALETTE["actual"]`), seasonal naive is `muted_text` on the light baseline band.
- The footnote explains the band.
- The title is descriptive, not a finding.
- The policy line is correctly absent: the policy date is outside the x-range.
- It is readable at 7 in.

No defects.

## Decisions check

Every threshold, window or rule I found in code and config has a `DECISIONS.md` line:

- config sections: `quality`, `forecast_eval`, `sources` (retries, timeout, pad days, units), `duckdb`, `smoke`;
- dbt rules: threads, DST grid, straggler span, weather fall-back mean/max, DISTINCT duplicates (provisional), `is_airport` incl. EWR;
- model and evaluation rules: SeasonalNaive point/quantile rule and fallback, MASE scale, refit and window rules;
- verify, manifest, palette, clean-clone and deferred-paths rules.

No missing lines.

## Housekeeping (non-blocking; fix with the commit that stores this review)

- `DECISIONS.md` line 55: the heading `### Phase 0 — review round 2 additions (reviews/phase_0.md)` must read `(reviews/phase_0_round2.md)`. Commit `99630bd` renamed that file, and `reviews/phase_0.md` now holds this round-3 review. This is the same kind of slip as round-2 Fix 2.

## Observations for Phase 1 (not Phase-0 defects)

1. **Pickup window boundary.** `int_trips_valid.sql` keeps `pickup_ts < source_month + 1 month + 1 day`, a half-open window, while PLAN writes a closed bracket. Record the boundary choice when Phase 1 writes the filter counts.
2. **Overlapping weather chunks.** `stg_weather` deduplicates them with `DISTINCT` and then averages per hour. When the yearly chunk `open_meteo_2023-12-31_2025-01-01.csv` is downloaded next to the existing smoke chunk, any Open-Meteo revision between the two downloads is silently averaged. Either keep one source file per hour or add a test that overlapping rows are identical.
3. **Grid test target.** `tests/test_grid.py` still reads only the smoke warehouse and skips (and `verify` counts that as a pass) when it is absent. From Phase 1 it must run against `data/warehouse.duckdb`, including a DST month, and must not be skippable inside `verify`.
4. **GB units.** `scripts/checkpoint0.py` uses decimal GB (`GB = 1e9`), while `df -h` prints GiB (88.4 GB vs "84G"). The Checkpoint-0 message to Stanley should say "decimal GB" so the two do not look contradictory.
5. **Carried over from round 2.** Count in `results/data_quality.json` the trips dropped by the grid join: edge stragglers, and pickups stamped in the non-existent spring-forward 02:00 hour.

## Fix list

None.

## Escalation reasons

None.

## Amendments made

None.
