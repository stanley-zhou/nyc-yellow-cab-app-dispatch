# Review: E3 (dbt on Snowflake), PLAN Amendment 4, item E3, round 2

Reviewer: phase-reviewer (fresh context), 2026-11-14. Commits reviewed: d8d8979, a3bc032, 7ae6e4f, 1895688, 71d59e3 (round-1 fixes). Round 1: `reviews/e3_round1.md` (FIX).

## Verdict

**FIX (round 2 of 2).** Every round-1 fix is in place, and I reproduced the important ones. The Snowflake `avg()` truncation is gone: a read-only spot check returns `FLOAT[DOUBLE]`, with zero difference from DuckDB. Parity now covers nine marts, all identical. The DuckDB-unchanged evidence regenerates byte-for-byte apart from its timestamp. Every DoD item is MET. Two numbers in the main E3 entry of `DECISIONS.md` lost their source: the round-1 rerun overwrote `results/dbt_targets.json`, and the entry still cites that file for values it no longer contains. The fix is two in-place edits. Nothing else is open.

## DoD table (Amendment 4, E3)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | `snowflake` target in `dbt/profiles.yml`, credentials from env vars only, never committed | MET | Unchanged since round 1 (verified there). `git show 71d59e3` contains no host, key, password or home path (grep). `make verify` ran dbt on DuckDB with no Snowflake variables set. |
| 2 | Load cleaned yellow trips 2023-01 → 2026-09 and the HVFHV aggregates (internal stage, `COPY INTO`) | MET | `results/snowflake_load.json`, `all_match: true`. The independent re-count of 156,962,851 is in round 1. |
| 3 | Run intermediate → marts → channel models and all dbt tests on Snowflake | MET | `results/dbt_targets.json → targets.snowflake.build`: 26 models success, 1 seed, 62/62 tests pass, `generated_at` 2026-11-14T23:28:31Z (the rebuild after the fix), 63.3 s. The DuckDB-only tests disabled on Snowflake are documented in DECISIONS [E3] (1). |
| 4 | SQL portable with dbt macros where dialects differ | MET (was PARTIAL) | `dbt/macros/portable.sql → avg_double` (`snowflake__` casts to double, `default__` is `avg(x)`). It is applied to `features_demand` (`m7`, `m28`, `mean_day`) and to `stg_weather` (`cloudcover`, `relativehumidity_2m`). My grep of the remaining `avg(` calls and `/` divisions in `dbt/models` and `dbt/macros` finds only double inputs, `diff_seconds` (cast to double on Snowflake), or exact integer multiples (`event_week`). My read-only spot check on Snowflake (query tag `taxi_shock_e3_review_r2`; zones 132/161/237, 2024-03-10 → 03-11, which includes the spring-forward day; 141 rows on both sides) gives max abs difference 0.0 for `mean_same_hour_prev_7d`, `_28d`, `mean_prev_day` and `rel_humidity_pct`. `system$typeof` = `FLOAT[DOUBLE]`. DuckDB unchanged: I reran `scripts/26_duckdb_sql_unchanged.py --base a3bc032`. It gives 91/91 nodes, the same two differing nodes, EXCEPT ALL 0/0 on 67,968 rows and `duckdb_unchanged: true`. Only `generated_utc` changed, and I restored the committed file. |
| 5 | Row counts and test results per target in `results/dbt_targets.json` | MET | `row_counts` (30 models, both targets), `targets.duckdb.tests`, `targets.snowflake.build`, `parity` (nine marts, `all_identical: true`), `dialect_checks`, credits. |
| 6 | CI stays on DuckDB | MET | `.github/workflows/ci.yml` not touched in 71d59e3. `make snowflake` is not in `all`. |
| 7 | BigQuery not added | MET | Unchanged since round 1. |
| 8 | After Checkpoint 6, Stanley's account via env vars | MET | Commit order. DECISIONS [E3] (7). |

## Test output

- `ruff check .`: `All checks passed!`
- `make verify PHASE=7` (E3 outputs registered under phase 7, now including `results/e3_duckdb_sql_check.json`): ruff PASS, pytest PASS (136 tests, 0 skipped), no_skips PASS, dbt_test PASS (`PASS=62 WARN=0 ERROR=0 SKIP=0`), outputs PASS. Wall time 5m23s.
- `pytest -q tests/test_phase7.py -k dbt_targets`: 1 passed. It now also covers date vs datetime64 equality and a changed string.
- I did not rerun `dbt build --target snowflake`. Snowflake was checked with one read-only query set (above).

## Number trace

