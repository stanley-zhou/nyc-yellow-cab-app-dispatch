# Phase 5 review, round 2 (after fix round 1): how the system should adapt

Reviewer: phase-reviewer subagent (fresh context), 2026-11-13. Reviewed HEAD 4c46b7f, working tree clean. The round-1 review (FIX) is kept as `reviews/phase_5_round1.md`.

## Verdict

**FIX** (fix round 2 of 2).

All ten round-1 fixes were applied, and the S1e sensitivity is clean:
- S1e's 2025-01 refit reproduces the frozen model exactly: same train window, rows_boost 2,639,787, rounds {409, 4244, 1239} (`adaptation_refits.csv` vs `frozen_model.json`).
- Its daily absolute errors for 2025-01 are identical to S0's (max difference 0.0, `adaptation_daily.csv`).
- So S1e − S0 is a pure retraining contrast, and the "gain is from retraining, not the window" reading holds.

Two defects remain, both introduced or exposed by fix 1:
- F5 draws S0's **in-sample** 2024-H2 forecasts as if they were forecasts.
- S0's rolling-conformal calibration for the first eight weeks of the window uses in-sample residuals.

The Phase-3 decision (DECISIONS line 193) explicitly rejects both practices. There are also smaller documentation gaps. None of this needs a human decision.

## DoD table

Scope: PLAN Phase 5, re-scoped by Amendment 4 D6 and Amendment 5 (S0, S1, S4, S6; no S2/S3/S5). The re-scope is human-approved.

| Item | Status | Evidence |
|---|---|---|
| Strategies S0, S1, S4, S6 | MET | `config/project.yaml → adapt.strategies`; 23 refits each for S1/S6 (`adaptation_refits.csv`); S1e sensitivity and SN reference added (`adapt.sensitivity`, `adapt.reference`) |
| Evaluation window 2025-02 → 2026-09 | MET | `adaptation_summary.json → eval_window`; 607 days (`adaptation_gaps.csv n_days`) |
| Same metrics as Phase 2 | MET | `adaptation.csv`: wape, mae, mase, bias, pinball q10/q50/q90, coverage_80, width_80, n_missing_forecast; raw and rolling-conformal; 5 zone groups × 5 horizon buckets × 3 subsets; 3,360 rows per strategy; one `n` per cell across strategies. SN reference: present. MASE scale now 2022-01-01 → 2024-12-31 as stated. |
| WAPE and coverage per strategy × zone group × quarter | MET | `adaptation.csv`, period 2025Q1…2026Q3. The 2025Q1 = Feb–Mar rule is in DECISIONS and in the §5 table note. |
| Recovery curve, rolling 4-week WAPE, CBD, Phase-3 axes | PARTIAL | F5 is now on 2024-07-01 → 2026-09-30 with the policy line on every panel. However, the S0 segment 2024-07 → 2024-12 is in-sample (see Figures 1). |
| `results/adaptation.csv`, `F5_adaptation.png` | MET | `make verify PHASE=5` outputs PASS |
| Recommendation paragraph citing the table (cost vs gain) | MET | `reports/analysis.md` §5. Every number traces (see Number trace). Airports, the refit vs month cost, 2025-Q1 and the S0 intervals are corrected. |

## Test output

- `ruff check .` → `All checks passed!`
- `make verify PHASE=5` → exit 0 in 1m46s:
  - ruff PASS
  - pytest PASS
  - no_skips PASS
  - dbt_test PASS (`PASS=62 WARN=0 ERROR=0 SKIP=0`)
  - outputs PASS (7 files)
- `pytest -q tests/test_leakage.py tests/test_adapt.py` → 26 passed.

## Number trace

Sources: `adaptation_summary.json` (AS), `adaptation_gaps.csv` (AG), `adaptation.csv` (AC), `figure_stats_phase5.json` (FS), `adaptation_refits.csv` (AR).

