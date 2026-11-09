# Phase 2 review, round 3: probabilistic forecasting before the shock

Reviewer: phase-reviewer subagent, fresh context, 2026-11-09. Commit under review: `6d45047` (fix round 2).
Earlier rounds: `reviews/phase_2_round1.md`, `reviews/phase_2_round2.md`.

## Verdict

**PASS**

- Every DoD item is met and all tests pass.
- All three round-2 fixes are done:
  - The F2 title now follows a stated pairwise rule and quotes no range.
  - DECISIONS line 164 points to the bootstrap qualification.
  - `taxi_shock.evaluation` has unit tests.
- I recomputed every number I checked from the forecast files, and they reproduce.
- The minor observations below do not block the phase.

## DoD table

| # | Item (PLAN Phase 2) | Status | Evidence |
|---|---|---|---|
| 1 | Every model beats or is compared with `SeasonalNaive` using a number | MET | `results/forecast_summary.json → wape_relative_to_seasonal_naive_expanding`. Pairwise gaps with 95% intervals are in `results/wape_gap_bootstrap.csv`. Seasonal naive is worse than every model in every group, and each interval excludes 0. Example: LGBM − naive over all zones is −0.07365 [−0.093145, −0.057975]. |
| 2 | Coverage reported | MET | `coverage_80` and `width_80` exist for every model × window × calibration × zone group × horizon bucket × subset (`results/backtest_2024.csv`, 16,800 rows). |
| 3 | `tests/test_leakage.py` poisons the future and asserts unchanged predictions | MET | 23/23 pass when run alone. Future pickups are set to 1e6 and to NaN for 4 factories × 3 origins. A past-poisoning power check runs for each factory. Exog is poisoned from origin + 1 d, and a target-day weather power check is included. Chronos inputs are covered by `tests/test_chronos_inputs.py`. |
| 4 | WAPE, MASE, pinball q10/q50/q90, 80% coverage and width per zone group (CBD, Manhattan non-CBD, airports, other) and horizon bucket; y = 0 handled explicitly | MET | `backtest_2024.csv` metrics: wape, mase, pinball_q10/q50/q90, coverage_80, width_80, bias, mae, n_missing_forecast. Subsets: all / y_pos / y_zero. MAPE is not reported. |
| 5 | Both windows reported; primary chosen in DECISIONS | MET | `forecast_summary.json → primary_window`: 2.4228 vs 2.4163, a 0.27% difference, so `expanding` wins under the pre-registered rule (DECISIONS lines 147, 163). |
| 6 | Rolling origin, daily origins, monthly refit | MET | `results/lgbm_refits.csv` (36 refits). `results/stat_runs.csv` (12 refits × 103 zones). The LGBM test file has origins 2024-01-01 → 2024-12-31 for 103 zones (904,649 rows). |
| 7 | StatBaseline (mandatory) | MET | AutoETS daily × hourly profile, with 0 failed fits and 0 fallbacks (`stat_runs.csv`). |
| 8 | LGBM small grid on 2023, grid recorded | MET | `results/lgbm_tuning.csv`, `results/lgbm_params.json`, DECISIONS line 174. |
| 9 | Chronos-2 zero-shot, 2048 h context, daily origins, Colab | MET | `results/chronos_run.json`. `results/chronos_import_check.json` passed. |
| 10 | Split-conformal on 2023 residuals per zone group; before/after for every interval model | MET | `results/conformal.json → rows` (CQR on 2023, per group, with Q and before/after coverage and width). `rolling.coverage_and_width` holds the primary calibration from the human-approved amendment. Chronos-2 before/after is on matched rows (`raw_rolling_origins`). Chronos-2 has no 2023 calibration, and this is stated (DECISIONS line 152). |
| 11 | Modeled zones and share of non-modeled pickups | MET | `results/modeled_zones.json`: 0.990412 / 0.009588. |
| 12 | README task definition word for word | MET | `README.md → Forecasting task`. |
| 13 | Outputs: `backtest_2024.csv`, F2, F2b | MET | `make verify PHASE=2`: 17/17 outputs present. |

## Test output

`make verify PHASE=2` ran in 56.6 s and exited 0:
```
ruff       PASS
pytest     PASS
no_skips   PASS
dbt_test   PASS   (PASS=47 WARN=0 ERROR=0 SKIP=0, full warehouse)
outputs    PASS   (17 files)
```

Other checks:
- `ruff check .`: All checks passed.
- `pytest -q`: all pass, 0 skipped.
- `pytest -rA tests/test_leakage.py tests/test_evaluate.py`: 27 passed (23 leakage + 4 evaluation).
- Reproducibility: I ran `python scripts/04b_evaluate.py`, which skipped every unit and reassembled the outputs, then `make figures`. Afterwards `git diff` showed only the `generated_utc` values in `conformal.json` and `forecast_summary.json`, which I reverted. Every CSV, PNG and SVG was byte-identical, so the committed F2 title is what the code produces.

## Number trace

I recomputed these independently from `data/forecasts/lgbm_quantile__expanding__test.parquet` and from `results/chronos_forecasts.parquet` (with sort and clip applied):

