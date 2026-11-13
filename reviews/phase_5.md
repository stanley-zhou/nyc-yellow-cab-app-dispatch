# Phase 5 review, round 3 (after fix round 2): how the system should adapt

Reviewer: phase-reviewer subagent (fresh context), 2026-11-13. Reviewed HEAD 11a2a24, working tree clean. Earlier rounds are kept as `reviews/phase_5_round1.md` (FIX) and `reviews/phase_5_round2.md` (FIX).

## Verdict

**PASS.**

All four round-2 fixes are applied and verified against the data, not just against the text:
- S0 before 2025-01-01 is now the out-of-sample Phase-2 backtest.
  - S0's daily absolute errors in `results/adaptation_daily.csv` equal the Phase-3 `lgbm_quantile / monitored` series in `results/shock_errors.csv` (window_days = 1) on all 4,110 zone-group-days. The max difference is 0.0, both before and after 2025-01-01.
  - Against the in-sample `frozen` series, the pre-2025 rows differ by up to 15,122 pickups.
- The SN daily file now agrees with the headline (0.236985 both).
- The annotation that the policy line struck through is gone.
- README and `runtimes.json` now include S1e.

Every DoD item is MET, tests are green, and every number traces to a results file. No failure from an earlier round survives.

## DoD table

Scope: PLAN Phase 5 as re-scoped by Amendment 4 D6 and Amendment 5 (S0, S1, S4, S6; no S2/S3/S5). The re-scope is human-approved.

| Item | Status | Evidence |
|---|---|---|
| Strategies S0, S1, S4, S6 (+ S1e sensitivity, SN reference) | MET | `config/project.yaml → adapt`. `results/adaptation_refits.csv` has 23 refits each for S1, S6 and S1e. `adaptation_summary.json → uncalibrated_origins` is 0 for all six. |
| Evaluation window 2025-02 → 2026-09 | MET | `adaptation_summary.json → eval_window`; `adaptation_gaps.csv n_days` = 607 |
| Same metrics as Phase 2 | MET | `adaptation.csv` (20,160 rows) has WAPE, MAE, MASE, bias, pinball q10/q50/q90, coverage_80, width_80 and n_missing_forecast, each raw and with rolling-12w conformal, by zone group × horizon bucket × subset. The SN reference is included. `n_missing_forecast` is 0 for every strategy and 206 for SN (documented). |
| WAPE and coverage per strategy × zone group × quarter | MET | `adaptation.csv`, period 2025Q1…2026Q3; the 2025Q1 = Feb–Mar rule is in DECISIONS l.275 and in the §5 table note |
| Recovery curve, rolling 4-week WAPE, CBD, on the Phase-3 axes | MET | F5 covers 2024-07-01 → 2026-09-30, with the policy line on all four panels. Every pre-2025 segment is now out of sample (S0 = Phase-2 backtest, S4 zero-shot, S1/S6 their own monthly refits). `min_periods=28`, so no partial windows are drawn. |
| `results/adaptation.csv`, `reports/figures/F5_adaptation.png` | MET | `make verify PHASE=5` outputs PASS (7 files) |
| Recommendation paragraph citing the table (cost vs gain) | MET | `reports/analysis.md` §5 "Recommendation for the forecasting system". It recommends S1, quotes refit 384 s / month 411 s / S1e 720 s / Chronos 250 s per month from `retrain_cost`, and states that the gain does not hold in every quarter. |

## Test output

- `ruff check .` → `All checks passed!`
- `make verify PHASE=5` → exit 0, 1m38s:
  - ruff PASS
  - pytest PASS
  - no_skips PASS
  - dbt_test PASS (`PASS=62 WARN=0 ERROR=0 SKIP=0`)
  - outputs PASS
- `pytest tests/test_leakage.py tests/test_adapt.py` → 26 passed, exit 0.
- Full `pytest -q` → green, no skips.

## Number trace

Sources:
- AS = `results/adaptation_summary.json`
- AC = `results/adaptation.csv`
- AG = `results/adaptation_gaps.csv`
- AD = `results/adaptation_daily.csv`
- FS = `results/figure_stats_phase5.json`
- RT = `results/runtimes.json`

