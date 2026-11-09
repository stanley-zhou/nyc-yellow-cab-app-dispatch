# Phase 2 review: probabilistic forecasting before the shock

Reviewer: phase-reviewer subagent, fresh context, 2026-11-09. Commit under review: `df9c541`.

## Verdict

**FIX**

All five DoD items are met and the tests are green. The leakage test is real. Every model is compared with SeasonalNaive using a number. No lag shorter than 24 h exists. The remaining items are fixable inside the plan:
- Chronos-2 raw quantiles go through different post-processing than every other model.
- Chronos-2 "before vs after" calibration is reported on unmatched periods.
- The F2 title's ranking claim is ambiguous, and the figure does not show it.
- Several decision lines are missing.
- The leakage test does not cover the exogenous path.

No escalation trigger was found.

## DoD table

| # | Item (PLAN Phase 2) | Status | Evidence |
|---|---|---|---|
| 1 | Every model beats or is compared with `SeasonalNaive` using a number | MET | `results/forecast_summary.json → wape_relative_to_seasonal_naive_expanding`. LGBM 0.6946, AutoETS 0.7649, Chronos-2 0.6823 / 0.6851 (all zones). The same figures exist for each zone group. MASE is in `results/backtest_2024.csv` (seasonal naive 1.3377, LGBM 0.9780). |
| 2 | Coverage reported | MET | `coverage_80` and `width_80` exist for every model × window × calibration × zone group × horizon bucket × subset in `results/backtest_2024.csv`. Before/after values are in `results/conformal.json` (`rows`, `rolling.coverage_and_width`). For Chronos-2, see fix 2. |
| 3 | `tests/test_leakage.py` poisons the future and asserts unchanged predictions | MET (gap: fix 8) | Future pickups are set to 1e6 and to NaN. Checked for 4 model factories × 3 origins, plus a past-poisoning power check. 16/16 pass when run alone. Chronos-2 input construction is covered by `tests/test_chronos_inputs.py` (10/10, includes a DST day). |
| 4 | Metrics: WAPE, MASE, pinball at each quantile, 80% coverage, width, per zone group (CBD / Manhattan non-CBD / airports / other) and horizon bucket; y = 0 hours handled explicitly | MET | `backtest_2024.csv`: metrics `wape, mase, pinball_q10/q50/q90, coverage_80, width_80, bias, mae`. Zone groups: all, cbd, manhattan_non_cbd, airports, other. Horizon buckets: h01-06 … h19-24. Subsets: `all / y_pos / y_zero`. MAPE is not reported (allowed). |
| 5 | Both training windows reported, one chosen as primary in DECISIONS | MET | Both windows are in `backtest_2024.csv`. Primary = expanding under a pre-registered rule (`results/forecast_summary.json → primary_window`: 2.4228 vs 2.4163, below the 1% tie). The rule was committed in `4ea6115` (2026-11-08 00:25). The LGBM test forecasts are dated 04:40 and later, so the rule came first. |
| 6 | Monthly refit; daily origins | MET | `results/lgbm_refits.csv`: 36 refits (12 validation, 12 test expanding, 12 test sliding). `refit_mask("monthly")` in `backtest.py`. |
| 7 | StatBaseline (mandatory) | MET | AutoETS(season 7) on daily totals × lagged hour profile. The deviation from hourly ETS has a recorded reason (DECISIONS P2 line 148). The statsforecast guard `if m > 24` was verified at `statsforecast/ets.py:40`. Fallbacks: 0 in `logs/backtest_sn_stat.log`, but the count is not in `results/` (fix 9). |
| 8 | Global LGBM quantile with a small grid on 2023 and a recorded grid | MET | `results/lgbm_tuning.csv` (8 points × 3 quantiles), `results/lgbm_params.json` (`chosen_hit_max_rounds: false`). Refit early stopping follows the amendment of 2026-11-08. |
| 9 | Chronos-2 zero-shot: 2048 h context, daily origins, Colab, covariates | MET | `results/chronos_run.json` and `results/chronos_import_check.json` (`passed: true`, 1,809,298 / 3,153,860 rows, hashes match). Two covariate variants. The primary variant is undecided (fix 7). |
| 10 | Split-conformal with 2023 residuals per zone group; before/after for every model with intervals | PARTIAL | The 2023 CQR and the rolling 12-week method (amendment) are reported for all trained models. Chronos-2 has no 2023 forecasts. Its raw coverage starts at 2024-01-01 while its rolling coverage starts at 2024-03-25, so its before/after compares different rows (fix 2). |
| 11 | Modeled zones and the share of pickups in non-modeled zones | MET | `results/modeled_zones.json`: 103 zones, 0.990412 / 0.009588. |
| 12 | README states the task definition word for word | MET | `README.md → Forecasting task`. |
| 13 | Outputs: `backtest_2024.csv`, F2, F2b | MET | Present and non-empty (`make verify PHASE=2`). `make figures` regenerates all figures byte for byte (git status clean afterwards). |

