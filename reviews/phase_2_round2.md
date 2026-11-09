# Phase 2 review, round 2: probabilistic forecasting before the shock

Reviewer: phase-reviewer subagent, fresh context, 2026-11-09. Commit under review: `948e073` (fix round 1).
Round-1 review kept as `reviews/phase_2_round1.md`.

## Verdict

**FIX** (fix round 2 of 2)

All DoD items are met, the tests are green, and every number I traced reproduces from the forecast files. Eleven of the twelve round-1 fixes are done cleanly. The one figure fix (F2 title ranking) introduced a new defect: the title quotes a WAPE range that contains a model it leaves out, and the model it leaves out is the primary Chronos-2 variant. One small cross-reference and two missing tests remain. No escalation trigger was found.

## DoD table

| # | Item (PLAN Phase 2) | Status | Evidence |
|---|---|---|---|
| 1 | Every model beats or is compared with `SeasonalNaive` using a number | MET | `results/forecast_summary.json → wape_relative_to_seasonal_naive_expanding`: LGBM 0.6946, AutoETS 0.7649, Chronos-2 0.6823 (future) / 0.6851 (past), all zones. Values exist for each zone group, and all are < 1. Paired intervals vs the best model are in `results/wape_gap_bootstrap.csv`. Seasonal naive gap over all zones: 0.076612 [0.060592, 0.096212]. |
| 2 | Coverage reported | MET | `coverage_80` and `width_80` exist for every model × window × calibration × group × bucket × subset (`results/backtest_2024.csv`, 16,800 rows). Before/after values are in `results/conformal.json`. Chronos-2 now has a matched before/after: `raw_rolling_origins` 0.7142 / 0.6976 vs rolling 0.7932 / 0.7930 on the same 697,104 rows. |
| 3 | `tests/test_leakage.py` poisons the future and asserts unchanged predictions | MET | 23/23 pass alone. Future pickups are set to 1e6 and to NaN, for 4 factories × 3 origins. A past-poisoning power check runs for each factory. New: exog (weather, `is_holiday`) is poisoned from origin + 1 d for LGBM with fixed rounds and with early stopping. A target-day weather power check documents the by-design exception. |
| 4 | WAPE, MASE, pinball per quantile, 80% coverage, width per zone group and horizon bucket; y = 0 handled | MET | `backtest_2024.csv` metrics: `wape, mase, pinball_q10/q50/q90, coverage_80, width_80, bias, mae, n_missing_forecast`. Groups: all, cbd, manhattan_non_cbd, airports, other. Buckets h01-06 … h19-24. Subsets all / y_pos / y_zero. |
| 5 | Both windows reported, primary chosen in DECISIONS | MET | `forecast_summary.json → primary_window`: 2.4228 vs 2.4163, below the 1% tie threshold, so expanding. The rule was pre-registered (DECISIONS P2 lines 147, 163). |
| 6 | Daily origins, monthly refit | MET | `results/lgbm_refits.csv` (36 refits); `results/stat_runs.csv` (12 refits per run). |
| 7 | StatBaseline mandatory | MET | AutoETS daily × profile. `results/stat_runs.csv`: 1236 zone fits per run, 0 failed fits, 0 fallbacks (round-1 fix 9 done). |
| 8 | LGBM small grid on 2023, grid recorded | MET | `results/lgbm_tuning.csv`, `results/lgbm_params.json`. Grid and fixed parameters are justified in DECISIONS line 174. |
| 9 | Chronos-2 zero-shot, 2048 h, daily origins, Colab | MET | `results/chronos_run.json`; `results/chronos_import_check.json` (`passed: true`). Primary variant `weather_past` is set by a specification rule (DECISIONS line 168, `chronos.primary_variant`). |
| 10 | Split-conformal on 2023 residuals per zone group; before/after for every interval model | MET | `conformal_2023` covers all trained models. The primary is `conformal_rolling_12w` (human-approved amendment). Chronos-2 is uncalibrated on 2023 (no 2023 forecasts) and this is stated. The matched raw label is described in `conformal.json → matched_raw_label`. |
| 11 | Modeled zones and share of non-modeled pickups | MET | `results/modeled_zones.json` 0.990412 / 0.009588; README. |
| 12 | README task definition word for word | MET | `README.md → Forecasting task`. |
| 13 | Outputs `backtest_2024.csv`, F2, F2b | MET | `make verify PHASE=2`: 17/17 listed outputs present (round-1 fix 10 done). |

## Test output

`make verify PHASE=2` took 56 s and exited 0:
```
ruff       PASS   (All checks passed!)
pytest     PASS   (92 passed, 0 skipped)
no_skips   PASS
dbt_test   PASS   (PASS=47 WARN=0 ERROR=0 SKIP=0, full warehouse)
outputs    PASS   (17 phase-2 files)
```
- `pytest -rA tests/test_leakage.py`: 23 passed.
- `ruff check .`: All checks passed.
- Reproducibility:
  - `python scripts/04b_evaluate.py` skipped all 8 units and reassembled.
  - `make figures` regenerated every figure.
  - `git status` afterwards showed only the `generated_utc` timestamps in `conformal.json` / `forecast_summary.json` changed (reverted by me). Every CSV, PNG and SVG was byte-identical.