| Number | Where | Source | Recomputed | OK |
|---|---|---|---|---|
| 0.1645 / 0.1675 / 0.2411 | F2 title | `figure_stats_phase2.json`, `backtest_2024.csv` | LGBM 0.167490 | yes |
| "LightGBM not distinguishable" | F2 title | `wape_gap_bootstrap.csv` (all, lgbm vs chronos2_weather_future: [−0.000037, 0.005887]) | – | yes |
| Bar labels: 0.1652, 0.1844, and the per-group values | F2 | `backtest_2024.csv` (window expanding / zero_shot, raw, subset all, bucket all) | Chronos past 0.165208 | yes |
| LGBM − Chronos past gap 0.002283 [−0.000653, 0.005256] | DECISIONS line 178 | `wape_gap_bootstrap.csv` | gap 0.0022826. My own circular 7-day block bootstrap (seed 7) gave [−0.00121, 0.00562]: tied, the same conclusion. | yes |
| Raw coverage 0.7808 / 0.6919 | DECISIONS line 164 | `forecast_summary.json → coverage_80_all_zones` | 0.78078 / 0.69190 | yes |
| 0.7930–0.8220, 0.7142 / 0.6976, 0.8446 | DECISIONS line 164 | `forecast_summary.json`, `conformal.json` | – | yes |
| 131 of 168, 2024-10-13, Midtown Center | F2b title | `figure_stats_phase2.json` | – | yes |
| 103, 99.04%, 0.990412, 48%, 0.4816 / 0.4635 / 0.4488 | README | `modeled_zones.json`, `citywide_yearly.csv` | – | yes |
| Commit message `6d45047` | – | no numbers | – | n/a |

There are no untraceable numbers. `reports/analysis.md` does not exist yet (Phase 7).

## Method sanity

- **Lags under 24 h:** none. The grep for `lag_1`, `shift(1)` and `rolling(4)` over `src/`, `scripts/` and `dbt/models` finds only `features.py:65,66,78`. Those are `.shift(1)` on date-indexed matrices, which is a 1-day shift and correct.
- **Horizon:** `horizon` is in `CALENDAR_FEATURES` (`features.py:32`).
- **Leakage:** the test is real (see DoD 3).
- **SeasonalNaive comparison:** done with numbers and intervals for every model and group.
- **Metrics per zone group:** all present. Missing forecasts are counted in `n_missing_forecast`: 103 seasonal-naive rows at the DST lag-168 hole.
- **Conformal:**
  - CQR Q is not clipped at 0. Q = 0.0 in several groups comes from the mass of zero scores where q10 is clipped to 0 and y = 0. I checked `conformal_q`.
  - Rolling per-quantile calibration brings every model to 0.7930–0.8220.
  - The 2023 CQR under-covers in 2024. This is reported as a year-to-year shift.
- **Ranking:** over all zones, LightGBM and the two Chronos-2 variants form one top tier.
  - LGBM vs future-weather variant: tied.
  - LGBM vs past-weather variant: tied.
  - Past vs future weather: separated by 0.000679 [0.000147, 0.001211].
  - The F2 title states only the pairs it tests. Its rule is in DECISIONS line 171 and in the figure note. This is a finding, not a defect: a zero-shot model matching the trained model goes into the summary for Stanley.

## Figures

**F2_model_comparison.png**
- The title matches `wape_gap_bootstrap.csv`.
- No min–max range is quoted. The past-weather variant is left out of the "not distinguishable" list only because an interval in `results/` separates it from the best model.
- Bars start at 0. Each panel's scale is stated in the note. Model names are y tick labels, so there is no legend.
- Colours: baseline grey, LGBM in `model` blue, Chronos in the `foundation` palette entry and its tint.
- The x axis is "WAPE", a unitless ratio.
- It is readable at 7 in.
- No time axis, so no policy line is needed.

**F2b_fan_chart.png**
- The y axis is "Pickups per hour, Midtown Center". The x axis states the origin.
- The raw band is shaded, the conformal band dashed, and the actuals near-black.
- The legend sits in the headroom and covers no data.
- The axis is 2024-10 and has no policy date, so no policy line is needed.
- The title number is traced.

## Decisions check

- Every Phase-2 config key has a DECISIONS line: `models.*`, `forecast_eval.*`, `chronos.*` and `f2` / `f2b`.
- One exception: `chronos.batch_size: 256` has no line of its own. It is a GPU runtime knob. With `cross_learning=False` (DECISIONS line 142) and a fixed 2048-hour context for every series, it cannot change forecasts. I did not count it as a fix item. Add a half-line when Phase 3 next touches DECISIONS.

## Non-blocking observations (carry to Phase 3/5; not fix items)

1. `taxi_shock.conformal.conformal` reports `coverage_test_raw` / `coverage_test_conformal` over rows with an actual, including rows whose forecast is NaN. Those rows count as misses.
   - `evaluate()` and `rolling.coverage_and_width` drop such rows instead.
   - For seasonal naive CBD the two differ by 0.0001: 0.7771 in `conformal.json → rows` vs 0.7772 in `rolling.coverage_and_width`.
   - The effect is immaterial. Use one convention before Phase 5 reuses these tables.
2. Carried from round 2:
   - `04_backtest.py --full` skips an existing forecast file without checking a code fingerprint (DECISIONS line 180).
   - Phase 3 must name the frozen refit and its rounds per quantile (`lgbm_refits.csv`; q0.5 rounds range 61–5610).
3. `chronos.batch_size` decision half-line (see Decisions check).

## Fix list

None.

## Escalation reasons

None.
- No mandatory item was downgraded.
- Every model beats SeasonalNaive with intervals that exclude 0.
- Zero-shot Chronos-2 ties or slightly beats LightGBM. This is a finding to report, not a contradiction of the storyline.

## Amendments made

None.
