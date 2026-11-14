# Review: E3 (dbt on Snowflake), PLAN Amendment 4, item E3

Reviewer: phase-reviewer (fresh context), 2026-11-14. Commits reviewed: d8d8979, a3bc032, 7ae6e4f, 1895688.

## Verdict

**FIX.** The load, the Snowflake target, the dialect macros and the 89/89 build are real and I reproduced the key claims. But the Snowflake build of `features_demand` is **not** numerically the same as DuckDB's. Two of its rolling-mean columns are truncated to 3 decimals on Snowflake. The parity check did not catch this because it compares only the five weekly marts. The bug is the same class as the fixed-point issue the Builder already found for durations. It does not touch any analysis result, since every downstream script reads DuckDB. It is a portability bug in an E3 deliverable, and the Builder can fix it within the plan.

## DoD table (Amendment 4, E3)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | `snowflake` target beside `duckdb` in `dbt/profiles.yml`, credentials from environment variables only, never committed | MET | `dbt/profiles.yml`: every value goes through `env_var()`, with key-pair auth. `git log -p 73674d6..HEAD` contains no account host, key, `SNOWFLAKE_*=` assignment or home path. `git ls-files` lists no `.env`, `.p8` or `dbt/target/`. `.gitignore` covers `dbt/target/`, `.env` and `data/raw/*`. `make verify` ran dbt on `dev` without any Snowflake variables, so the profile does not break the DuckDB path. |
| 2 | Load cleaned yellow trips 2023-01 → 2026-09 and the HVFHV aggregates (internal stage, `COPY INTO`) | MET | `scripts/24_snowflake_load.py`, `results/snowflake_load.json`: 6 tables, `all_match: true`. I re-counted independently in DuckDB: `int_trips_flagged where drop_reason is null` and `int_trips_valid` over source months 2023-01..2026-09 both give 156,962,851, which equals `tables.yellow_trips_valid.rows_snowflake`. |
| 3 | Run intermediate → marts → channel models and all dbt tests on Snowflake | MET (documented scope) | `results/dbt_targets.json → targets.snowflake.build`: 26 models `success`, 1 seed, 62 tests `pass`. Six DuckDB tests do not run on Snowflake: `assert_data_quality_balances`, `assert_format_exemptions_applied`, `assert_monthly_removal_share_stable`, and three schema tests on `int_trips_flagged`. All of them test the raw-file cleaning, which by design is not loaded. Six source tests replace them. Reason and rejected alternative are in DECISIONS [E3] (1). |
| 4 | SQL kept portable with dbt macros where dialects differ | PARTIAL | `dbt/macros/portable.sql` and `week_start.sql` use `adapter.dispatch`. **Bug:** `features_demand.mean_same_hour_prev_7d` / `_28d` are truncated on Snowflake (see Method sanity). The DuckDB side is unchanged: I compiled all 91 nodes at 73674d6 and at HEAD in scratch worktrees. With whitespace ignored, only `int_weather_selected` (`interval (1) day` → `interval 1 day`) and `assert_channel_matches_weekly` (`+ 6` → `+ interval 6 day`) differ, which matches the DECISIONS claim. |
| 5 | Row counts and test results per target in `results/dbt_targets.json` | MET | `row_counts` (per model, both targets), `targets.duckdb.tests` 62/62, `targets.snowflake.build` 89/89, `parity`, `snowflake_credits_last_7_days`. |
| 6 | CI stays on DuckDB | MET | `.github/workflows/ci.yml` runs `make setup` (`.[dev]` only) and `make smoke`. `[snowflake]` is an optional extra in `pyproject.toml`. `make snowflake` is not part of `all`. |
| 7 | BigQuery not added | MET | grep over py/yml/toml/sql finds nothing. |
| 8 | Runs after Checkpoint 6, with Stanley's account through env vars | MET | Order of commits. DECISIONS [E3] (7). |

## Test output

- `ruff check .`: `All checks passed!`
- `pytest -q`: 136 passed, 0 failed, 0 skipped (warnings are pyfixest/pandas deprecations only).
- `dbt test` (DuckDB, via `make verify`): `PASS=62 WARN=0 ERROR=0 SKIP=0`.
- `make verify PHASE=7` (the E3 outputs are registered under phase 7 in `config/phase_outputs.yaml`): ruff PASS, pytest PASS, no_skips PASS, dbt_test PASS, outputs PASS, including `results/snowflake_load.json` and `results/dbt_targets.json`. Wall time 2m27s.
- I did not rerun `dbt build --target snowflake`. The Snowflake side was checked with read-only queries (below).