- `backtest_2024.csv` at `df9c541` vs `948e073`:
  - Only Chronos-2 rows changed (from the sort/clip fix).
  - All trained-model rows are identical, which confirms the AutoETS rerun reproduced its forecasts.
  - There are 1,400 new `raw_rolling_origins` rows.

## Number trace

Independent recomputation by the reviewer from `data/forecasts/lgbm_quantile__expanding__test.parquet` and `results/chronos_forecasts.parquet`, with sorting and clipping applied:

| Number | Where | Source | Recomputed | OK |
|---|---|---|---|---|
| 0.1645 / 0.1652 / 0.1675 / 0.1844 / 0.2411 | F2 title and bars, DECISIONS 164 | `forecast_summary.json`, `backtest_2024.csv` | 0.164528 / 0.165208 / 0.16749 | yes |
| raw coverage 0.7121 / 0.6919 / 0.7808 | DECISIONS 164 | `forecast_summary.json → coverage_80_all_zones` | 0.7121 / 0.6919 / 0.7808 | yes |
| 0.7142 / 0.6976 (`raw_rolling_origins`), n = 697,104 | DECISIONS 164, 170 | `backtest_2024.csv`, `conformal.json` | 0.7142 / 0.6976, 697,104 rows | yes |
| 0.7930–0.8220, 0.8446 | DECISIONS 164 | `forecast_summary.json`, `conformal.json` line 876 | – | yes |
| mean pinball 2.3269, 2.4228, 2.4163 | DECISIONS 163, 164 | `forecast_summary.json` | – | yes |
| gap 0.002962 [−0.000037, 0.005887]; 0.000679 [0.000147, 0.001211]; CBD 0.004162 [0.000963, 0.007067] | DECISIONS 178 | `wape_gap_bootstrap.csv` | gap 0.0029618. My own block bootstrap gave [−0.00015, 0.00583], and a circular moving-block bootstrap gave [−0.00032, 0.00626]. The tie conclusion is robust. | yes |
| 674 / 345 crossing rows | DECISIONS 144 | `chronos_import_check.json` | – | yes |
| 0.0007 WAPE between variants | DECISIONS 168 | `wape_gap_bootstrap.csv` 0.000679 | – | yes |
| 12 × 103 = 1236, 0, 0 | DECISIONS 178(b) | `stat_runs.csv` | – | yes |
| 2922.5 / 902.5 | DECISIONS 158 | `lgbm_refits.csv` | – | yes (round-1 fix 12 done) |
| 131 of 168, 2024-10-13, Midtown Center | F2b title | `figure_stats_phase2.json` | – | yes |
| 103, 99.04%, 0.990412; 48%, 0.4816/0.4635/0.4488 | README | `modeled_zones.json`, `citywide_yearly.csv` | – | yes |
| Commit message `948e073` | – | contains no numbers | – | n/a |

No untraceable numbers. `reports/analysis.md` does not exist yet (Phase 7).

## Method sanity

- **Short lags:** none. A grep for `lag_1`, `shift(1)` and `rolling(4)` over `src/ scripts/ dbt/models` finds only `features.py:65,66,78`. Those are `.shift(1)` on **date-indexed** matrices, a 1-day shift, which is correct.
- **Horizon index:** `horizon` is in `CALENDAR_FEATURES` and therefore in the LGBM feature set.
- **Leakage:** the test is real (see DoD 3). The exogenous path is now covered, and the by-design exception (observed weather over the target day) is stated in the docstring and power-checked. This closes round-1 fix 8.
- **Chronos-2 post-processing (round-1 fix 1):** `04b_evaluate.py load_unit` sorts per row, clips at 0 and sets point = q50, the same as LGBM. The effect is tiny (all-zone WAPE 0.164530 → 0.164528), as predicted in round 1.
- **SeasonalNaive comparison:** every model beats naive in every zone group. Every naive gap interval excludes 0 (`wape_gap_bootstrap.csv`).
- **Ranking:** over all zones, Chronos-2 (future weather) has the lowest point WAPE. LightGBM is not distinguishable from it. I also ran LightGBM vs the primary `weather_past` variant, which the evaluation does not compute (reviewer check, not a project result):
  - all zones: gap 0.002283 [−0.000874, 0.005286], also tied;
  - CBD: 0.003515 [0.000155, 0.006545], Chronos better;
  - Manhattan non-CBD: −0.001345 [−0.005077, 0.00215], tied.
  - The honest top tier over all zones is therefore all three of LightGBM and both Chronos-2 variants. This matters for fix 1.