| Number (where) | Source | OK |
|---|---|---|
| WAPE all 0.164 / 0.162 / 0.165 / 0.168; CBD 0.154 / 0.151 / 0.154 / 0.157 (§5 table, exec. summary 4, README l.19) | AS headline | yes |
| S1e 0.162 / 0.152 / −1.8% / 0.81; SN 0.237 / 0.223 / −0.1% / 0.81 (§5 table) | AS headline s1e, sn; bias_pct s1e\|all −1.79, sn\|all −0.15 | yes |
| Bias −2.3 / −1.7 / −2.0 / −2.9% | AS bias_pct_of_pickups | yes |
| Coverage 0.81 / 0.80 / 0.80 / 0.80; raw 0.74–0.78; 2025-Q1 0.80–0.82; S0 raw 0.78 → 0.81 | AC (0.8122, 0.8045, 0.7995, 0.8027; raw 0.7441…0.7821; Q1 0.8006…0.8183) | yes |
| MASE S0 1.40, SN 1.89; "beats naive by about 7 pp" | AS headline mase; AG sn gaps 6.92–7.51 pp | yes |
| S1 vs S0 0.23 pp all, 0.29 pp CBD, CIs exclude 0; Manhattan non-CBD not distinguishable | AG | yes |
| Retraining effect 0.24 pp [−0.36, −0.14]; window effect 0.01 pp [−0.08, +0.11] | AG all s1e/s0, s1/s1e; FS | yes |
| S4 outer boroughs 0.395 vs S1 0.403 vs S0 0.412; airports 0.175 vs 0.179 (excludes 0); Manhattan non-CBD 0.147 vs 0.142, distinguishably behind S0 and S1 | AS, AG | yes |
| 2026-Q1 WAPE 0.187–0.191 | AC raw 2026Q1 (0.1868…0.1908) | yes |
| S0 ahead in 2025-Q1 | AC 0.1623 vs 0.1639 | yes |
| Refit median 384 s, month 411 s, 23 refits; S1e 720 s, "about twice" (1.87×); Chronos 250 s/month on an L4 | AS retrain_cost | yes |
| F5 title 16.2% / 16.4% / −2.9% / −2.3%; note 16.19% / 16.20% / 23.7% | FS | yes |
| README l.89 "166.1 / 137.4 min" | AR wall_seconds sums 9964.5 / 8242.8 s | yes, but S1e is missing (see fix 4) |
| DECISIONS l.276 S1e/SN results, 4,065,925 / 4,142,557 rows | AS, AG, AR rows_boost | yes |
| Commit 4c46b7f message | no numbers | n/a |

No untraceable numbers.

## Method sanity

1. **Leakage.**
   - `tests/test_leakage.py` poisons every pickup from the origin onwards (1e6 and NaN) and asserts unchanged SN/ETS/LGBM forecasts.
   - The new `tests/test_adapt.py` runs LightGBM with the channel features through `run_backtest` with the channel table poisoned from the origin day (1e6 and 0). The forecasts are identical. Its power check (shuffled pre-origin shares) changes them.
   - Targets are the hours 0–23 of the origin day (`backtest.py:73–77`), so the day-keyed channel features never reach day D.
2. **Short lags.** `grep lag_1|shift(1)|rolling(4)` finds `shift(1)` only on daily, date-reindexed frames (`adapt.py:38–45`, `features.py:65–78`), i.e. 24 h. There is no `lag_1` and no `rolling(4)`.
3. **S1e isolates retraining.** It matches S0 exactly in January 2025 (Verdict). The window effect is not distinguishable overall. Not stated in the report: S1e is ahead of S1 by 0.5 pp in 2026-Q1 (0.1818 vs 0.1868, AC), and S1 is ahead in 2025-Q4 (0.1532 vs 0.1550). That is acceptable because the report claims only the overall result.
4. **S0 conformal calibrated partly on in-sample residuals (new).**
   - `08_adapt.py::evaluate_all` calls `rolling_conformal(fc, …)` on `data/forecasts/frozen/lgbm_quantile.parquet`, whose origins start 2024-07-01.
   - For eval origins 2025-02-01 → 2025-03-25, the trailing 12-week calibration window starts between 2024-11-09 and 2024-12-31. It therefore contains frozen-model residuals on days the model was trained on: boosted on through 2024-12-03, early-stopped on 2024-12-04 → 12-31 (`frozen_model.json → fit`).
   - DECISIONS line 193 (Phase 3) rejected exactly this ("would understate normal error"). Phase 3 used the out-of-sample `monitored` series (`data/forecasts/lgbm_quantile__expanding__test.parquet`) before 2025-01-01.
   - Observed S0 2025-Q1 calibrated coverage is 0.8125 (AC), so the effect may be small. It is unmeasured and undocumented.
5. **SN reference has 206 missing forecasts.**
   - `n_missing_forecast` = 206 for `sn` (AC). These are the lag-168 targets 2025-03-16 02:00 and 2026-03-15 02:00 × 103 zones, which point at the non-existent spring-forward hour.
   - `metrics.py` drops NaN pairs, so SN is scored on 1,500,092 hours while `n` says 1,500,298.
   - In `adaptation_daily.csv` those rows add `y` but no error. As a result, SN WAPE recomputed from the daily file is 0.236957 vs the headline 0.236985, and SN `bias_pct_of_pickups` is diluted the same way.
   - The size is immaterial, but the rule is unrecorded, and DECISIONS line 272 says no Phase-5 row has a missing forecast.
