# Phase 0 review — round 2

Reviewer: phase-reviewer · Date: 2026-11-07 · HEAD reviewed: `91936c7` (round-1 fixes in `b827625`, clean-clone evidence in `bbfcb93`)

## Verdict

**FIX** — I checked all six round-1 fixes and each one is applied. I re-ran the smoke pipeline on a clean export of HEAD and it passed in 18.4 s, with the same outputs as the committed copies. Two items remain, both documentation-only:

- Part of the §3 layout was left out, and `DECISIONS.md` does not record that choice.
- A `DECISIONS.md` heading points to a review file that has since been renamed.

## Round-1 fixes: were they applied?

| # | Round-1 fix | Status | Evidence |
|---|---|---|---|
| 1 | Clean-clone evidence must come from code | APPLIED | `scripts/clean_clone_smoke.py` + `make smoke-clean`. `results/smoke/smoke_run_clean_clone.json` records `git_commit` b827625 and `working_tree_dirty_at_run` false. The only later commits change that JSON and rename the review file, so the code it tested is the code at HEAD. |
| 2 | Remove the stale weather row; prune the manifest | APPLIED | `data/raw/manifest.csv` lists only the 4 files on disk. `update_manifest` drops rows whose file is missing. New test `tests/test_download.py::test_manifest_drops_files_no_longer_on_disk` passes. |
| 3 | Five missing decision lines | APPLIED | `DECISIONS.md`, section "review round 1 additions": is_airport/EWR, weather units, HTTP timeout, dbt threads, SeasonalNaive fallback |
| 4 | Ignore `dbt/.user.yml` | APPLIED | `.gitignore` last line |
| 5 | `effective_ceiling` in machine resources | APPLIED | `results/machine_resources.json` → `effective_ceiling: {source: windows_c_drive, free_gb: 88.4}` |
| 6 | Palette: `actual`, `muted_text`; no hex literals; visible naive line | APPLIED | `viz/style.py` PALETTE. `viz/figures.py` contains no hex literals. In the regenerated PNG the naive line is visible on its band (see Figures). |

## DoD table

| DoD item | Status | Evidence |
|---|---|---|
| `make smoke` passes on a clean clone in < 10 min | MET | I ran `git archive HEAD` into an empty scratch dir, deleted `results/smoke` and `reports/figures/smoke`, then ran `make setup && make smoke`. Exit 0. The run really downloaded the files (64,346,071-byte Parquet). `smoke_run.json` in the clone: `total_seconds` 18.4, `limit_seconds` 600.0, `passed` true. `backtest_smoke.csv`, `forecasts_smoke.parquet` and `F0_smoke_placeholder.png` are byte-identical to the committed copies (`cmp`). |
| `ruff` clean | MET | `All checks passed!` |
| `pytest` green | MET | 28 passed, 0 skipped |
| `DECISIONS.md` has its first entries | MET | 42 Phase-0 lines in the required format. One judgement call is still missing (Fix 1). |
| Task 1: §3 layout; pinned deps; `[chronos]` extra | PARTIAL | Deps: every package is pinned with `==`, `uv pip check` → "All installed packages are compatible", and torch/chronos are only in `[chronos]`. Layout: every Python module in §3 exists, later ones as docstring stubs, and that choice is logged. Five §3 paths do not exist and nothing records why: `dbt/models/marts/dim_zones.sql`, `features_demand.sql`, `fct_weekly_zone_panel.sql`, `config/zones_cbd.csv`, `reports/analysis.md`. Deferring them to their phases is reasonable (an empty dbt model would break `dbt build`), but it is an unrecorded judgement call. Round 1's statement "Every §3 path exists" was wrong. |
| Task 2: download (resume, size check, retry, `--months`, lookup + shapefile) | MET | `src/taxi_shock/download.py`. `tests/test_download.py` (resume, skip, identity encoding, manifest). |
| Task 3: Open-Meteo, 9 variables, yearly chunks | MET (documented deviation) | Requests use GMT unixtime and are converted in `stg_weather`; the DECISIONS "Data surprise" line explains why. `assert_weather_covers_grid` passes. |
| Task 4: dbt → `data/warehouse.duckdb`, `read_parquet` sources | MET | `dbt/models/sources.yml` (`external_location`), `dbt/profiles.yml` |
| Task 5: smoke = download 2024-10 → dbt run+test → seasonal-naive backtest → placeholder figure | MET | `scripts/00_smoke.py` stages. Clone log: `dbt build` PASS=19, 107,304 forecast rows, figure written. |
| §7: `make verify PHASE=N` | MET | `scripts/verify.py`, `config/phase_outputs.yaml` |
| §7: CLAUDE.md at the root, reviewer agent, `reviews/` | MET | `diff` against the source copies is empty for `CLAUDE.md`, `PLAN.md` and `.claude/agents/phase-reviewer.md` |

## Test output

- `.venv/bin/ruff check .` → `All checks passed!` (rc 0)
- `.venv/bin/pytest -q` → 28 passed (rc 0)
- `.venv/bin/pytest -q tests/test_leakage.py` → 4 passed
- `make verify PHASE=0` → `ruff PASS`, `pytest PASS`, `dbt_test PASS` (PASS=13 WARN=0 ERROR=0 on the smoke warehouse), `outputs PASS` (6/6 OK)
- I did not run `dbt test` against the default profile. It targets the full warehouse, which is only built in Phase 1, and running it would create `data/warehouse.duckdb`. The smoke-warehouse run inside `verify` covers every Phase-0 dbt test.
- `git status` was clean after all my runs.