| Number (where) | Source | OK |
|---|---|---|
| WAPE all 0.164 / 0.162 / 0.165 / 0.168, CBD 0.154 / 0.151 / 0.154 / 0.157 (§5 table; exec. summary 4; README l.19) | AS headline (0.16433, 0.16201, 0.16485, 0.16775; CBD 0.15437, 0.15147, 0.15443, 0.15696). Recomputed from AD in-window rows to 6 d.p. | yes |
| S1e 0.162 / 0.152 / −1.8% / 0.81; SN 0.237 / 0.223 / −0.1% / 0.81 | AS headline s1e, sn; bias_pct s1e\|all −1.788, sn\|all −0.147; coverage 0.8059, 0.8143 | yes |
| Bias −2.3 / −1.7 / −2.0 / −2.9% (table, exec. summary, F5 title) | AS bias_pct_of_pickups | yes |
| Coverage 0.81 / 0.80 / 0.80 / 0.80; "0.80–0.81"; raw "0.74–0.78"; S0 raw 0.78 → 0.81 | AC conformal 0.8126 / 0.8045 / 0.7995 / 0.8027; raw 0.7441…0.7826 | yes |
| 2025-Q1 coverage "0.80–0.82 for the four strategies" | AC 0.8165, 0.8183, 0.8006, 0.8121 | yes |
| DECISIONS l.277: S0 coverage 2025-Q1 0.8125 → 0.8165, CBD 0.8099 → 0.8153, window 0.8122 → 0.8126, CBD 0.8028 → 0.8033 | old values: `git show 4c46b7f:results/adaptation.csv` (0.812529, 0.809913, 0.812229, 0.802771); new values: AC | yes |
| SN 206 missing hours; daily-file WAPE 0.236985 = headline | AC n_missing_forecast (103 + 103; CBD 38 + 38); AD recomputed 0.236985 | yes |
| S1 vs S0 −0.23 pp all, −0.29 pp CBD, CIs exclude 0; Manhattan non-CBD not distinguishable | AG rows 31, 60, 91 | yes |
| Retraining effect 0.24 pp (CI excludes 0); window effect 0.01 pp (CI includes 0) | AG s1e/s0 −0.002444 [−0.00358, −0.00143]; s1/s1e +0.000122 [−0.00078, 0.00111]; FS | yes |
| S4 outer boroughs 0.395 vs 0.403 vs 0.412; airports 0.175 vs 0.179 (excludes 0); Manhattan non-CBD 0.147 vs 0.142 | AS headline; AG airports s4/s1 [−0.00829, −0.000008]; Manhattan non-CBD s4/s0 and s4/s1 distinguishable | yes |
| 2026-Q1 WAPE 0.187–0.191; S0 ahead in 2025-Q1 | AC raw 0.1868…0.1908; 0.1623 vs 0.1639 | yes |
| MASE S0 1.40, SN 1.89; "about 7 pp" | AS mase 1.396, 1.893; AG sn gaps 6.92–7.51 pp | yes |
| Refit 384 s, month 411 s, 23 refits, S1e 720 s, Chronos 250 s/month on L4 | AS retrain_cost (384.2, 411.1, 23, 719.5, 249.8, "NVIDIA L4") | yes |
| README l.89 166.1 / 137.4 / 301.7 min | RT adaptation_refits 9964.5 / 8242.8 / 18102.6 s | yes |
| F5 title 16.2% / 16.4% / −2.9% / −2.3%; note 16.19% / 16.20% / 23.7% | FS | yes |
| Commit 11a2a24 message | no numbers | n/a |

No untraceable numbers.

## Method sanity

1. **Leakage.**
   - `tests/test_leakage.py` poisons every pickup from the origin on (1e6 and NaN) and asserts unchanged SN/ETS/LGBM forecasts. It includes power checks.
   - `tests/test_adapt.py` runs LightGBM with the channel features end to end through `run_backtest`, with the channel table poisoned from the origin day. The forecasts are unchanged, and the power check changes them.
   - Both pass when run alone.