## Test output

`make verify PHASE=2` exited 0 after 1 min 03 s:
```
ruff       PASS   (All checks passed!)
pytest     PASS   (85 passed)
no_skips   PASS   (skipped tests: 0)
dbt_test   PASS   (PASS=47 WARN=0 ERROR=0 SKIP=0, full warehouse)
outputs    PASS   (8/8 phase-2 files present)
```
Leakage tests run on their own: `pytest tests/test_leakage.py tests/test_chronos_inputs.py tests/test_conformal.py` gave 31 passed (16 leakage, 10 Chronos inputs, 5 conformal).

## Number trace

| Number | Where it appears | Source | OK |
|---|---|---|---|
| 103 zones, ≥ 1.0, 99.04 % / 0.990412 | README | `results/modeled_zones.json` | yes |
| 48 %, 0.4816, 0.4635, 0.4488 | README | `results/citywide_yearly.csv → ratio_to_2019` | yes |
| 0.165 (Chronos-2 future), 0.241 (naive) | F2 title | `forecast_summary.json → wape_by_zone_group` 0.1645 / 0.2411 | yes (fix 3: wording) |
| All 25 F2 bar labels | F2 | `backtest_2024.csv` (raw, expanding/zero_shot, all/all), e.g. AutoETS other 0.6047, LGBM airports 0.1641 | yes (spot-checked 10) |
| 131 of 168 hours, 2024-10-13, Midtown Center | F2b title | `figure_stats_phase2.json`. Recomputed from `results/fan_chart_f2b.csv` (161, raw, expanding): 131 | yes |
| ≈ 345 q10 plateau | DECISIONS P2 (F2b note) | `fan_chart_f2b.csv`, max q10 on Wed–Fri daytime = 345.33 | yes |
| 2706.7 / 4657.9 / 3724.5 s, 3.08 h, 558.9 s | DECISIONS P2 | `results/lgbm_refits.csv` | yes |
| q0.5 median "2922", q0.9 median "902" | DECISIONS P2 | `lgbm_refits.csv` gives 2922.5 and 902.5 | truncated (fix 12) |
| 0.1645 / 0.1652 / 0.1675 / 0.1844 / 0.2411, 2.3274 / 2.4228, coverage ranges 0.7930–0.8220, 0.8446 | DECISIONS P2 findings | `forecast_summary.json`, `conformal.json` | yes |
| 257,108 vs 333,716 rows (pre-fix NaN bug) | DECISIONS P2 | not reproducible from `results/`: it describes a superseded run | observation only (bug narrative, not a reported result) |
| Exploratory ETS/Theta/MSTL timings (124 s, 30 s, 4.5 s, ≈ 40 h, −110 to −272) | DECISIONS P2 line 148 | not in `results/`, labelled "exploration, not a result" | observation: must never appear in README or the report without a results file |
| Commit message `df9c541` | | contains no numbers | n/a |

`reports/analysis.md` does not exist yet (Phase 7).

## Method sanity

