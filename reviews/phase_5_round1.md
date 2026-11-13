# Phase 5 review — how the system should adapt

Reviewer: phase-reviewer subagent (fresh context), 2026-11-13. Phase commit reviewed: aba8ccb. HEAD at review time was e23143b (a Phase-7 WIP commit on top of it). The working tree also had uncommitted Builder edits to `DECISIONS.md` and `reports/analysis.md` (Phase 7 work, made while this review ran). Where the text of `reports/analysis.md` §5 changed between aba8ccb and the working tree, both versions are noted.

## Verdict

**FIX.** The pipeline is sound:
- All four strategies are scored on identical evaluation sets: `n` is equal across strategies in every cell of `results/adaptation.csv`, with 1,500,298 zone-hours over all zones.
- The S0 and S4 WAPEs reproduce exactly from the Phase-3 file `results/shock_errors.csv` (0.1643 and 0.1649).
- Leakage tests are real and green.
- Every Phase-5 number in the report, README, F5 title and DECISIONS traces to a results file.

The figure and the recommendation still have defects:
- F5 is not on the Phase-3 axes and has no policy line.
- The recommendation paragraph contains one false claim and one mislabelled cost.
- The S1-vs-S0 gap, on which the recommendation rests, mixes the retraining effect with the training-window effect.
- No seasonal-naive reference is reported for 2025–26.
- The MASE scale window is described wrongly.

None of these needs a human decision. The pre-registered D6 expectation failed (S6 does not remove the bias). That is a finding, reported as found with no tuning afterwards (DECISIONS line 271), so it is not an escalation.

## DoD table

Scope: PLAN Phase 5 as re-scoped by Amendment 4 D6 and Amendment 5 ("Go-ahead: Phase 5 (D6: S0, S1, S4, S6)"; "No S3"). Dropping S2, S3 and S5 is human-approved, not a Builder downgrade.

| Item | Status | Evidence |
|---|---|---|
| Strategies S0, S1, S4, S6 (Amendment 4 D6 / Amendment 5) | MET | `config/project.yaml → adapt.strategies`; `scripts/08_adapt.py`. S0 = `data/forecasts/frozen/lgbm_quantile.parquet`, with `results/frozen_model.json` train_end 2024-12-31 23:00. S1/S6 have 23 monthly refits each, on a sliding 731/730-day window (`results/adaptation_refits.csv`). S4 = Chronos-2 `weather_past`. |
| Evaluation window 2025-02 → 2026-09 | MET | `adaptation_summary.json → eval_window` 2025-02-01 → 2026-09-30, 607 days (`adaptation_gaps.csv n_days`) |
| Same metrics as Phase 2 | PARTIAL | WAPE, MAE, MASE, bias, pinball q10/q50/q90, coverage_80 and width_80 are present. Each is given raw and with rolling-12w conformal calibration, by zone group, horizon bucket (h01–06…h19–24) and subset (all / y_zero / y_pos). Two gaps: (a) no SeasonalNaive reference row, although Phase 2's DoD compares every model against it; (b) the MASE scale window is not what it claims to be (see Method sanity 4). |
| WAPE and coverage per strategy × zone group × quarter | MET | `results/adaptation.csv`, `period` ∈ 2025Q1…2026Q3 at horizon_bucket=all. Note: 2025Q1 covers Feb–Mar only and is not labelled as such. |
| Error-recovery curve: rolling 4-week WAPE, CBD, on the Phase-3 axes | PARTIAL | F5 top-left panel shows rolling 28-day CBD WAPE. Its x-axis starts 2025-02-28, not on the Phase-3 axes (2024-07-01 → 2026-09-30). It therefore has no pre-shock reference and no policy line, so it cannot show "recovery". |
| Output `results/adaptation.csv` | MET | 13,440 rows |
| Output `reports/figures/F5_adaptation.png` | MET (renders), defects below | 2024×1223 px, 200 dpi, plus SVG |
| One paragraph recommending a strategy, with retraining cost vs gain | PARTIAL | `reports/analysis.md` §5 "Recommendation for the forecasting system" recommends S1 and cites `adaptation_summary.json → retrain_cost`. Problems: (i) "Chronos-2 … buys no accuracy over S1 except in the outer boroughs" is false: at airports S4 is distinguishably ahead of S1 (0.1749 vs 0.1790, gap −0.0041 [−0.0083, −0.000008], `adaptation_gaps.csv`). (ii) "One refit costs a median of 411 s" is wrong: 411.1 s is `wall_seconds`, which is refit plus a month of daily forecasts; the refit alone (`seconds`) has a median of 384.2 s. (iii) At aba8ccb the paragraph said the gain is "consistent". It is not: S0 beats S1 in 2025Q1 over all zones (0.1623 vs 0.1639) and in the CBD (0.1550 vs 0.1568). The uncommitted working-tree text already corrects this ("not in every quarter (S0 is ahead in 2025-Q1)"); it must be committed. |