2. **Short lags.** `grep lag_1|shift(1)|rolling(4)` over src, scripts, tests and dbt models finds only `shift(1)` on daily, date-reindexed frames (`adapt.py:38–45`, `features.py:65–78`), i.e. 24 h. There is no `lag_1` and no `rolling(4)`.
3. **S0 splice (fix 1).** `08_adapt.py::load_strategy` takes Phase-2 backtest origins in [`shock.forecast_window[0]`, `shock.monitor_start`) and frozen origins ≥ `monitor_start`. It neither overlaps nor leaves a gap, and the result matches the Phase-3 `monitored` series exactly. Point metrics are unchanged; only the conformal residuals of the first ~8 evaluation weeks moved (coverage +0.004 in 2025-Q1). All bounds are read from config.
4. **Identical evaluation sets.** `n` is common across strategies in every cell. SN's 206 missing forecasts are dropped pairwise in the metrics and now also in the daily file.
5. **Pre-registered D6 expectation failed** (S6 bias −2.9% vs S0 −2.3%; S6 is distinguishably worse than S0 and S1 over all zones and in the CBD). It is reported as found, and no S6 variant was tried afterwards.
6. **S1e isolates retraining** (verified in round 2: the 2025-01 refit is identical to the frozen model). The report claims only the overall result, which holds. Its quarter-level reversals (S1e ahead in 2026-Q1, S1 ahead in 2025-Q4) are not claimed either way.

## Figures

`reports/figures/F5_adaptation.png` (2051 × 1223 px, about 10.3 × 6.1 in at 200 dpi, small-multiples size):
- **Fix 2 applied.** The in-panel "before the evaluation window" label is removed, and the shading is explained in the note.
- **Pre-2025 S0 segment.** The S0 segment before 2025 is now out of sample. In the CBD it sits at about 15–17.5% in Aug–Oct 2024, near or above S4, so the manufactured "frozen model best until the policy" pattern from round 2 is gone. The note states that S0 there is the Phase-2 backtest.
- **Other checks pass:**
  - The policy line is on all four panels.
  - The axes are the Phase-3 axes.
  - S0 is drawn in `PALETTE["baseline"]`.
  - Y-labels carry units ("WAPE, 4-week (%)", "Bias, 4-week (%)").
  - Direct labels replace a legend.
  - The bias panels have a zero line.
  - The WAPE axes are not zero-based, which is acceptable for a rate shown as a line.
  - The title is two lines and states a finding supported by FS / AS, with no causal anchoring to the policy.
  - The figure is readable at 7 in.
- **Cosmetic, non-blocking (Phase 7 polish).**
  - In the CBD WAPE panel, the S6 and S0 peak in January 2025 (about 23%) touches the "C" of the policy-line label "Congestion pricing starts 2025-01-05". The label stays legible. Lowering `label_y`, or placing the label in the all-zones panel, would clear it.
  - The "S0 frozen" direct label also covers the pre-2025 backtest segment. The note explains this; a lighter tint before 2025-01-01 would make it visible without reading the note.

## Decisions check

| Rule in code | DECISIONS line | Status |
|---|---|---|
| S0 before `shock.monitor_start` = Phase-2 out-of-sample backtest | 277 (1), referencing the [P3] in-sample-overlap rule at l.192–193 | OK |
| SN: 206 spring-forward lag-168 hours without a forecast, dropped pairwise; `n` counts them; daily file drops them | 277 (3), which explicitly corrects l.272 | OK |
| F5 shading explained in the note (no in-panel label) | 277 (2) | OK |
| `adapt.windows`, `sensitivity`, `reference`, `run_start`, channel windows, MASE scale window | 269, 274, 276 | OK |
| S6 NaN rule, quarter assignment, S0 adaptive intervals | 275 | OK |
| `retrain_cost` hardware from `machine_resources.json`; refit vs month seconds | 274 | OK |
| S1e rows_boost above the ~4M guideline, kept | 276 | OK |

No missing lines. A trivial inconsistency: the `Makefile` comment on the `adapt` target (l.92) says "S1 / S6 monthly refits" while the recipe also runs `--run s1e`. Update it in Phase 7.

## Fix list

None.

## Escalation reasons

None. This is the third review of Phase 5. None of the round-2 defects survived.

## Amendments made

None.

## Non-blocking notes for Phase 7

1. `src/taxi_shock/viz/figures.py::f5_adaptation`: keep the January 2025 CBD peak clear of the policy-line label, and consider a lighter tint for S0 before `shock.monitor_start`.
2. `Makefile` l.92: mention S1e in the `adapt` target comment.
