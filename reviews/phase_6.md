# Phase 6 review (round 3): HVFHV streaming, C6 (FHV congestion pricing), Amendment 4/4a D0–D5b

Reviewer: phase-reviewer subagent (fresh context), 2026-11-13. Commit reviewed: 12efb05 (working tree clean). Round-2 fixes are in 682ea81. Earlier reviews are kept at `reviews/phase_6_round1.md` and `reviews/phase_6_round2.md`.
Scope = `config/phase_outputs.yaml → 6`. PLAN gives Phase 6 no formal DoD, so the DoD below is the one used in rounds 1–2: PLAN Phase 6, Amendment 3 C6, Amendment 4/4a (HVFHV disk decision, D0–D5b), plus the round-1 and round-2 fix items.

## Verdict

**PASS.**

- All four round-2 fixes are applied, and I verified each against code, results and the rendered figure.
- No round-1 or round-2 failure survives.
- Tests, dbt tests and ruff are green.
- Every number in figure titles and in the fix commit message traces to `results/`.
- The D2 re-run reproduces the committed results.

What the results show, for Checkpoint 6. These are findings, not defects; each was handled by a pre-registered rule.
- **C6:** every FHV series fails the pre-trend test, so no effect is estimated.
- **D2:** the estimators disagree, and the Manhattan non-CBD lead placebo fails.
- **D3:** not identified.
- **D5:** the gate is closed.
- **D5b:** the step is citywide, not CBD-specific. All DiD pre-trend tests reject.
- **Amendment 4's motivating CBD "decline"** compares a 5-week month with a 4-week month. Per week, CBD yellow pickups rose 15.6% (`results/channel_restatement.json`).

## DoD table

| Item | Status | Evidence |
|---|---|---|
| HVFHV 2023-01 → 2026-09 streamed (download → aggregate → verify → delete), manifest kept | MET | `results/hvfhv_stream_log.csv` (45 verified); `data/raw/hvfhv_manifest.csv` |
| Aggregates (i) zone × hour × … and (ii) pair × week | MET | `scripts/11_hvfhv_stream.py`; `tests/test_phase6.py::test_hvfhv_aggregate_trip_types_bins_and_accounting` |
| Disk report first; 15 GB guard | MET | `results/hvfhv_disk_report.json`; `hvfhv.min_free_gb` |
| HVFHV totals saved | MET | `results/hvfhv_summary.json` |
| C6: Phase-4 design, platform split, weighted and equal weight, pre-trend test first, stop if it rejects | MET | `results/fhv_did.json`: 4 series × 2 weightings, all fail, no `estimate` key; `test_c6_gate_withholds_the_estimate_when_pretrends_reject` |
| Lyft January 2025 separate | MET (by the rule) | `channel_did.lyft_splits`; computed only for a passing series |
| F6 taxi vs FHV on one axis | MET | `reports/figures/F6_taxi_vs_fhv.png`: label fits (round-2 fix 1) |
| No FHV forecasting | MET | none present |
| D0–D5b result files; F6a–F6e | MET | `make verify PHASE=6` → outputs PASS |
| D2 reproducible and not seed-dependent | MET | `incr.n_rep: 25`, `scripts/12_incrementality.py::plpr`; draws in `results/incrementality_dml.json → areas.*.dml_panel_plpr.theta_draws`. My re-run (3 min 27 s) reproduced the committed file: only float noise at the 1e-16 level in TWFE SEs, plus `generated_utc`. I restored the committed file afterwards |
| D5b pre-trend tests saved and cited | MET | `app_share_policy_step.json → yellow.pretrend.*`, `hvfhv.pretrend_uber_lyft_cell_weighted` |
| Per-week monthly means | MET | `channel_monthly.csv`, `channel_restatement.json`, `cross_platform_monthly.csv` (`n_weeks`) |
| Tests for Phase-6 code | MET | `tests/test_phase6.py` (4 tests) |
| No hard-coded dates/thresholds | MET | config keys `channel.*`, `channel_did.*`, `incr.*` |
| `make all` includes the Phase-6 tables | MET | `Makefile` line 92 `all: … hvfhv channel fhv …`. `adapt` and `report` are still unimplemented (Phases 5 and 7), which is not this phase's item |

## Test output

`make verify PHASE=6` exited 0 in 1 min 17 s:

| Check | Result |
|---|---|
| `ruff check .` | All checks passed! (also run standalone) |
| pytest | 124 passed, 0 skipped (`no_skips` PASS) |
| dbt test | PASS=62 WARN=0 ERROR=0 SKIP=0 |
| outputs | PASS (every file in `config/phase_outputs.yaml → 6`) |

- `pytest tests/test_leakage.py tests/test_phase6.py`: 27 passed. `test_leakage.py` poisons values at and after the origin and asserts unchanged forecasts. It is not a placeholder, and this phase does not touch it.

## Number trace

**Fix commit 682ea81.** "CBD median 0.522 over 25 draws" traces to `incrementality_dml.json → areas.cbd.dml_panel_plpr.theta` = 0.52176, `n_rep` = 25. The 13th of the 25 sorted draws is 0.522.

**DECISIONS D2 / round-2 entries**, all checked against `incrementality_panel_summary.csv` and `theta_draws`:

| Area | Median θ [CI] | Draw range | Draws below 0.5 |
|---|---|---|---|
| CBD | 0.522 [0.414, 0.629] | 0.491–0.559 | 4 of 25 |
| Manhattan non-CBD | 0.503 [0.226, 0.779] | 0.438–0.720 | — |
| Outer | 0.866 [0.234, 1.499] | 0.747–0.902 | — |