- **Bootstrap design:** paired, 7-day non-overlapping blocks, per-model denominators, seed from config. The tie rule is pairwise against the best model only, so it cannot say whether two non-best models are tied (see fix 1). The best model is selected on the same sample (a mild selection effect). This is acceptable for a title rule.
- **Calibration:**
  - Raw coverage is below 0.80 for every model.
  - Rolling 12-week calibration gives 0.7930–0.8220.
  - Over-coverage in LGBM "other" zones (0.8446) is reported.
  - Chronos-2 before/after is now on matched rows.
- **Primary Chronos variant:** `weather_past`, chosen by the specification rule, not by results (DECISIONS 168). This is sound.
- **Carried to Phase 3 (no action now):**
  - `scripts/04_backtest.py --full` now skips any existing forecast file by existence alone. Unlike `04b_evaluate.py`, it uses no code/config fingerprint. If model code changes, `make forecast` would silently reuse stale forecasts. The current files are not stale: only the `GlobalLGBMQuantile` constructor signature changed after they were written, and predict-time behaviour (30 days of history) is unchanged.
  - Phase 3 must name the frozen refit and its rounds (q0.5 rounds range 61–5610 in `lgbm_refits.csv`).

## Figures

**F2_model_comparison.png** (re-rendered this round)
- Fixed since round 1:
  - constrained layout, no empty band under the title;
  - 4-dp bar labels make the ordering readable (e.g. Manhattan non-CBD 0.1507 vs 0.1512);
  - Chronos colours come from `PALETTE["foundation"]` and `tint()`;
  - the note names both sources and the bootstrap.
- Unchanged and fine: x label "WAPE" (a unitless ratio), bars from 0, per-panel scale stated, y tick labels instead of a legend, grey baselines, model blue for LGBM.
- **Defect (fix 1):** the title reads "Chronos-2 (future weather) and LightGBM within bootstrap uncertainty (0.1645-0.1675)".
  - The quoted range contains Chronos-2 (past weather) at 0.1652, which the title omits.
  - It is omitted only because its gap to the *best* model has a tight interval (the two Chronos variants are highly correlated). It is not distinguishable from LightGBM (reviewer check above).
  - A reader will conclude that the past-weather variant, which is the primary variant carried into Phases 3 and 5, falls outside the top tier. The bootstrap does not support that reading.

**F2b_fan_chart.png** (unchanged since round 1)
- Units on the y axis, origin stated on the x axis, raw band shaded, conformal band dashed, near-black actuals.
- The legend sits in the headroom above the data.
- No policy line is needed on a 2024-10 axis.
- The title number is traced.

## Decisions check

All round-1 missing lines are now present:
- F2b rule: line 173
- LGBM grid and fixed parameters: line 174
- `predict_history_days`, moved to config: line 175
- Chronos colours: line 172
- primary Chronos variant: line 168
- bootstrap `block_days` / `bootstrap_reps`: line 171
- matched raw label: line 170
- sort/clip rule: line 169
- `results/*.lock` handling and run records: line 176

No new constant in code lacks a line, except figure padding (`vmax × 1.45`), which is a layout detail.

One wording issue: line 164 says "Chronos-2 is lowest on all zones, CBD … and airports". That is a point-estimate statement written before the bootstrap. Line 178 qualifies it for all zones (LightGBM tied), but line 164 does not point to line 178. A Phase-7 writer quoting line 164 would overclaim (fix 2).

## Fix list

1. `scripts/09_figures.py` (`phase2`), and `scripts/04b_evaluate.py` if needed: make the F2 title consistent with the bootstrap. Use one of these:
   - (a) name the best model and the models not distinguishable from it, without a min–max range that includes an unlisted model, e.g. "Chronos-2 (future weather) lowest at 0.1645; LightGBM (0.1675) not distinguishable";
   - (b) compute pairwise gap intervals among all non-baseline candidates in `wape_gap_bootstrap.csv` (or a sibling file), and list every model that is not distinguishable from the best or from any listed model.

   Record the chosen wording rule in `DECISIONS.md` (amend line 171). The title must not make the primary `weather_past` variant look excluded unless an interval written to `results/` shows it.
2. `DECISIONS.md` line 164: add "point estimates; with paired bootstrap intervals (line 178) LightGBM is not distinguishable from Chronos-2 over all zones" after the ranking sentence.
3. `tests/` (e.g. a new `tests/test_evaluate.py`):
   - Test `wape_gap_bootstrap` (via `daily_errors`) on synthetic daily errors. Two identical models must come out tied. A model with uniformly larger errors must not be tied. The `wape` column must equal sum |e| / sum y.
   - Test that the Chronos-2 post-processing in `load_unit` sorts crossed quantiles and clips negatives.

   These two code paths gate a figure title and the Chronos metrics, and neither has a test.

## Escalation reasons

None.
- No mandatory item was downgraded.
- Every model beats SeasonalNaive.
- Chronos-2 zero-shot matching or slightly beating LightGBM is a finding, not a contradiction of the storyline. It should go into Stanley's PASS summary, with the bootstrap tie stated.

## Amendments made

None.