## Number trace

| Number | Where | Source | OK |
|---|---|---|---|
| 89/89 build steps and tests | README, commit 7ae6e4f, DECISIONS | `dbt_targets.json → targets.snowflake.build`: 26 models + 1 seed + 62 tests, all success/pass | yes |
| 2023-01-08 → 2026-09-20 | README, DECISIONS | `dbt_targets.json → parity.weeks` | yes |
| 62.4 s | README runtime table, DECISIONS | `dbt_targets.json → targets.snowflake.build.elapsed_seconds` | yes |
| 16.0 min | README runtime table | `snowflake_load.json → wall_seconds` 960.0 | yes |
| 235 entries / 136 tests | README | `presentation_numbers.json → repository` (I re-counted 235 with the stated regex; pytest collected 136) | yes |
| 156,962,851 / 199,416,480 / 20,326,968 | DECISIONS | `snowflake_load.json → tables` | yes |
| 62/62 DuckDB | DECISIONS | `dbt_targets.json → targets.duckdb.tests` | yes |
| 67,968 rows | DECISIONS | `dbt_targets.json → row_counts.int_weather_selected` | yes |
| 8,107,124 rows | DECISIONS | `dbt_targets.json → parity.marts.fct_weekly_pair_speed` | yes |
| ≤ 3.4e−15 | DECISIONS | `parity.marts.fct_weekly_pair_speed` max 3.43e−15 | yes |
| 0.464 credits | DECISIONS | `snowflake_credits_last_7_days.total` 0.4638 | yes |
| 91 nodes, two compiled differences | DECISIONS | not in `results/`; **reproduced by me** | reproduced, unsaved |
| "EXCEPT ALL both ways = 0" | DECISIONS | not in `results/` | **no source** |
| 3.3e−7 (pre-fix duration difference) | DECISIONS | not in `results/` (superseded run, overwritten) | **no source** |
| "every row count matches" | commit a3bc032 | `snowflake_load.json → all_match` | yes |
| "connection test passes" | commit d8d8979 | no saved record; superseded by the load | not a number |

## Method sanity

1. **features_demand rolling means differ across targets (bug).** This comes from a reviewer check with read-only queries and the same environment file, query tag `taxi_shock_e3_review`; the script is in the scratchpad. Aggregate statistics over 2023-03-01 → 2026-09-26 (8,236,108 rows on both targets) match for every column except `mean_same_hour_prev_7d` and `mean_same_hour_prev_28d`. For those two, the DuckDB sum exceeds Snowflake's by about 2.1e−5 relative. Row level (zones 132/161/237/43/236, March 2024): 3,207 of 3,715 rows differ, max abs 8.6e−4 (7d) and 9.6e−4 (28d), mean +4.3e−4. Example: 314.857143 on DuckDB vs 314.857 on Snowflake. Cause: Snowflake's windowed `avg()` over `pickups` (`NUMBER(38,0)`) returns `NUMBER(33,3)`, truncated. I confirmed with `system$typeof` on a 4-row example. `mean_prev_day` (non-window `avg` of `NUMBER(38,0)`) is rounded to 6 decimals: 2,493 rows differ, max abs 4.3e−7. Lags, calendar, weather, `fct_hourly_zone_demand` (all columns) and `fct_daily_zone_panel` matched at 1e−9 in the sample. `fct_daily_zone_channel` matched on aggregate statistics.
2. **Parity scope.** `scripts/25_dbt_targets.py → PARITY` covers only the five weekly marts. `features_demand`, `fct_hourly_zone_demand`, `fct_daily_zone_panel` and `fct_daily_zone_channel` are compared by row count only, so finding 1 went undetected. The README sentence ("the weekly marts match DuckDB exactly") is literally true. The DECISIONS line "Two dialect findings, from the parity check" is incomplete.
3. **Coverage differences explained.** `int_speed_trips` 132,638,940 vs 132,638,936. In DuckDB, exactly 4 valid trips from a pre-2023 source file have pickups at or after 2023-01-01, which matches the first-week exclusion. The last parity week stops at 2026-09-20 ("last complete week"). Week 2026-09-27 has identical source data on both targets and could be included, but excluding it is conservative.
4. **Load integrity.** Every count is checked and the script exits non-zero on a mismatch. `COPY INTO ... on_error = abort_statement`. The yellow export reads the DuckDB `int_trips_flagged` table, so the cleaning is not re-implemented. That is consistent with the plan's "load cleaned yellow trips".
5. **HVFHV.** Loaded and source-tested (`not_null` only, because pair-week is not unique on its keys by construction; documented). No dbt model consumes it on either target, because the HVFHV analyses are Python on Parquet. This is consistent with the plan, which only asks for it to be loaded.

