# Phase 1 review: data foundation (dbt)

Reviewer: phase-reviewer (fresh context) · Date: 2026-11-07 · Commit reviewed: `5e8b76b` (working tree clean)

## Verdict

**FIX**

Tests are green and every DoD line is met. Every number I traced has a source file. One real bug blocks PASS. The record-format exemption keeps unmetered Flex Fare trips with `trip_distance = 0`. Those trips are counted as the shortest distance tercile, and they are also included in `mean_distance` and `revenue`. Their share rises from 0.65 % of valid trips (2024) to 1.86 % (2025) and 2.33 % (2026). So the `pickups_dist_t1` split gains volume after the policy for a reason unrelated to the policy. That split is the input to the Phase 4 heterogeneity test "short trips respond more". There are also four smaller defects: a missing PLAN-requested note, a missing feature-value test, and two figure defects.

## DoD table

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | `dbt test` green on full data | MET | `make verify PHASE=1` → `dbt test` against `data/warehouse.duckdb`: PASS=42 WARN=0 ERROR=0 SKIP=0 |
| 2 | F1 renders | MET | `reports/figures/F1_demand_map.png` (+ .svg), opened; F1b also renders |
| 3 | DECISIONS: filter thresholds | MET | DECISIONS P0 line "Filter thresholds moved into config", P1 lines on the pickup window, filter order and record-format exemptions |
| 4 | DECISIONS: DST handling | MET | P0 "DST in the grid", P1 "Grid-join drops", P1 wall-clock lags |
| 5 | DECISIONS: model_start choice | MET | P1 "`model_start = 2022-01-01` confirmed by the data" → `results/citywide_yearly.csv` |
| 6 | DECISIONS: CBD mapping outcome | MET | P1 "CBD mapping outcome" + "Manual overrides" → `results/cbd_validation.json`, `config/zones_cbd.csv` |
| A1 | Pickup-window boundary recorded, consistent with counts | MET | DECISIONS P1 "half-open"; `results/data_quality.json → rules.pickup_window` uses the same predicate as `macros/trips_flagged.sql` |
| A2 | One weather file per hour or identity test | MET | `int_weather_selected` + dbt `unique_int_weather_selected_unix_time`; `data_quality.json → weather`: 1,128 overlapping hours, 0 differing |
| A3 | `test_grid.py` on full warehouse, DST days, not skippable in verify | MET | `tests/test_grid.py` (2019-03-10, 2024-03-10, 2024-11-03, 2025-11-02 + every spring-forward day); `scripts/verify.py` sets `TAXI_SHOCK_REQUIRE_WAREHOUSE=1` and fails on skips (JUnit XML: 45 tests, 0 skipped) |
| A4 | Size units explicit | MET | `results/machine_resources.json`, `results/download_plan_summary.json` use `_gb_decimal` / `_gib` keys |
| A5 | Grid-join drops counted | MET | `data_quality.json → grid_join`: edge stragglers 286 (pickup), spring-forward gap 0 (pickup) / 3 (dropoff). I checked the 0: `int_trips_flagged` contains no raw row at 02:xx on any spring-forward Sunday, while 03:xx has thousands. |

Phase-body items (outside the DoD, checked for completeness):

| Item | Status | Evidence |
|---|---|---|
| `stg_yellow_trips` projection + `source_month`, NULL `cbd_congestion_fee` pre-2025 | MET | `describe stg_yellow_trips` |
| Filters with counted reasons; per-month share | MET | `results/data_quality.json`, `results/data_quality_monthly.csv` (93 rows); dbt `assert_data_quality_balances` |
| `dim_zones` columns incl. `is_cbd`, `is_airport`, `geometry_available` | MET | `describe dim_zones` |
| `fct_hourly_zone_demand` columns | MET (with caveat, see Fix 1) | `pickups, dropoffs, revenue, mean_distance, n_cbd_fee_trips` (+ `n_format_exempt`) |
| `features_demand` calendar/weather/lags ≥ 24 h | MET | `dbt/models/marts/features_demand.sql`; my independent pandas check (below) |
| Weekly panel with hour band, weekday/weekend, distance tercile, dropoff-in-CBD; daily variant | MET (tercile defect, Fix 1) | `fct_weekly_zone_panel`, `fct_daily_zone_panel` |
| dbt tests: unique/not_null (zone_id, hour_ts), borough accepted_values, pickups ≥ 0, count = n_zones × n_hours, `is_cbd` not null for Manhattan | MET | `dbt/models/schema.yml`, `dbt/tests/assert_grid_complete.sql` |
| `tests/test_grid.py`, `tests/test_cbd_map.py` | MET | both pass |
| "Exclude the FDR/West Side Highway through-routes only if the data makes them ambiguous (note it)" | **NOT MET** | No mention anywhere (`grep -i "FDR\|West Side Highway"` over DECISIONS, src, scripts, config, results: empty). Fix 2. |