- The wording "median just above that range, CI overlapping it" is accurate.

**DECISIONS C6, lowest pre-period months.** Checked against `fhv_event_study.csv`, k mapped to month (k = −1 is Dec 2024):

| Series | Weighting | Lowest pre-period month(s) | Matches DECISIONS |
|---|---|---|---|
| Uber + Lyft | equal | k = −5, Aug 2024, 8.6% | ✓ |
| Uber + Lyft | weighted | k = −1 / −5 / −13: 14.9 / 15.1 / 15.2%, within 0.3 pp | ✓ (k = −2 at 15.2% also qualifies; not wrong) |
| Uber | equal | Aug 2024 | ✓ |
| Uber | weighted | Dec 2024 | ✓ |
| Lyft | equal | k = −20, May 2023 | ✓ |
| Lyft | weighted | k = −13, Dec 2023 | ✓ |
| Shared | both | Dec 2024, after a steep fall over the last three pre-period months (27.8 → 18.2 → 6.3%) | ✓ |

**DECISIONS D5b.**
- Significant pre-weeks: −26 to −22, −18 to −17 and −5 to −3. Each has |z| > 2.2 in `app_share_step_event_study.csv`, and −21 (z 0.62) is correctly excluded.
- HVFHV pre-trend p = 2.5e−87 is cited (`hvfhv.pretrend_uber_lyft_cell_weighted`). The "fee mattering for FHV" reading is withdrawn.

**Figure titles**, all checked against `results/figure_stats_phase4c.json`:

| Figure | Title numbers | Source |
|---|---|---|
| F6 | yellow p = 2e−17, Uber + Lyft p = 2e−18 | `did_by_channel.json` 1.57e−17; `fhv_did.json` 2.27e−18 |
| F6a | +105.0k / −5.9k / +42.8k / +0.7k | `d1` |
| F6b | 22 / 71 / 91 / 89% | `d1.zone_median_app_share` |
| F6c | 0.90 [0.74, 1.06], 1.18 [1.00, 1.35] | `d2` |
| F6d | −1.12, 0.68 [0.09, 1.23], pre-trend p 2.3e−7 | `d3` |
| F6e | +11.3 / +11.1 / +8.1 / +10.6 pp, +3.0 pp, p = 4e−27 | `d5b` |

**README:** no Phase-6 numbers (make targets only). `reports/analysis.md` does not exist yet (Phase 7).

**Not traced exactly (non-blocking).** These are in `DECISIONS.md`, which is outside the trace list, but carry them into Phase 7:
- The D5b entry says the event study is "+2 to +6 pp after". In `app_share_step_event_study.csv` the post coefficients range from +0.3 to +6.6 pp. Weeks 12, 14 and 15 are +1.8, +0.3 and +1.1 pp, so 22 of 25 post weeks are at or above +2 pp.
- When this enters `reports/analysis.md`, quote the exact range.

## Method sanity

- **D2 repeated cross-fitting.**
  - `DoubleMLPLPR(n_rep=25)` is seeded through the global numpy RNG before construction, and the LGBM learners are seeded.
  - The reported θ is DoubleML's median over the 25 draws. DoubleML's median aggregation also widens the SE by the dispersion of the draws.
  - The full set of draws is saved, so no single seed now decides which side of the 0.5 bound the estimate falls on.
- **C6, D3, D5, D5b.** Unchanged since round 2 and correct as reviewed there. Gates are applied as pre-registered, and all failing pre-trend tests are reported, not tuned away.
- **Leakage.** `tests/test_leakage.py` passes. This phase adds no forecasting.

## Figures

All six F6 PNGs were opened. Palette is consistent with `style.py`:
- CBD red; non-CBD grey; `comparison` purple for FHV and Curb; app teal.

| Figure | Finding |
|---|---|
| F6 | y-label "CBD vs control (%)" fits the axis; nothing overlaps the title or caption; the reference week is in the caption. The legend could be direct labels (minor, carried over; not required). |
| F6a | Policy line labelled in the CBD panel. Fine. |
| F6b | Fine. About 30% of the canvas is empty above and below the maps (layout only). |
| F6c | Legend reads "DoubleML panel (median of 25 fold draws)". Plotted values match the results. Fine. |
| F6d | Curb in purple, CMT in grey; excluded window shaded. No policy line needed (x starts 2025-06). |
| F6e | Pre-trend p in the title; labelled policy line in the left panel. Fine. |

Axis labels carry units, and every figure is readable at 7 in.

## Decisions check

- `incr.n_rep: 25` has a matching DECISIONS line: the round-2 P6 entry, item 3, with the rejected alternative "one seeded draw".
- The D2 entry states the superseded single-draw values (0.555, 0.522, 0.497).
- No new threshold, window or rule in the round-2 code lacks a DECISIONS line.

## Fix list

None.

## Escalation reasons

None. Round-2 items are all resolved, and no mandatory item was downgraded.

For Checkpoint 6, Stanley should see these results together:
- C6 stop (every FHV series fails pre-trends);
- D2 estimator disagreement and the failed lead placebo in Manhattan non-CBD;
- D3 not identified;
- D5 gate closed;
- D5b step citywide;
- the per-week restatement of Amendment 4's motivation (CBD +15.6% per week, `channel_restatement.json`).

The storyline decision is outside reviewer bounds and belongs to Checkpoint 6.

## Amendments made

None.