## Number trace

| Number (where) | Source | OK? |
|---|---|---|
| F0 title "2024-10-15 to 2024-10-31" | `results/smoke/forecasts_smoke.parquet`: `target_ts` min 2024-10-15 00:00, max 2024-10-31 23:00 | yes |
| README "Python 3.12", "3.14", "2025-01-05" | environment facts; `config/project.yaml` `data.policy_date` | yes |
| Latest commit messages (`phase 0: ...`) | no numeric claims | n/a |
| `reports/analysis.md` | not yet produced (Phase 7) | n/a |
| Checkpoint 0: yellow 93/93, 5.45 GB, largest 0.116 GB; hvfhv 33/33, 16.33 GB | `results/download_plan_summary.json`. I recomputed from `results/download_plan.csv` and got 5.450 / 0.116 / 16.328 / 0.538. | yes |
| Checkpoint 0: 12 CPUs, 8.23 GB RAM, C: 88.4 GB free | `results/machine_resources.json`. `df -h /mnt/c` now shows 84G (GiB) available, which is consistent. | yes |
| Clean-clone 18.3 s | `results/smoke/smoke_run_clean_clone.json`, written by `scripts/clean_clone_smoke.py`. My independent run took 18.4 s. | yes |

## Method sanity

- **Leakage.** The test is real.
  - `tests/test_leakage.py` poisons every value at or after the origin with 1e6 and with NaN, and asserts bit-identical forecasts at 3 origins.
  - A power test checks that poisoning the past does change the forecasts.
  - The engine cuts history positionally (`np.searchsorted` on the sorted `hour_ts`, `side="left"`).
- **Grid.** `tests/test_grid.py` asserts n_rows = n_zones × n_hours, zones = lookup count, zeros present and no duplicates. The dbt test `assert_grid_complete` repeats the check in SQL.
- **Backtest sanity** (`results/smoke/backtest_smoke.csv`, all/all):
  - n = 107,304 = 56,637 (y = 0) + 50,667 (y > 0).
  - WAPE is 0.184. MASE is 1.069, as expected for seasonal naive scored against its own in-sample scale.
  - 80% coverage is 0.861.
  - No missing forecasts, q10 ≤ q90 on every row, and `train_end < origin` on every row.
- **Carry-forward for Phase 1 (not a Phase-0 defect).** `fct_hourly_zone_demand` LEFT JOINs counts onto the grid. Any trip whose pickup hour is not in the grid is therefore silently dropped. That covers two cases:
  - edge stragglers, which DECISIONS already says will be counted;
  - pickups stamped in the non-existent spring-forward 02:00 hour, which DECISIONS does not mention.

  Phase 1 must count both cases in `results/data_quality.json`. It must also add a DST-month grid test, because the smoke month has no DST transition.
- **Note: verify skips the grid test silently.** `tests/test_grid.py` is skipped when `data/smoke.duckdb` is absent, and `verify` treats a skip as a pass. In Phase 0 the `dbt test --smoke` step would still fail in that case, so nothing is masked yet. No fix is required now.

## Figures

`reports/figures/smoke/F0_smoke_placeholder.png` (I opened it):

- Both axes are labelled with units ("Yellow-taxi pickups per hour (all zones)", "Local time (America/New_York)").
- The y-axis starts at 0.
- Direct end labels are used and there is no legend.
- The actual series is near-black (`PALETTE["actual"]`). The seasonal-naive line is dark grey (`muted_text`) and visible on the light band.
- The footnote explains what the band is.
- The title is descriptive, not a finding.
- The policy line is correctly absent: 2025-01-05 is outside the x-range.
- The figure is readable at 7 in wide.

No defects.

## Decisions check

The rules visible in code and config all have lines, including the five added in round 1:

- config `quality`, `forecast_eval`, `sources`, `duckdb`, `smoke`;
- DST handling, weather timezone, straggler span, MASE scale, horizon buckets, the refit and window rules;
- the manifest, palette and clean-clone rules.

Missing or broken:

- No line records that the §3 dbt marts (`dim_zones`, `features_demand`, `fct_weekly_zone_panel`), `config/zones_cbd.csv` and `reports/analysis.md` are deferred to their phases instead of being stubbed. The stub line covers only the Python modules.
- The heading `### Phase 0 — review round 1 additions (reviews/phase_0.md)` points to `reviews/phase_0.md`. That path now holds this round-2 review; the round-1 review is in `reviews/phase_0_round1.md`.

## Fix list

1. In `DECISIONS.md`, add a Phase-0 line recording that the §3 paths `dbt/models/marts/dim_zones.sql`, `features_demand.sql`, `fct_weekly_zone_panel.sql`, `config/zones_cbd.csv` and `reports/analysis.md` are created in Phase 1 / Phase 7 rather than stubbed in Phase 0, with the reason (for example, an empty dbt model breaks `dbt build`) and the rejected alternative.
2. In `DECISIONS.md`, change the heading reference `(reviews/phase_0.md)` to `(reviews/phase_0_round1.md)`.

## Escalation reasons

None.

## Amendments made

None.