## Test output

- `ruff check .` → `All checks passed!`
- `make verify PHASE=5` → exit 0, runtime 1m31s:
  - ruff PASS
  - pytest PASS (all dots; 0 skipped)
  - no_skips PASS
  - dbt_test PASS (`PASS=62 WARN=0 ERROR=0 SKIP=0`)
  - outputs PASS (all 7 files in `config/phase_outputs.yaml → 5` exist and are non-empty)
- `pytest -q tests/test_leakage.py tests/test_phase6.py::test_channel_features_use_only_previous_days` → 24 passed.
- Warnings are pyfixest/pandas `inplace` deprecations only.

## Number trace

All numbers below were checked against the files named. Report = `reports/analysis.md` §5 and the executive summary item 4; README lines 19–21 and 89; F5 title; DECISIONS lines 269–272.

| Number (where) | Source | OK |
|---|---|---|
| WAPE all: S0 0.164, S1 0.162, S4 0.165, S6 0.168 (report table, exec. summary, README) | `adaptation_summary.json → headline.*|all.wape` (0.16433, 0.16201, 0.16485, 0.16775) | yes |
| WAPE CBD 0.154 / 0.151 / 0.154 / 0.157 | `headline.*|cbd.wape` | yes |
| Bias −2.3 / −1.7 / −2.0 / −2.9 % (table, exec. summary, F5 title) | `bias_pct_of_pickups.*|all` | yes |
| Coverage 0.81 / 0.80 / 0.80 / 0.80; "0.80–0.81" | `headline.*|all.coverage_80` (0.8122, 0.8045, 0.7995, 0.8027) | yes |
| Raw coverage "0.74–0.78" | `adaptation.csv` raw coverage_80 all/all/all: 0.7441 (S4) … 0.7821 (S0) | yes |
| S1 vs S0: 0.23 pp all, 0.29 pp CBD, both CIs exclude 0 | `adaptation_gaps.csv` all s1/s0 −0.002322 [−0.00361, −0.000864]; cbd −0.002895 [−0.004349, −0.001379] | yes |
| Manhattan non-CBD S1 vs S0 not distinguishable | gaps −0.000892 [−0.00229, 0.000556] | yes |
| S4 vs S0/S1 all not distinguishable | gaps 0.00052 [−0.0022, 0.0035]; 0.00284 [−0.000066, 0.0059] | yes |
| S4 outer boroughs 0.395 vs 0.412 | `headline.s4|other` 0.39503, `s0|other` 0.41192 | yes |
| S4 Manhattan non-CBD 0.147 vs 0.142, distinguishable | gaps 0.004933 [0.00166, 0.00848] | yes |
| S6 distinguishably worse than S0 and S1 (all, CBD) | gaps all 0.00342 [0.00119, 0.00602]; cbd 0.002596 [0.000216, 0.00512]; vs S1 both > 0 | yes |
| 2026-Q1 WAPE 0.187–0.191 | `adaptation.csv` raw wape all/2026Q1: 0.1869, 0.1868, 0.1883, 0.1908 | yes |
| F5 title 16.2% / 16.4% / −2.9% / −2.3% / +0.3 pp | `figure_stats_phase5.json` (gap_vs_s0_all.s6 0.00342) | yes |
| Median refit 411 s, 23 refits | `retrain_cost.s1` wall_seconds_median 411.1, n_refits 23 | number yes, **label wrong** (see DoD) |
| Chronos median 250 s per month on an L4 | `retrain_cost.s4` 249.8, hardware "NVIDIA L4" (from `chronos_run.json → environment.gpu`) | yes |
| README "166.1 / 137.4 min" | `adaptation_refits.csv` wall_seconds sums 9964.5 / 8242.8 s (`runtimes.json → adaptation_refits`) | yes |
| "Chronos-2 … buys no accuracy over S1 except in the outer boroughs" | contradicted by `adaptation_gaps.csv` airports s4/s1 | **NO** |
| "the gain over the frozen model is small but consistent" (aba8ccb) | contradicted by `adaptation.csv` 2025Q1 | **NO** (fixed in working tree, uncommitted) |
| Commit message aba8ccb | no numbers | n/a |