| Number | Where | Source | OK |
|---|---|---|---|
| 89/89, 26 models + 1 seed + 62 tests | README, DECISIONS (4) | `dbt_targets.json → targets.snowflake.build` | yes |
| 63.3 s | README runtime table, DECISIONS (4), round-1 entry | `targets.snowflake.build.elapsed_seconds` | yes |
| 16.0 min | README | `snowflake_load.json → wall_seconds` | yes (round 1) |
| "nine … marts match DuckDB exactly", "all nine identical" | README, commit 71d59e3 | `parity.marts` (9 entries, each `identical: true`, `cells_differing: 0`), `parity.all_identical` | yes |
| 2023-01-08 → 2026-09-20 | DECISIONS (4) | `parity.windows.weeks` | yes |
| 8,107,124 rows | DECISIONS (4) | `parity.marts.fct_weekly_pair_speed.rows_compared_both` | yes |
| 1e−9 | DECISIONS, config | `config/project.yaml → snowflake.parity.relative_tolerance`, `parity.relative_tolerance` | yes |
| 3.3e−7 | DECISIONS (3) | `dialect_checks.duration_minutes_decimal_vs_double.max_relative_difference` 3.28e−7 | yes |
| 91 nodes, 2 differing, 67,968 rows, EXCEPT ALL = 0 | DECISIONS (2) | `results/e3_duckdb_sql_check.json` (reproduced) | yes |
| 17,091,972 cells; 9.6e−4 / 8.6e−4 / 4.8e−7 | round-1 entry | `dbt_targets_before_avg_fix.json → parity.marts.features_demand` (cells_differing; max rel 9.63e−4, 8.57e−4, 4.78e−7) | yes |
| 0.785 credits | round-1 entry | `snowflake_credits_last_7_days.total` 0.7852 | yes |
| 236 entries, 136 tests | README | `presentation_numbers.json → repository` | yes |
| **0.464 credits** | DECISIONS [E3] (6), cited to `dbt_targets.json → snowflake_credits_last_7_days` | That field now reads **0.785**. The before-fix file reads 0.658. No file in `results/` contains 0.464. | **no source** |
| **≤ 3.4e−15** (duration difference after the cast) | DECISIONS [E3] (3) | The current file gives `fct_weekly_pair_speed.max_relative_difference.sum_duration_min` = **2.75e−15**. The 3.43e−15 that round 1 traced was in the overwritten file. The bound still holds, but no file contains the number. | **no source** |

## Method sanity

1. **Fix verified on Snowflake, not just in compiled SQL.** See DoD 4. The before-fix file is a genuine run with the new script against the old build: build `generated_at` 22:55, 62.4 s, and only `features_demand` differs. The after-fix run is against the new build (23:28). The weather means were exact before the fix too, because one source row per hour makes `avg` of a single integer exact. The cast there is defensive, which is correct.
2. **Parity windows are sound.** Daily and hourly marts are compared from 2023-01-02, which excludes the straggler-affected first day. `features_demand` is compared from 2023-01-30, so its longest look-back (28 days, `days_back(28, 1)`) does not reach 2023-01-01. The end is 2026-10-01 exclusive, and both targets end at the same source month. The comparison runs month by month in 45 chunks, with `rows_compared_both` equal to the rows on each side for every mart (no key-only rows).
3. **Comparison logic.** `compare()` now types columns explicitly (time, number, text) and raises on non-numeric values in a numeric column (`errors="raise"`) instead of coercing them to NaN. That closes the earlier risk that a NaN-coerced mismatch could pass silently.
4. **Observation, no action:** `snowflake__event_week` uses `cast(x / 7 as integer)`, which rounds on Snowflake, while DuckDB uses floor `//`. It is exact only because both arguments are Sunday week starts, which the macro comment states. Parity shows `event_week` max diff 0.0 on all five weekly marts. If the macro is ever called on a non-week-start column, use `floor()`.
5. **Observation, no action:** the `dialect_checks` grouping uses Snowflake `date_trunc('week', …)`, which starts weeks on Monday by default, not the project's Sunday panel week. It only sizes an illustration, and the JSON says "week". It does not affect any result.

## Figures

None produced by E3. N/A.

## Decisions check

- Round-1 gaps are closed. The tolerance is in config (`snowflake.parity.relative_tolerance`), and so is the warm-up (`snowflake.parity.warmup_days`). The window rules (second week to last complete week, second day, second day + 28) are in the round-1 entry (2). The 4-thread default and the rejected alternative are in (4). The third dialect finding is in (1).
- Script 26 is named in DECISIONS (2) with its `--base` argument. It is not in `make snowflake`, which is acceptable for a one-off evidence script.
- Only the two stale citations in the Number trace remain.

## Fix list

1. In `DECISIONS.md`, entry `[2026-11-14] [E3] dbt on Snowflake — design and result`, item (6): the credit figure 0.464 is cited to `results/dbt_targets.json → snowflake_credits_last_7_days`, which now reads 0.785. Either replace it with the current value and file, or mark 0.464 as superseded by the round-1 entry's 0.785 and drop the file citation from the old value. Do not quote a number that no file contains.
2. In the same entry, item (3): replace "≤ 3.4e−15" with the value in the current file (`results/dbt_targets.json → parity.marts.fct_weekly_pair_speed.max_relative_difference.sum_duration_min`, 2.7e−15), or with the max over that mart's columns (3.6e−15, `sum_fare`), and name the field.
3. Edit both in place, without adding a new entry. If a new entry is added, rerun `scripts/23_presentation_numbers.py` so the README's "236 entries" stays sourced.

## Escalation reasons

None. This is fix round 2. The remaining items are stale citations created by the round-1 rerun, not a repeat of a round-1 failure.

## Amendments made

None.
