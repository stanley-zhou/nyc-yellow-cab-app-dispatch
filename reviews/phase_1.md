# Phase 1 review: data foundation (dbt), round 2

Reviewer: phase-reviewer (fresh context) · Date: 2026-11-07 · Commit reviewed: `fdab997` (working tree clean) · Previous round: `reviews/phase_1_round1.md` (FIX, 6 items)

## Verdict

**PASS**

All six round-1 fixes are applied, and I checked each one against the warehouse, not only the diff. Every DoD line and every Checkpoint-0 amendment item is MET. Tests are green: ruff, 48 pytest tests with 0 skipped, 42 dbt tests on the full warehouse, and 64 dbt tests in the smoke build. Every number I traced has a source file. No new defects block the phase. Four open questions must go to Stanley in the phase summary (listed at the end).

## DoD table

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | `dbt test` green on full data | MET | `make verify PHASE=1` → dbt test against `data/warehouse.duckdb`: `PASS=42 WARN=0 ERROR=0 SKIP=0` |
| 2 | F1 renders | MET | `reports/figures/F1_demand_map.png` (+ .svg) regenerated 18:46 after the dbt rebuild (warehouse 18:44); opened |
| 3 | DECISIONS: filter thresholds | MET | P0 "Filter thresholds moved into config"; P1 pickup window, filter order, record-format exemptions, unmetered-trip rule |
| 4 | DECISIONS: DST handling | MET | P0 "DST in the grid"; P1 "Grid-join drops"; P1 wall-clock lags |
| 5 | DECISIONS: model_start choice | MET | P1 "`model_start = 2022-01-01` confirmed by the data" → `results/citywide_yearly.csv` |
| 6 | DECISIONS: CBD mapping outcome | MET | P1 "CBD mapping outcome", "Manual overrides", new "FDR Drive / West Side Highway" line → `results/cbd_validation.json` |
| A1 | Pickup-window boundary recorded, consistent with counts | MET | DECISIONS P1 "half-open" = `data_quality.json → rules.pickup_window` |
| A2 | One weather file per hour, or an identity test | MET | `int_weather_selected` + `unique_int_weather_selected_unix_time`; `data_quality.json → weather`: 1,128 overlapping hours, 0 differing |
| A3 | `test_grid.py` on the full warehouse, DST days, cannot be skipped in verify | MET | 9 grid tests PASSED with `TAXI_SHOCK_REQUIRE_WAREHOUSE=1`; verify JUnit: 48 tests, 0 skipped, `no_skips PASS` |
| A4 | Size units explicit | MET | `_gb_decimal` / `_gib` keys in `results/machine_resources.json`, `results/download_plan_summary.json` |
| A5 | Grid-join drops counted | MET | `data_quality.json → grid_join` (286 / 0 / 1,641 / 3) |

Round-1 fix verification:

| Fix | Status | Evidence |
|---|---|---|
| 1 Unmetered trips: own distance bin, out of meter aggregates | MET | Warehouse: `fct_hourly_zone_demand` has `n_revenue_trips`, `n_distance_trips`; 0 zone-hours with `revenue < 0` (round 1: 5,821); `min(mean_distance)` 0.01. `int_trips_valid` has 0 rows with `trip_distance <= 0` and `payment_type <> 0`, and 0 NULL distance/fare rows. Sum of `pickups_dist_unknown` by year = 2,306,077 = `data_quality.json → distance_terciles.pickups_distance_unknown` = `exemptions_used.distance_flex_zero`. Cut points re-estimated on known distances (`c1` 1.29, `c2` 2.62). `assert_panels_match_hourly` now checks the four bins at daily and weekly level. DECISIONS line present. |
| 2 FDR / West Side Highway note | MET | DECISIONS P1 line; `cbd_validation.json → cbd_zones_fee_labels {cbd: 38}`, `cbd_zones_min_fee_share` 0.9629 (zone 232). I checked the named waterfront zones in `config/zones_cbd.csv`: 13, 50, 125, 137, 224, 229, 231, 232, 233, 246 are all `is_cbd=True` with `fee_label=cbd`. |
| 3 Feature-value test | MET | `tests/test_features.py`: independent pandas computation on (local date, local hour) keys, zones 161 and 3, spring-forward and fall-back weeks of 2024, all 7 features, NULL pattern asserted; plus NULL lag at 2024-03-10 02:00. 3 tests PASSED. |
| 4 F1 inset label | MET | "Inset: CBD and neighbours, enlarged" matches the shown extent |
| 5 Zero-pickup zones distinguishable | MET | `NO_DATA_COLOR = #B9BDC4` + hatching; the caption says "Hatched grey" |
| 6 Minor (`day_of_week`, README probes) | MET | `tests/test_grid.py:73`; README `probes` row lists all four |

## Test output

- `ruff check .` → `All checks passed!`
- `pytest -q` → all passed. With the warehouse required (verify JUnit): `tests=48 failures=0 errors=0 skipped=0`.
- Phase-1 warehouse tests alone (`test_features`, `test_grid`, `test_cbd_map`, `test_data_quality`): `20 passed`.
- `dbt test` (full warehouse) → `PASS=42 WARN=0 ERROR=0 SKIP=0 TOTAL=42`
- `make verify PHASE=1` → ruff PASS, pytest PASS, no_skips PASS, dbt_test PASS, outputs PASS (15/15 present and non-empty).
- Regression check that the dbt changes did not break Phase 0: `git archive HEAD` into the scratchpad, then `make setup && make smoke`. Exit 0; smoke dbt `PASS=64 ERROR=0`; `total_seconds` 46.1 against a 600 s limit. Run in the scratchpad so no tracked file changed.