## Method sanity

1. **Leakage.** `tests/test_leakage.py` poisons every pickup at or after the origin (1e6 and NaN) and asserts bit-identical forecasts for SeasonalNaive, ETS and LightGBM, with and without early stopping. It includes power checks and is not a placeholder. `tests/test_phase6.py::test_channel_features_use_only_previous_days` poisons the channel table from day D and checks that the S6 features for day D are unchanged. It tests the helper only. No test runs `GlobalLGBMQuantile(extra=…)` end to end through `run_backtest` with a poisoned channel table.
2. **Short lags.** `grep lag_1|shift(1)|rolling(4)`:
   - `src/taxi_shock/adapt.py:30–36` and `features.py:65–78` use `shift(1)` on **daily**, date-reindexed frames, i.e. 1 day = 24 h, which is ≥ min_lag for a 00:00 origin. OK.
   - No `lag_1` or `rolling(4)` anywhere.
3. **Identical evaluation sets.** `n` has one unique value per (group, bucket, subset, period, metric) across strategies, and `n_missing_forecast` = 0 everywhere.
   - 1,500,298 = 607 days × 24 h × 103 zones − 2 spring-forward hours × 103. This is consistent.
   - S0 and S4 WAPE over the window match the Phase-3 `shock_errors.csv` daily rows to 4 d.p.
4. **MASE scale is not the stated window.**
   - `adaptation_summary.json → mase_scale` and DECISIONS line 269 say the scale is the seasonal-naive MAE "2022-01-01 → 2024-12-31".
   - `evaluate_all` computes it from the panel returned by `load_inputs`, which starts at `run_start − 24 months − feature_history_days` = 2022-09-27. Residuals therefore start 2022-10-04, and `res[res.hour_ts >= model_start]` is a no-op.
   - Rankings are unaffected (the scale is common to all strategies), but the recorded claim is false.
5. **S1 vs S0 mixes two changes.** S1 differs from S0 in refit frequency (monthly vs once) **and** in training window (sliding 24 m vs expanding from 2022-01-01).
   - Phase 2 already measured a window effect in 2024 with both on monthly refits: LightGBM WAPE all zones sliding_24m 0.1664 vs expanding 0.1675 (`results/forecast_summary.json → wape_by_zone_group`). That is 0.11 pp, about half of the 0.23 pp S1–S0 gap.
   - The recommendation "retrain monthly" attributes the whole gap to retraining. That is not supported until an expanding-window monthly refit is run or the confound is stated.
