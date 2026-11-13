# Phase 3 review — where the forecaster breaks

Reviewer: phase-reviewer subagent (fresh context), 2026-11-09. Commits reviewed: 76d611e, 9243fc9.

## Verdict

**ESCALATE.** The pipeline is sound, the tests pass, and every number traces to a file. But the result goes against the Phase-3 storyline, and Stanley has to decide how Phases 3, 5 and 7 present it. The fixes below are needed whatever he decides.

The PLAN expected a CBD-specific forecasting failure ("persistent negative bias in CBD only"). The data show something different:
- The deviation is citywide and has the same sign in both groups: in the first four post-policy weeks actual pickups were CBD +6.29% and non-CBD +5.34% above forecast.
- The CBD's 4-week WAPE does not get worse (0.1904 → 0.1877).
- The one CBD CUSUM alarm is the same kind of event the calibration allows once a year. See the escalation reasons.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| T1 Freeze primary LGBM through 2024-12-31; SN and Chronos frozen | MET | `results/frozen_model.json` (train_end 2024-12-31 23:00, rounds 409/4244/1239, 2,639,787 rows). I checked that the booster files in `data/models/` have 409/4244/1239 trees. `forecast_frozen` only calls `predict_quantiles` and never refits. SeasonalNaive keeps its residual quantiles from the fit, and `predict_quantiles` reads history only for the lag-168 value. Chronos rows are the imported `main` run. |
| T2 Day-ahead forecasts 2024-07-01 → 2026-09-30, no retraining | MET | 822 origins. `shock_errors.csv` has 822 daily rows per model/series/group. `logs/shock.log`: 2,031,778 rows per model. |
| T3 Rolling 4-week WAPE and mean signed error per zone group | MET | `results/shock_errors.csv` has `wape`, `bias` (forecast − actual per zone-hour) and `log_actual_over_forecast` for cbd, non_cbd, manhattan_non_cbd, airports, other and all, with window_days 1 and 28. `tests/test_shock.py`. |
| T4a CUSUM on daily standardized CBD residuals, false alarms ≤ 1/yr on 2024, detection date + delay | MET | `results/drift_detection.json`: CBD h = 9.15, 1 calibration alarm, first alarm 2025-01-19 (up, 14 days). I reproduced this independently from `data/forecasts/lgbm_quantile__expanding__test.parquet`: mean 0.013963, sd 0.086679, one 2024 alarm, and h − 0.05 gives 2 alarms. |
| T4b Rolling-bias rule (2σ, 7 consecutive days) | PARTIAL | Implemented on **daily** z (`drift.rolling_bias_alarms`), not on a rolling bias. The word "rolling" in PLAN is ignored and no DECISIONS line records that reading. It never fires in 2024 or after, in any group or model. |
| Output `results/shock_errors.csv` | MET | 48,996 rows |
| Output `results/drift_detection.json` | MET | |
| Output `reports/figures/F3_error_over_time.png` | MET (renders), defects below | |
| DoD: F3 renders | MET | PNG 2023×1223 px, SVG too |
| DoD: detection delays recorded for both monitors | MET | CUSUM delay_days 14 (CBD) and 385 (non-CBD). Rolling-bias `first_alarm_on_or_after_policy: null` with `n_alarms_monitoring: 0`. |
| DoD: DECISIONS notes CUSUM parameters and false-alarm calibration | PARTIAL | k, the h grid, h values and "exactly 1 alarm in 2024" are recorded (DECISIONS line 195). The **dates** of the 2024 calibration alarms are not in DECISIONS or in `results/`, and the 2024-H1 daily series used for calibration is not saved under `results/` (`shock_errors.csv` starts 2024-07-01). So the calibration cannot be audited from `results/`. |

## Test output