## Test output

- `ruff check .` → `All checks passed!`
- `pytest -q` → 45 passed, 0 skipped. 8 warnings, all `Pandas4Warning: Timestamp.dayofweek is deprecated` from `tests/test_grid.py:73`.
- `dbt test` (full warehouse, via verify) → `Done. PASS=42 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=42`
- `make verify PHASE=1` → ruff PASS, pytest PASS, no_skips PASS, dbt_test PASS, outputs PASS (15/15 files present and non-empty). Wall time 56 s.

## Number trace

| Number | Where | Source | OK |
|---|---|---|---|
| 93 yellow months | commit `ae0f378`, DECISIONS | `results/download_plan_summary.json → yellow.months_available`; I cross-checked `data/raw/manifest.csv`: 93 yellow files, manifest bytes = plan bytes = on-disk bytes for all 93 | yes |
| 5.45 decimal GB | DECISIONS | `download_plan_summary.json → yellow.total_gb_decimal` | yes |
| 13,015 / 341,589,889 / 12,949 (2020-01) / 13,016 / 11,309 / 0 cross-file | DECISIONS | `results/duplicates_probe.json → totals`, `per_file` (2020-01: 12,949; 2019-06: 1 vs 2) | yes |
| 0.35 % vs 89.1 % | DECISIONS | `results/negative_fare_probe.json → share_flex_neg_with_twin` 0.003469, `share_other_neg_with_twin` 0.89069 | yes |
| ratio_to_2019 0.2890 / 0.3625 / 0.4635 / 0.4488 / 0.4816 / 0.5724 | DECISIONS | `results/citywide_yearly.csv` | yes |
| "38 CBD zones … 59 % … airports 8 %" | F1 title | `results/figure_stats_phase1.json` (`n_cbd_zones` 38, `cbd` 0.5878, `airports` 0.078), derived from `results/zone_summary.csv` | yes |
| "2024 daily mean at 48 % of 2019" | F1b title | `figure_stats_phase1.json → mean_daily_pickups_2024_vs_2019` 0.4816 = `citywide_yearly.csv` | yes |
| agreement 1.0 / 0.5652 | DECISIONS | `results/cbd_validation.json` | yes |
| README | — | contains no numbers | n/a |

No untraceable numbers.

## Method sanity (Phase 1)