6. **No naive reference.** No 2025–26 SeasonalNaive row in `adaptation.csv` or in the report table.
   - The number exists: seasonal naive (frozen), 2025-02-01 → 2026-09-30, WAPE 0.2370 over all zones, computed by me from `results/shock_errors.csv` window_days = 1 rows. So every strategy beats it by about 7 pp.
   - It must be reported, not left implicit. MASE > 1 over all zones (1.28–1.31) will otherwise read as "worse than naive". It is not: the MASE scale is in-sample 2022–24 and post-2025 outer-borough demand grew.
7. **S0 intervals are not frozen.** The "frozen" S0 has rolling 12-week conformal calibration, so its intervals adapt even though its point forecasts do not. The report table header says "rolling conformal" but never states that this is an adaptation applied to S0 as well. Raw S0 coverage is 0.782; calibrated it is 0.812.
8. **Pre-registered expectation.** The D6 expectation "S6 removes most of the post-2025 bias" failed: S6 bias −2.9% vs S0 −2.3%. This is reported as found, with no tuning afterwards. Good.

## Figures

`reports/figures/F5_adaptation.png` (10.1 × 6.1 in, small-multiples size):
- **No policy line, and not on the Phase-3 axes.** PLAN Phase 5 asks for the recovery curve "on the Phase-3 axes" (2024-07-01 → 2026-09-30). PLAN §7 asks for `policy_line` on every time axis.
  - `f5_adaptation` never calls `policy_line`, and the data start 2025-02-01, so the helper would skip it anyway.
  - The forecasts needed exist: S0 from 2024-07, S4 from 2024-01, S1/S6 from 2024-11 (`adapt.run_start`). Only `adaptation_daily.csv` is cut at the evaluation window.