- **Short lags:** none. A grep for `lag_1`, `shift(1)` and `rolling(4)` over `src/ scripts/ dbt/` finds only `shift(1)` on **daily-indexed** matrices in `features.py:65,66,78`, which is a 1-day shift and is correct. The dbt `features_demand` uses RANGE frames of 1 day or more.
- **Horizon index:** `horizon` (= local hour + 1) is in `CALENDAR_FEATURES` and therefore in the LGBM feature set. It is identical to hour of day at a 00:00 origin, and this is documented.
- **Leakage:** the engine cuts `history` by position at the origin. LGBM, ETS and naive are poisoned and checked, and past poisoning changes their forecasts. **Gap:** the exogenous table (weather, holidays) is never poisoned. LGBM uses observed weather at the target hour by design, which PLAN lists as a limitation. The test docstring says "No forecast may depend on data at or after its origin", which is false for that by-design path. No test checks that exog rows beyond the target day are unused (fix 8).
- **SeasonalNaive comparison:** every model beats naive in every zone group and horizon bucket (CBD by bucket: LGBM 0.2496/0.1498/0.1304/0.1734 vs naive 0.3412/0.2211/0.1869/0.2482).
- **Chronos-2 vs LGBM:** the zero-shot Chronos-2 has lower all-zone WAPE (0.1645 vs 0.1675) and lower mean pinball (2.3274 vs 2.4228). LGBM is lower only in Manhattan non-CBD (0.1507 vs 0.1512). As a reviewer-only check, not a project result, a day-resampled bootstrap of the all-zone WAPE gap (LGBM − Chronos-2 future) gave a 95 % interval of about [0.0002, 0.0054]. The gap is small, and an iid-day bootstrap understates its uncertainty. This is a finding for Stanley's summary, not a defect.
- **Chronos-2 post-processing differs from the other models (fix 1).** LGBM, ETS and naive quantiles are sorted and clipped at 0. Chronos-2 raw quantiles are used as returned. `chronos_import_check.json` records 674 crossing rows in the test file (`test_quantile_crossings`). Reviewer count on `results/chronos_forecasts.parquet`: 109,795 (future) / 74,975 (past) negative q10 and 1,319 / 221 negative q50. Measured effect is small: coverage unchanged to 4 dp, q10 pinball 1.5227 → 1.5214, width 21.045 → 21.032. It is still a methods inconsistency. DECISIONS line 144 says the import check validates "finite and ordered quantiles", which overstates it: crossings are counted, not rejected.
- **Calibration:**
  - Raw coverage is below 0.80 for every model. CQR on 2023 barely moves seasonal naive (Q = 0 in three groups) because 2023 errors were smaller (this is reported).
  - The rolling 12-week method reaches 0.7930–0.8220.
  - Chronos-2 rolling starts at 2024-03-25 (84 origins uncalibrated, `conformal.json → origins_without_full_trailing_window`), so its raw/rolling comparison mixes calibration with season (fix 2).
  - LGBM "other" over-covers (0.8446). This is reported.
  - Chronos-2 raw y = 0 coverage is 0.4256 / 0.2803: q10 > 0 on hours with no pickups. Worth a sentence in the report.
- **Pre-registration:** the primary-window rule and the F2b week (`models.f2b.week_start: 2024-10-13`) were both committed in `4ea6115`, before LGBM 2024 forecasts existed. F2b is not cherry-picked in its favour: 131/168 = 0.780 in that week vs 0.7532 CBD raw coverage for the year, so it is mildly favourable at most.
- **Refit early stopping:** q0.5 rounds range from 61 to 5610 (`lgbm_refits.csv`). The last 4 weeks of each training window are never boosted on. Both points are recorded (DECISIONS line 155). Phase 3 must state which refit is "frozen" and its rounds.
- **Stale forecast risk:** the forecast parquets (`data/forecasts/`) post-date the last edit of the model, feature and engine code (mtimes checked). The evaluation fingerprints its own code but not the model code that produced the forecasts. Acceptable now; note it if model code changes.

## Figures

**F2_model_comparison.png**
- Good: axis labels "WAPE" (unitless ratio); bars start at 0; each panel has its own scale, and the note says so; y tick labels replace a legend; baselines are grey and LGBM uses the model blue.
- Defect: the title says "Chronos-2 (future weather) lowest across modeled zones (0.165 …)". Both Chronos-2 bars read 0.165 at 3 dp, and in the Manhattan non-CBD panel LGBM and Chronos-2 (future) both read 0.151 although LGBM is lower. The claimed ranking cannot be seen in the figure, and "across" reads as "in every group", which is false.
- Defect: a large empty band between the suptitle and the panel titles (about 0.7 in at 10 in width).
- Defect: the Chronos-2 oranges (`#eb6834`, `#f4a582`) are hex literals in `viz/figures.py:200-201`, outside `PALETTE`. This contradicts DECISIONS line 57.

**F2b_fan_chart.png**
- Good: y label has units ("Pickups per hour, Midtown Center"); the x label states the origin; the raw band is shaded and the conformal band dashed; the legend does not cover data (22 % headroom); the actual series is near-black per the palette. No policy line is needed (Oct 2024 axis; `policy_line` correctly draws nothing).
- Acceptable: a 4-entry legend instead of direct labels.

## Decisions check