## Number trace

| Number | Where | Source | OK |
|---|---|---|---|
| 93 months, 5.45 decimal GB | commit `ae0f378`, DECISIONS | `results/download_plan_summary.json` | yes |
| 13,015 / 341,589,889 / 12,949 / 13,016 / 11,309 / 0 | DECISIONS | `results/duplicates_probe.json` | yes (round 1) |
| 0.35 % / 89.1 % | DECISIONS | `results/negative_fare_probe.json` | yes (round 1) |
| ratio_to_2019 series | DECISIONS | `results/citywide_yearly.csv` | yes |
| 0.9629, Two Bridges/Seward Park, 38 CBD fee labels | DECISIONS (new) | `results/cbd_validation.json → cbd_zones_min_fee_share`, `cbd_zones_fee_labels` | yes |
| 1.0 / 0.5652 agreement | DECISIONS | `results/cbd_validation.json` | yes |
| "38 CBD zones … 59 % … airports 8 %" | F1 title | `results/figure_stats_phase1.json` (38, 0.5878, 0.078) | yes |
| "2024 daily mean at 48 % of 2019" | F1b title | `figure_stats_phase1.json` 0.4816 = `citywide_yearly.csv` | yes |
| c1 1.29, c2 2.62, 2,306,077, 0.006958 | data_quality.json | written by `scripts/03b_data_results.py` from the warehouse; matches my query | yes |
| Latest commit message `fdab997` | — | contains no numbers | n/a |
| README | — | contains no numbers | n/a |

No untraceable numbers.

## Method sanity (Phase 1)

- **Grid completeness.** 263 zones × 67,912 hours = 17,860,856 rows (`data_quality.json → span`, `hourly_panel`), guarded by `assert_grid_complete` and `test_grid_is_complete_with_explicit_zeros`.
- **Zeros present.** 9,895,526 zero rows, 55.4 % (`hourly_panel`).
- **`is_cbd` geometric vs fee agreement.** 1.0 over the 39 decisive Manhattan zones and 0.5652 over all 69 Manhattan zones; 0 disagreements (`cbd_validation.json`). I accepted this reading in round 1 and still accept it.
- **Filter shares per month saved.** `results/data_quality_monthly.csv` (93 rows). Median share removed 0.0328; overall 0.0297.
- **No lag < 24 h.** A grep for `lag_1`, `lag_12`, `shift(1)`, `rolling(4)` and `lag(` over `src/`, `scripts/`, `dbt/models`, `dbt/macros`, `tests/` (excluding `test_leakage.py`) finds nothing. Feature values are now guarded by `tests/test_features.py`.
- **Observation for Phase 4 (not a defect).** With unmetered trips separated, the yearly split shares (my query on `fct_daily_zone_panel`) are dist_unknown 0.65 % (2024) → 1.86 % (2025) → 2.33 % (2026), and t3 (long) 0.331 → 0.359 → 0.369, while t1 (short) goes 0.332 → 0.307 → 0.306. The unknown bin grows after the policy, so Phase 4's distance heterogeneity must state how `pickups_dist_unknown` is treated. It must also report the static DiD on both trip definitions, as DECISIONS already requires. These shares are my aggregation and are not saved in `results/`. Phase 4 should save them if it cites them.

## Figures

- **F1_demand_map.png.** The title is a finding and traces to results. Log colour bar with a unit label. Single-hue blues; CBD outline in the CBD accent. The inset label is now accurate. No-data zones are mid grey and clearly distinct from the lightest blue. Cosmetic only: there is a small detached red ring in the East River at about 42nd St. I identified it as a detached island polygon of zone 233 (UN/Turtle Bay South), probably U Thant Island. It is real geometry, not an artefact, so no fix is required.
- **F1b_citywide_weekly.png.** No change since round 1, still correct. Units on both axes, y axis from 0, `policy_line` with the standard label, muted dotted NY PAUSE marker, no legend.

## Decisions check

The new rules all have DECISIONS lines: the `distance_known` / `revenue_known` definitions, the `pickups_dist_unknown` bin, cut points estimated on known distances, the FDR/WSH outcome, the feature test, the hatched no-data colour and the inset label. No threshold in the new code lacks a DECISIONS line.

## Fix list

None.

## Escalation reasons

None. These open questions carry over and must appear in the Builder's 5-line summary to Stanley:
- (a) Panel weeks start on Sunday, not ISO Monday as PLAN says (DECISIONS P1; one config switch).
- (b) Record-format exemptions keep 5,249,484 valid rows (`data_quality.json → valid_only_by_format_exemption`, 1.54 % of valid rows overall; they are concentrated after the policy date). Phase 4 must report both trip definitions.
- (c) CBD agreement: 1.0 over decisive zones, 0.5652 over all Manhattan zones (`results/cbd_validation.json`).
- (d) Modeled-zone set for Stanley's confirmation (PLAN Checkpoint 1): 103 zones pass the 1.0 threshold (`results/zone_summary.csv → passes_forecast_threshold`). The group split and the share of 2024 pickups (99.04 % in round 1) are not yet saved as numbers. Phase 2 must save them before quoting them.

## Amendments made

None.