- **Grid completeness.** 263 zones × 67,912 hours = 17,860,856 rows = `count(*)` of `fct_hourly_zone_demand` (`data_quality.json → span`). `test_grid_hours_equal_an_independent_tz_calendar` checks the hour set against pandas/zoneinfo. Explicit zeros: 9,895,526 rows, 55.4 % (`hourly_panel`).
- **Zeros present.** Yes (above, and `test_grid_is_complete_with_explicit_zeros`).
- **`is_cbd` geometric vs fee-based agreement.** Reported. 39 of 69 Manhattan zones get a decisive fee label, and 39/39 agree. Over all Manhattan zones the share is only 0.5652, because 27 non-CBD zones fall in the 0.2–0.8 band: the fee is charged on trips *into* the CBD. The intra-zone signal has 56 decisive zones, 56/56 agree. 11 Manhattan zones have no decisive signal on either measure: 43, 103–105, 120, 128, 142, 143, 194, 202, 237. The test was relaxed from the literal "≥ 95 % of Manhattan zones" to "≥ 95 % of decisive zones" after the Builder saw the data, and the Builder says so openly. I accept this reading. PLAN asks to "report disagreements … and resolve manually", and an ambiguous label is not a disagreement. Both shares are saved, and neither signal disagrees with the geometric rule anywhere. 142, 143, 237 and 43 are real boundary straddlers (intra-zone fee shares 0.46, 0.22, 0.27, 0.36). The Builder already flags them for a Phase 4 robustness drop. **Stanley must be told the 0.5652 number in the phase summary.**
- **Filter shares per month saved.** `results/data_quality_monthly.csv`, 93 months, median share removed 0.0328 (min 0.0170 2026-09, max 0.0491 2020-07). Overall share 0.0297. This replaces the "≈3 %" claim with a measured number.
- **Record-format exemptions (a change to PLAN-specified filters).** CLAUDE.md's data-surprise rule allows this, and the evidence is solid (`negative_fare_probe.json`, `record_format_probe.csv`). Rows that are valid only because of an exemption make up 0.97 % of 2024 valid rows and 6.9 % of 2025 (my aggregation of `data_quality_monthly.csv`). Under the literal rules the median monthly removal share in 2025 would be 0.105, against 0.043 in 2024. Without the exemptions there would be a level shift exactly at the shock, so the rule is justified. The PLAN-literal counts can still be recovered, which is good. Its knock-on effect on the distance columns was not handled (Fix 1).
- **Features (independent check).** For zone 161 over 2024-02-01 → 2024-12-31 I recomputed `lag_24/48/168/336` for every hour, and `mean_same_hour_prev_7d/28d` and `mean_prev_day` for 500 random hours, with pandas from `fct_hourly_zone_demand`: **0 mismatches**. `lag_24` at 2024-03-11 02:00 and `lag_168` at 2024-03-17 02:00 are NULL, as documented. No feature looks back less than 24 h. The grep for `lag_1`, `shift(1)`, `rolling(4)`, `lag(` over `src/`, `scripts/`, `dbt/` finds nothing. No automated test guards these values (Fix 3).
- **Holidays.** 2024 list checked by eye (14 dates incl. Lincoln's Birthday, Election Day); `test_holidays_seed.py` guards drift.
- **Weather.** 0 NULL `temp_f`/`precip_in` in `features_demand`; 7 merged fall-back hours = 7 fall-back days inside the span (2019–2025).
- **Leakage test** (Phase ≥ 2 item, noted only): `tests/test_leakage.py` exists with 2 tests from Phase 0; it will be reviewed in Phase 2.

### Bug behind Fix 1 (evidence)

`int_zone_day_trips.sql` assigns `pickups_dist_t1 = count(*) filter (where trip_distance <= c1)`. Flex trips exempted from the distance lower bound have `trip_distance = 0`, so they all land in t1. Share of valid trips with `trip_distance <= 0`, from `int_trips_valid` by year: 2022 0.18 %, 2023 0.77 %, 2024 0.65 %, **2025 1.86 %, 2026 2.33 %**. The same rows also enter the tercile cut-point estimate (`int_distance_terciles`, pre-period) and pull `mean_distance` down. Flex rows with negative `fare_amount` also enter `revenue`: in 2025-03 their mean `total_amount` is $4.51 against $25.63 for other Flex rows, and 5,821 zone-hours of `fct_hourly_zone_demand` have `revenue < 0`.

## Figures

**F1_demand_map.png.** Title is a finding backed by results. Log colour bar with a unit label. Single-hue Blues. CBD outline in `PALETTE["cbd"]`. The inset makes the CBD readable at 7 in. Defects:
- The inset is labelled "Inset: lower Manhattan", but it shows the lower 55 % of Manhattan's bounding box, up to about 96th St, and Brooklyn/Queens. "Lower Manhattan" normally means the area below about 14th St, so the label is wrong.
- The caption says "Light grey: no pickups in 2024", but `NO_DATA_COLOR = #F2F3F5` cannot be told apart from the lightest Blues colour (`#F7FBFF`) at vmin = 1 pickup. The two zero zones (103, 104, the harbour islands) are therefore not identifiable as the caption claims.

**F1b_citywide_weekly.png.** Units on both axes. Y axis starts at 0. Complete weeks only. Policy line drawn with `policy_line` and the standard label. COVID marker is a muted dotted line. No legend, as it should be. Title backed by results. No defects.

## Decisions check

Every config key in `quality:`, `cbd:`, `panel:`, `annotations:` and `duckdb:` and the figure parameters (60 ft buffer, 55 % inset) has a DECISIONS line. Missing:
- the FDR / West Side Highway through-route decision that PLAN Phase 1 asks to be noted (Fix 2);
- how unmetered distance and fare fields are treated in `mean_distance`, `revenue` and the distance terciles (part of Fix 1).

## Fix list

1. **Give unmetered trips a distance bin of their own and keep them out of the meter-derived aggregates.** In `dbt/models/intermediate/int_zone_day_trips.sql`, add `pickups_dist_unknown` for trips with `trip_distance <= 0` or NULL, and make t1 `0 < trip_distance <= c1`. Carry the new column through `fct_daily_zone_panel.sql` and `fct_weekly_zone_panel.sql`. In `dbt/models/intermediate/int_distance_terciles.sql`, exclude those trips from the cut-point estimate. In `dbt/models/intermediate/int_hourly_pickups.sql`, exclude them from `mean_distance`, and exclude Flex Fare rows with `fare_amount <= 0` from `revenue`, or set revenue NULL for them and add a trip count with known revenue. Extend `dbt/tests/assert_panels_match_hourly.sql` so the four distance bins add up to `pickups` at both daily and weekly level. Add a DECISIONS.md line. Re-run `make dbt` and regenerate `results/data_quality.json` (`distance_terciles`).
2. **Add the PLAN-requested FDR / West Side Highway through-route note to `DECISIONS.md`.** State whether the data made those routes ambiguous, citing evidence from `results/cbd_validation.json` (for example the fee shares of the zones bordering the FDR and the West Side Highway), and whether anything was excluded.
3. **Add a warehouse test of the feature values to `tests/test_features.py` (new file, `pytest.mark.warehouse`).** For at least one zone across a spring-forward and a fall-back week, compare `lag_24/48/168/336`, `mean_same_hour_prev_7d/28d` and `mean_prev_day` with an independent pandas computation from `fct_hourly_zone_demand`, and assert NULL lags at the missing 02:00.
4. **Fix the F1 inset label in `src/taxi_shock/viz/figures.py`.** Replace "Inset: lower Manhattan" with wording that matches the shown extent (for example "Inset: Manhattan below ~96th St", with the street derived from the inset bounds, not guessed).
5. **Make zero-pickup zones distinguishable in `src/taxi_shock/viz/maps.py`.** Use a clearly different no-data treatment (a mid grey or hatching) instead of `#F2F3F5`, or remove the "Light grey" claim from the F1 caption. Regenerate F1.
6. **Minor:** In `tests/test_grid.py:73`, replace `dayofweek` with `day_of_week` (Pandas4Warning). In `README.md`, list all four probes in the `probes` row (it names two; the Makefile runs four).

## Escalation reasons

None. These items are not escalations, but Stanley must see them in the Builder's phase summary as open questions:
- (a) Panel weeks start on Sunday rather than following ISO weeks as PLAN says (DECISIONS P1, flagged by the Builder).
- (b) Record-format exemptions: 6.9 % of 2025 valid trips depend on them; Phase 4 must report both definitions.
- (c) CBD agreement is 1.0 over decisive zones and only 0.5652 over all Manhattan zones (`results/cbd_validation.json`).
- (d) Modeled-zone set: 103 zones pass the 1.0 threshold, covering 99.04 % of 2024 pickups (38 CBD, 22 Manhattan non-CBD, 2 airports, 41 other; `results/zone_summary.csv → passes_forecast_threshold`). The 99.04 % and the group split are my aggregation of that column and are not saved as a number anywhere; Phase 2 should save them.

## Amendments made

None. No threshold, zone set, training window or runtime arrangement needs to change on this evidence. The CBD agreement reading is an interpretation of existing PLAN text, not a threshold change.