- `make verify PHASE=3`: **exit 0**. ruff PASS, pytest PASS (106 passed, 0 skipped), no_skips PASS, dbt test PASS (47/47), outputs PASS (5 files).
- `ruff check .`: All checks passed.
- `pytest -q tests/test_leakage.py tests/test_shock.py tests/test_drift.py`: 30 passed.
- Leakage: `tests/test_leakage.py` poisons the target at and after the origin with 1e6/NaN, and the exog beyond the target day. It asserts unchanged forecasts and includes power checks. It is real, not a placeholder. **However**, it covers only the backtest-engine path. Phase 3 adds a new history-slicing path, `scripts/06_shock.py::forecast_frozen` (`panel.iloc[lo:cut]` with `searchsorted`), and no test covers it. On reading the code, the slice is correct.
- Short-lag grep (`lag_1`, `shift(1)`, `rolling(4)`): the only hits are day-level `shift(1)` calls in `features.py`, already reviewed in Phase 2. No sub-24 h lag.

## Number trace

| Number | Where | Source | OK |
|---|---|---|---|
| CBD +6.3% / non-CBD +5.3% (first 4 post weeks) | F3 title, DECISIONS 196 | `results/figure_stats_phase3.json`; `shock_errors.csv` monitored/28d on 2025-02-01: exp(log)−1 = 6.29% / 5.34% | yes |
| CUSUM CBD 2025-01-19, up, 14 d; non-CBD 2026-01-25, down, 385 d | F3 title, DECISIONS | `drift_detection.json` | yes |
| WAPE 0.1904 → 0.1877 (CBD); 0.2061 → 0.1773 (non-CBD) | DECISIONS 196, figure_stats | `shock_errors.csv` 2025-01-04 / 2025-02-01 | yes |
| 0.166 frozen vs 0.179 monitored, CBD, 2024-12-31 | DECISIONS 193 | `shock_errors.csv` (0.1664 / 0.1787) | yes |
| h 9.15 / 8.35; mean/sd 0.013963/0.086679, 0.021326/0.075647 | DECISIONS 195 | `drift_detection.json` | yes |
| Later alarms 2026-01-26, 2026-02-23 (CBD), 2026-01-25, 2026-02-23 (non-CBD); Chronos 2025-12-25 | DECISIONS 196 | `drift_detection.json` | yes |
| Rounds 409/4,244/1,239; 2,639,787 rows; 559.8 s | DECISIONS 192 | `frozen_model.json` | yes |
| **701 s (822 origins), 11 s (seasonal naive)** | DECISIONS 197 | only `logs/shock.log`, which is git-ignored and not under `results/` | **NO, FIX** |
| Commit message | no numbers | n/a | |
| README | no Phase-3 numbers | n/a | |

## Method sanity (Phase 3)

- **Frozen is truly frozen:** yes. The training end date is in `results/frozen_model.json` and the booster tree counts match the recorded rounds. One gap: the boosters are git-ignored and have no hash in the record, and `frozen_lgbm()` loads whatever files are on disk without checking them against the record.
- **In-sample overlap:** handled well. `frozen` (PLAN-literal, flagged `in_sample`) and `monitored` (out-of-sample backtest before 2025-01-01) are both kept, and the monitors calibrate on out-of-sample residuals.
- **Detection delay saved:** yes, for both groups and both models.
- **False-alarm calibration:** done as the PLAN specifies, on the same 2024 data used to standardize. I reproduced the 2024 alarm: **CBD 2024-09-10 (up), non-CBD 2024-09-06 (up)**. F3 shows the cause: actual/forecast reached about +9–10% in September 2024, more than the January 2025 excursion. h ≈ 9σ is large because 2024 has holiday and snow outliers (z = −5.3 on 2024-02-13, −3.6 on Thanksgiving).
- **What the CBD alarm actually is:** S+ builds from 2025-01-07 and crosses h on 2025-01-19 because of a single day with z = 3.56. It then resets, and no further up-alarm follows for 20 months. The 7-day mean z is back to about 0 by late January. Non-CBD S+ climbs over the same days (to 5.5, below its h). This is a short citywide excursion, not a persistent CBD level shift.
- **Rolling-bias rule:** read as 7 consecutive *daily* |z| > 2. Under the null this is roughly a (0.023)^7 event and it has essentially no power against a 5–6% shift (that is about 0.6σ daily). I ran a probe (not a result) of a rolling reading: 7-day mean z, standardized by its 2024 sd (0.569), beyond 2 for 7 consecutive days. It also does not fire in January 2025. It fires 2024-09-12 (up) and 2026-03-01 (down). So the conclusion does not change, but the chosen reading must be recorded and the rolling variant reported.
- **Lag features soften the frozen model:** the frozen LightGBM still reads lag_24…lag_336 and 7- and 28-day means of actuals, so it partly follows any level shift within 1–4 weeks without retraining. This is by design (PLAN), but it is the main reason a frozen lag-based model cannot "break" for long. It belongs in the Phase-3 text and in the Phase-5 framing.