## Figures

None produced by E3. N/A.

## Decisions check

- Present: the load scope and the rejected re-implementation, the dialect macros, the DuckDB-unchanged evidence, the parity window and tolerance, pair-week non-uniqueness, warehouse size and auto-suspend, credentials handling, the optional extra, the connection notes. DECISIONS [E3] 2026-11-14.
- Missing or inconsistent:
  - `REL_TOL = 1e-9` is hard-coded in `scripts/25_dbt_targets.py`. It is recorded in DECISIONS, but CLAUDE.md says no thresholds in code. It should come from `config/project.yaml → snowflake`.
  - The parity-window end rule ("last complete week", which drops 2026-09-27) is in the script docstring but not in DECISIONS. Only the first-week exclusion is recorded.
  - The default `TAXI_SHOCK_SNOWFLAKE_THREADS = 4` in `dbt/profiles.yml` has no line.
  - Commit 7ae6e4f says "DuckDB SQL unchanged". DECISIONS correctly says two compiled nodes changed, semantically equivalently. The DECISIONS wording is the accurate one; no action beyond item 5.

## Fix list

1. In `dbt/models/marts/features_demand.sql`, via a dispatch macro in `dbt/macros/portable.sql`, make the Snowflake `avg()` in `m7`, `m28` and `daily.mean_day` run on a double (e.g. `avg(cast(pickups as double))` in `snowflake__`). Keep the `default__` body byte-identical so DuckDB stays unchanged. Grep the other models for `avg(` / integer division over `NUMBER` columns on the Snowflake path and apply the same rule.
2. Extend `scripts/25_dbt_targets.py → PARITY` to `features_demand` (from `snowflake.months[0]` + 28 days + 14 days of warm-up to the last complete day), `fct_hourly_zone_demand`, `fct_daily_zone_panel` and `fct_daily_zone_channel`. Key on `(zone_id, hour_ts)` / `(zone_id, date|day, …)`. If row pulls are too heavy, add per-key-chunk aggregation. Rebuild on Snowflake, rerun `make snowflake` and commit the new `results/dbt_targets.json` with `all_identical` over all nine marts.
3. Add a third dialect finding to DECISIONS [E3] (3): Snowflake windowed `avg` over integers is `NUMBER(…,3)`, truncated, and the non-window `avg` is rounded to 6 decimals. Give the before-fix magnitude from a saved file, and update the README Snowflake line if parity now covers the hourly and daily marts.
4. Move `REL_TOL` to `config/project.yaml` (`snowflake.parity_rel_tol`) and read it in `scripts/25_dbt_targets.py`. Add DECISIONS lines for the parity end-week rule and the Snowflake thread default.
5. Save the evidence for DECISIONS [E3] (2)–(3) under `results/`: the compiled-SQL comparison (91 nodes, 2 differing, names), the `int_weather_selected` EXCEPT ALL counts, and the pre-fix 3.3e−7 duration difference (e.g. `dbt_targets.json → duckdb_unchanged` and `dialect_findings`). Otherwise remove those numbers from `DECISIONS.md`.
6. Optional: in the README Snowflake line, say "the dbt models downstream of the cleaning" instead of "the same dbt models". `stg_yellow_trips`, `int_trips_flagged` and `fct_data_quality_monthly` are disabled on Snowflake.

## Escalation reasons

None. The defect is a fixable dialect bug in an optional-stack item. No analysis result, gate or storyline depends on Snowflake outputs.

## Amendments made

None.