6. **Pre-registered D6 expectation failed** (S6 bias −2.9% vs S0 −2.3%). It is reported as found, with no tuning. Fine.

## Figures

`reports/figures/F5_adaptation.png` (2051×1223 px, 10.3 × 6.1 in at 200 dpi, small-multiples size):
1. **The S0 line before 2025-01-01 is in-sample.**
   - In the CBD WAPE panel, S0 runs at ≈12–14% in Jul–Nov 2024 against ≈14–16% for S4. That gap is training-set fit, not forecast skill. The figure reads as "the frozen model was best until the policy, then lost its edge", which is a manufactured break.
   - The note says only "S0 … from 2024-07"; nothing marks the segment as in-sample.
   - F3 handled the same overlap with the `monitored` series (DECISIONS line 193).
2. **Annotation collision.** "before the evaluation window" (bottom-left panel) is struck through by the policy line, which sits inside the shaded band. Shorten the text or move it.
3. **Otherwise OK.**
   - The policy line is on all four panels.
   - Phase-3 x-range.
   - S0 is drawn in `PALETTE["baseline"]`.
   - Units on the y-labels.
   - Direct labels, no legend.
   - Zero line on the bias panels.
   - Two-line title stating a finding the results support, with no causal anchoring to the policy.
   - Readable at 7 in.

## Decisions check

| Rule in code | DECISIONS line | Status |
|---|---|---|
| `adapt.windows` (s1/s6 sliding_24m, s1e expanding), `sensitivity`, `reference` | 274 | OK |
| `channel_windows_days` [7, 28], `city_window_days` 7 (now in config) | 274 | OK |
| MASE scale from `model_start` | 274 | OK |
| S6 NaN rule, quarter assignment, S0 adaptive intervals | 275 (fix 8) | OK |
| `retrain_cost` hardware from `machine_resources.json`; refit vs month seconds | 274 | OK |
| S1e above the ~4M-row guideline, kept | 276 | OK |
| S0 conformal calibrated on in-sample residuals for origins to 2025-03-25 | none | **missing** (and contradicts line 193) |
| F5 S0 segment 2024-07 → 2024-12 in-sample | none | **missing** |
| SN: 206 spring-forward lag-168 hours without a forecast, dropped pairwise; `n` counts them | none (line 272 says 0 missing) | **missing** |

## Fix list

1. In `scripts/08_adapt.py::load_strategy` / `evaluate_all`, take S0 forecasts before 2025-01-01 from the out-of-sample Phase-2 expanding backtest (`data/forecasts/lgbm_quantile__expanding__test.parquet`, the Phase-3 `monitored` series), so that both the rolling-conformal calibration and F5 use out-of-sample residuals, as Phase 3 does. Then rerun `--evaluate` and `scripts/09_figures.py`.
   - If you keep the frozen in-sample rows instead, you must do two things. First, draw the S0 pre-2025 segment visibly different (lighter or dashed) in `src/taxi_shock/viz/figures.py::f5_adaptation` and label it "in-sample" in the note. Second, report S0's 2025-02-01 → 03-25 calibrated coverage under both calibrations in `DECISIONS.md`.
2. In `src/taxi_shock/viz/figures.py::f5_adaptation`, stop the policy line striking through the "before the evaluation window" annotation (shorter text, two lines, or placed at the top of the band).
3. In `DECISIONS.md`, add a line recording the following, with the source files:
   - The SN reference has 206 missing forecasts (lag-168 into the spring-forward hour; targets 2025-03-16 02:00 and 2026-03-15 02:00).
   - Metrics drop those pairs, while `n` in `adaptation.csv` counts them.
   - The daily file therefore gives SN WAPE 0.236957 vs the headline 0.236985.
   - Amend line 272's "no missing forecast" to "no strategy".
   - Also exclude rows with a NaN `point` from the `adaptation_daily.csv` sums in `scripts/08_adapt.py::evaluate_all`, so the daily file and the headline agree.
4. In `README.md`, add S1e to the `adapt` target description (l.68) and to the runtime table (l.89). Rerun `scripts/20_runtimes.py`: `results/runtimes.json` was generated 2026-11-13 12:20 UTC, before the S1e refits finished, and has no S1e entry.

## Escalation reasons

None. This is fix round 2. Fixes 1–4 are inside the plan. If the same defects survive the next round, the CLAUDE.md rule converts the outcome to ESCALATE.

## Amendments made

None.