- **Title.** "After congestion pricing, …" anchors the period to the policy. Under Amendment 5, Phase 5 is "forecasting through the shift" (app dispatch), and Phase 3 found no CBD-specific break. Opening with the policy invites the causal reading Amendment 5 forbids. State the date range instead. The title also wraps to three lines; shorten it.
- **Colour.** S0 is drawn in `PALETTE["non_cbd"]` (#8A8F98) inside a panel titled "CBD zones", which reuses the non-CBD semantic colour for a strategy. Use `PALETTE["baseline"]` for the frozen reference, or record why not.
- **Otherwise fine.**
  - Axis labels carry units ("WAPE, 4-week (%)", "Bias, 4-week (%)").
  - Direct labels are used, with no legend.
  - The zero line is on the bias panels.
  - The WAPE y-axes are not zero-based, which is acceptable for line plots of a rate.
  - Readable at 7 in.

## Decisions check

| Rule in code | DECISIONS line | Status |
|---|---|---|
| `adapt.run_start` 2024-11-01 (12-week conformal warm-up) | 269 | OK |
| `adapt.window` sliding_24m | 269 | OK |
| `adapt.scale_end`, common MASE scale | 269 | **wrong start date** (see Method sanity 4) |
| `adapt.rolling_days` 28 | PLAN ("rolling 4-week") | OK |
| S6 windows 7 d / 28 d zone, 7 d citywide | 269 | documented, but **hard-coded** in `src/taxi_shock/adapt.py` (CLAUDE.md: no thresholds in code) |
| S6 features NaN until the window is fully covered (`min_periods=k`); missing zone-days filled with 0 app / 0 total | none | **missing** |
| S4 primary variant `weather_past` | 269 | OK |
| Bias % definition, cost sources | 270 | OK |
| Bootstrap 2,000 reps, 7-day blocks | 269 | OK |
| Quarter assigned by origin date; 2025Q1 = Feb–Mar only | none | **missing** |
| S0 receives rolling conformal (intervals adapt, point frozen) | none | **missing** |
| `retrain_cost` hardware string "local CPU, 12 cores" | none | hard-coded literal; should come from `results/machine_resources.json` |

## Fix list

1. In `src/taxi_shock/viz/figures.py::f5_adaptation`, `scripts/09_figures.py::phase5` and `scripts/08_adapt.py::evaluate_all`, put F5 on the Phase-3 axes (2024-07-01 → 2026-09-30) with `policy_line` on every panel. Write daily errors for each strategy from its first available origin (S0 2024-07-01, S4 2024-07-01, S1/S6 2024-11-01) to a separate pre-window file or column, and shade or mark the evaluation window start (2025-02-01). Keep all metrics on the 2025-02-01 window.
2. In `scripts/09_figures.py::phase5`, replace "After congestion pricing" in the F5 title with the date range ("Feb 2025 – Sep 2026"), shorten the title to at most two lines, and draw S0 in `PALETTE["baseline"]` (or record the colour choice in `DECISIONS.md`).
3. In `reports/analysis.md` §5 (recommendation paragraph), correct "buys no accuracy over S1 except in the outer boroughs": S4 is also distinguishably ahead at airports (0.1749 vs 0.1790, `adaptation_gaps.csv`). Correct "One refit costs a median of 411 s" to say 411 s is a month of S1 (refit plus daily forecasts) and that the refit alone has a median of 384.2 s (`adaptation_refits.csv → seconds`). Add `seconds_median` to `retrain_cost` in `scripts/08_adapt.py` so the number has a results source. Commit the already-drafted "not in every quarter (S0 is ahead in 2025-Q1)" correction.
4. In `scripts/08_adapt.py`, separate retraining from the window change. Preferred: run S1 with `window: expanding` as a labelled sensitivity (`s1e`, monthly refits, same run_start) and add it to `adaptation.csv` / `adaptation_gaps.csv`. If that run is not done, `reports/analysis.md` §5 must state that S1 changes both refit frequency and window, quote the Phase-2 window gap (0.1664 vs 0.1675, `forecast_summary.json`), and drop the attribution of the S1–S0 gap to retraining alone. Record the choice in `DECISIONS.md`.
5. In `scripts/08_adapt.py::evaluate_all`, compute the MASE scale over `data.model_start` → `adapt.scale_end` as recorded: load the panel from `model_start − 7 days` for the scale. Regenerate `adaptation.csv` and `adaptation_summary.json`. Otherwise, correct the `mase_scale` string and DECISIONS line 269 to the actual 2022-10-04 → 2024-12-31 window.
6. In `scripts/08_adapt.py`, add a SeasonalNaive reference (the frozen Phase-3 seasonal naive, or the lag-168 naive) to `adaptation.csv`, the daily file and `adaptation_gaps.csv`, with the same metrics. Add its WAPE row to the §5 table in `reports/analysis.md`.
7. In `config/project.yaml` (`adapt.channel_windows_days`, `adapt.city_window_days`) and `src/taxi_shock/adapt.py`, move the 7/28/7-day channel windows out of code.
8. In `DECISIONS.md`, add lines for: S6 features are NaN until the window is fully covered and missing zone-days count as 0 app / 0 total; quarters are assigned by origin date and 2025Q1 covers 2025-02-01 → 03-31 only; S0's intervals are recalibrated by the rolling 12-week conformal (point forecasts frozen, intervals adaptive), with raw S0 coverage 0.782 → calibrated 0.812 (`adaptation.csv`). State the 2025Q1 coverage in the `reports/analysis.md` §5 table note as well.
9. In `tests/test_phase6.py` (or a new `tests/test_adapt.py`), add an end-to-end S6 leakage test: build `GlobalLGBMQuantile(..., extra=channel_feature_fn(channel_table(d)), extra_cols=CHANNEL_FEATURES)` on the synthetic panel, run `run_backtest` for one origin with the channel table clean and with it poisoned from the origin day on, and assert identical forecasts. Add a power check that poisoning earlier days changes them.
10. In `scripts/08_adapt.py::retrain_cost`, read the hardware description from `results/machine_resources.json` instead of the literal "local CPU, 12 cores".

## Escalation reasons

None.

## Amendments made

None. PLAN already specifies the Phase-3 axes for F5, and the S1 window (sliding 24 m) stays as written. Fix 4 adds a sensitivity run; it does not change S1.