Missing or incomplete lines:
1. F2b zone (busiest CBD zone of 2024, `04b_evaluate.py:201`) and week `2024-10-13` (`config/project.yaml models.f2b`). Only a config comment exists.
2. LGBM grid values (`learning_rate [0.05, 0.1]`, `num_leaves [31, 127]`, `min_data_in_leaf [20, 200]`) and fixed params `feature_fraction 0.9`, `bagging_fraction 0.8`, `bagging_freq 1`. There is no line giving the reason for these values. `max_bin 255` is covered by line 155.
3. `HISTORY_DAYS_FOR_FEATURES = 30` is hard-coded in `models/lgbm_quantile.py:30`, not in config and not in DECISIONS. CLAUDE.md requires no hard-coded thresholds.
4. Chronos-2 colours: no line, and they contradict line 57.
5. Primary Chronos-2 variant: line 141 defers it to "a Checkpoint-2 item", but Checkpoint 2 is reviewer-gated with no human stop, so it is currently undecided.

The other Phase-2 constants are covered: `profile_weeks`, `residual_weeks`, `feature_history_days`, refit early-stopping parameters, `tie_relative`, `alpha`, `rolling_weeks`, horizon buckets, `mape_min_y`, context 2048.

## Fix list

1. `scripts/04b_evaluate.py` (`load_unit`): apply the same monotone rearrangement and zero clip to Chronos-2 raw quantiles as `GlobalLGBMQuantile` uses, and record the rule in `DECISIONS.md`. Correct line 144 so it states that crossings are counted (674 test, 345 post), not rejected.
2. `scripts/04b_evaluate.py` → `results/conformal.json` (and `backtest_2024.csv` if convenient): add Chronos-2 raw coverage and width restricted to origins ≥ 2024-03-25. This gives Chronos-2 a matched before/after next to `conformal_rolling_12w`.
3. `scripts/09_figures.py` and `src/taxi_shock/viz/figures.py`:
   - Reword the F2 title to "over all modeled zones".
   - Print bar labels at 4 dp so the ranking is visible.
   - Before naming a single lowest model in a title, write a paired uncertainty for the WAPE gap to `results/`: for example, a block bootstrap over origin days of WAPE(LGBM) − WAPE(each Chronos-2 variant), for all zones and per zone group, written by `scripts/04b_evaluate.py`. Make the title's ranking conditional on that interval excluding 0.
4. `src/taxi_shock/viz/figures.py` (`f2_model_comparison`): remove the empty band between the suptitle and the panel titles.
5. `src/taxi_shock/viz/style.py`: add the Chronos-2 colours to `PALETTE` (one hue plus `tint()` for the second variant), use them in `figures.py`, and add a DECISIONS line.
6. `DECISIONS.md`: add lines for:
   - the F2b zone and week rule, noting that it was fixed in `4ea6115` before any LGBM 2024 forecast existed;
   - the LGBM grid values and the fixed bagging/feature-fraction parameters with reasons;
   - `HISTORY_DAYS_FOR_FEATURES`: move it into `config/project.yaml` or justify it.
7. `DECISIONS.md` (+ config if needed): choose and record the primary Chronos-2 variant for Phases 3 and 5 with a stated rule. Checkpoint 2 is reviewer-gated, so this cannot wait for Stanley.
8. `tests/test_leakage.py`: add a case that poisons the exog table (weather and `is_holiday`) for every hour ≥ origin + 1 day and asserts identical forecasts. Rewrite the docstring to state the one by-design exception: observed weather over the target day, a PLAN limitation.
9. `scripts/04_backtest.py`: write the ETS fallback count (`ETSDailyProfile.fallbacks_`) per window and period to a results file, such as a `results/stat_runs.csv` row like `lgbm_refits.csv`. DECISIONS line 148 promises it is "counted", but the count exists only in a log.
10. `config/phase_outputs.yaml`, phase 2: add `results/conformal.json`, `forecast_summary.json`, `lgbm_params.json`, `lgbm_tuning.csv`, `lgbm_refits.csv`, `fan_chart_f2b.csv` and `figure_stats_phase2.json`. The coverage claims and the F2/F2b titles depend on them.
11. `README.md`: update the stale `figures` row ("Phase 1: F1, F1b") and the setup example `make verify PHASE=1`.
12. `DECISIONS.md` line 158: the medians are 2922.5 (q0.5) and 902.5 (q0.9) in `results/lgbm_refits.csv`. Quote them exactly.

## Escalation reasons

None.
- Every model beats SeasonalNaive.
- No mandatory item was skipped. StatBaseline, Chronos-2 with daily origins, and conformal calibration all exist.
- The construction of the AutoETS baseline is a recorded deviation from the literal spec, and it is evidence-based.
- Chronos-2 zero-shot beating the tuned LGBM by a small margin is a finding to report in the PASS summary, not a storyline contradiction.

## Amendments made

None.