## Figures

`reports/figures/F3_error_over_time.png` (10.1 × 6.1 in at 200 dpi, the small-multiples size):
- OK: CBD accent (#B23A48) and non-CBD grey match `style.py`. Pre-policy segments are tinted. Direct end labels, no legend. WAPE axis starts at 0. Zero line on the % panel. The policy line with its label is on both panels. Readable at 7 in wide. Sources are in the footnote.
- **Defect 1 (misleading emphasis):** the title headlines "CUSUM alarm for the CBD after 14 days" next to the policy start, which reads as detection of the policy. The calibrated monitor gave the same kind of up-alarm in September 2024 (inside the plotted range, not marked). The figure itself shows the pre-policy excursion (≈ +10%) was larger than the post-policy one. PLAN §7: the title states the finding only when the data support it.
- **Defect 2:** the 2024 calibration alarms (CBD 2024-09-10, non-CBD 2024-09-06) are not marked, so the reader cannot compare the post-policy alarm with the allowed false alarm.
- Minor: the y-label "Actual vs forecast (%)" should say "(actual − forecast) / forecast, %" or "Actual above forecast (%)" so the sign is clear.

## Decisions check

Recorded: frozen_train_end, forecast_window, monitor_start, calibration_period, rolling_days 28, groups / monitored_groups, k 0.5, max_false_alarms 1, the h grid, n_sigma 2, consecutive_days 7, log-ratio series, the in-sample handling, and the resumability rule.

Missing:
- No DECISIONS line says the rolling-bias rule is applied to daily z rather than to a rolling bias, and none says σ is the daily 2024 sd.
- The hard-coded `pd.Timedelta(days=35)` look-back in `scripts/06_shock.py::forecast_frozen` comes from neither config nor a DECISIONS line. CLAUDE.md: no hard-coded thresholds.
- The 2024 calibration alarm dates are not recorded.

## Fix list

The Builder can apply these now; they hold under any decision Stanley takes.

1. In `scripts/06_shock.py::monitors`, write the calibration-period alarm dates and sides (and the alarms at one grid step below h) into `results/drift_detection.json`. Also save the 2024-01-01 → 2024-06-30 daily rows of the `monitored` and `zero_shot` series to `results/shock_errors.csv` (or a separate `results/drift_calibration_series.csv`), so the calibration can be reproduced from `results/`. Add the dates (expected: CBD 2024-09-10 up, non-CBD 2024-09-06 up) to the DECISIONS entry for the CUSUM calibration.
2. In `src/taxi_shock/drift.py` and `scripts/06_shock.py`, add the rolling reading of the rolling-bias rule: trailing 7-day mean of z, standardized by its own 2024 sd, beyond ±2 for 7 consecutive days, same side. Report it beside the daily-z rule with its 2024 false alarms and post-policy first alarm. Add a unit test in `tests/test_drift.py`. Record both readings, and which one is primary, in `DECISIONS.md`.
3. In `scripts/06_shock.py::forecast_frozen`, replace the hard-coded `pd.Timedelta(days=35)` with a config value (e.g. `models.feature_history_days`), and add a DECISIONS line if a new key is introduced.
4. Move `forecast_frozen` into `src/taxi_shock/shock.py` (or another library module). Add a leakage test (`tests/test_leakage.py` or `tests/test_shock.py`) that poisons every panel row at or after each origin, asserts identical frozen forecasts for LGBM and SeasonalNaive, and includes a power check.
5. In `scripts/06_shock.py`, write each model's forecast runtime (origins, rows, seconds) into `results/frozen_model.json`. Re-cite the 701 s / 11 s in `DECISIONS.md` (line 197) from that file instead of `logs/shock.log`.
6. In `scripts/06_shock.py::frozen_lgbm`, record each booster file's sha256 and `num_trees` in `results/frozen_model.json`, and refuse to load boosters whose hash or tree count does not match the record. The files are git-ignored, so this is the only proof that the forecasts came from the recorded frozen model.
7. In `scripts/09_figures.py::phase3` / `viz/figures.py::f3_error_over_time`, mark the 2024 calibration alarms on F3, label them "CUSUM alarm, 2024 (calibration)", and change the % axis label to show the sign convention. The final title wording waits for Stanley's decision below. Until then the title must not present the CBD CUSUM alarm as detection of the policy without the 2024 comparison next to it.
8. In `README.md`, add F3 (Phase 3) to the `figures` row of the make-target table.

## Escalation reasons

1. **The result goes against the storyline and needs a human decision** (reviewer rules: "a result contradicts the storyline … needs a human decision"; the storyline is outside the amendment bounds).
   - PLAN Phase 3's goal is to "show the structural break as a forecasting failure, separated by CBD vs non-CBD", and it expects persistent negative CBD-only bias.
   - Measured instead: the CBD and non-CBD deviations move together for the whole post-period (F3 lower panel). In the first four weeks, actual is above forecast in both groups (+6.29% / +5.34%, `results/figure_stats_phase3.json`). CBD rolling WAPE does not rise (0.1904 → 0.1877, `results/shock_errors.csv`). The daily-z rolling-bias rule never fires (`results/drift_detection.json`).
   - The only CBD alarm (2025-01-19, up) is the same kind of event the ≤ 1/yr calibration allows. The calibrated CUSUM alarmed up on 2024-09-10 (reproduced here, not yet in `results/`; see Fix 1). The 2025 alarm is driven by one day with z = 3.56 and is followed by no further up-alarm.
   - The Builder reported this honestly as a finding (DECISIONS line 196). What is unresolved is the storyline itself.

   Decisions Stanley must take:
   - (a) How Phase 3 and the F3 title describe the result, e.g. "a lag-based day-ahead forecaster absorbed congestion pricing; no CBD-specific break detected" versus presenting the 14-day alarm.
   - (b) Whether Phase 5 keeps its design unchanged. The CBD "error-recovery curve" for S0–S3 has no error to recover from. S3 multiplies CBD forecasts by exp(β̂), which only makes sense once Phase 4 gives the sign and size of β̂.
   - (c) Whether README/analysis framing ("where the forecaster breaks") changes. That framing is part of the storyline in PLAN §1.

   No tuning should be done to make a break appear (CLAUDE.md).

## Amendments made

None. Nothing within the amendment bounds (thresholds, zone set, training window, figure details, runtime) would resolve the escalation. Changing the CUSUM k/h or the monitored series to produce a CBD detection would be tuning toward an expected result.

## Closing note (2026-11-13, Stanley's ruling — PLAN Amendment 5)

Phase 3 is **closed**. The ESCALATE verdict above is resolved by Stanley's ruling at Checkpoint 6: no CBD-specific break is detected, and this is reported as found. The review is not re-run. The open fix items that remain relevant (runtimes and booster sha in `frozen_model.json`, saved calibration alarm dates, the rolling-mean bias rule, the F3 title) are carried to the Phase 7 deferred-items list (DECISIONS.md).
