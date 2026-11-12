# Phase 4 review (round 2): how much did demand change (causal), with Amendment 3 C1/C4/C5/C2

Reviewer: phase-reviewer subagent (fresh context), 2026-11-11. Commit reviewed: e3389e1, plus 8e96d05, c63a207 and cf4bcf2 for C4, C5 and C1. The working tree also holds uncommitted C3 work: `scripts/07f_synth_control.py` and edits to `config/project.yaml`, `pyproject.toml`, `09_figures.py`, `viz/figures.py` and `DECISIONS.md`. That work is **not** reviewed here. The test and verify runs below include it.

## Verdict

**FIX.**

- All round-1 fix items are done.
- The tooling is green.
- The DoD sentence now exists.

There are two kinds of open item. First, a substantive gap: C2 made the **pre-volume-weighted** DiD the primary estimate, but most of the PLAN Phase-4 checks were still run only on the equal-weight spec. Second, several smaller defects.

I ran the missing checks for the primary spec as a reviewer diagnostic (below, not saved to `results/`). They answer the question the Builder raised in DECISIONS l.231 (clustered CI vs permutation):

- The random-zone permutation is **not** a valid null for the real CBD/donut assignment.
- With no policy at all, the real assignment produces placebo estimates in the permutation's extreme tail or beyond it.

So the wording "CI includes 0, yet beyond 100% of placebos" in the README and the F4 title presents an artefact as counter-evidence. The Builder must save these checks and fix the wording.

This does not contradict the Amendment-3 storyline ("no detectable change"); it supports it. So it is a FIX, not an ESCALATE. The final wording is still Stanley's at Checkpoint 6.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| Panel 2023-01 → 2026-09, log1p + levels, balanced | MET | `did_static.json → main` n_obs 8,946 = 63 × 142; `tests/test_demand_panel.py` (2 tests, pass); levels +440.4 [9.8, 871.0] |
| Treatment `is_cbd`; donut primary; full Manhattan non-CBD + B+Q robustness | PARTIAL | Equal-weight: all three are in `did_static.json`. **Primary (weighted):** B+Q exists only as the "airports" rows in `heterogeneity.csv` (−0.7184; with airports −0.0758). The full Manhattan non-CBD control is not computed. Reviewer diagnostic: **−0.0098 [−0.0609, +0.0413]**. |
| Zone FE, week FE, weather, SE clustered by zone, formula recorded | MET | every estimate carries `formula`, `vcov: CRV1 by zone_id`, `weights` |
| Reference week before 2025-01-05; monthly bins (figure) + weekly bins (appendix) | MET | `event_study.csv` main month/week; weighted month |
| Static β with 95% CI; persistence H1/H2/2026 | MET | weighted −0.0534 [−0.1367, 0.0299]; −0.0150 / −0.0255 / −0.0965 |
| Pre-trend joint test saved | MET (rejects) | `placebo.json`: equal-weight F*(24,39) p = 2.7e−10; weighted F*(24,37) p = 1.6e−17 |
| Placebo in time 2024-01-07 saved | PARTIAL | Saved for equal weight only (−0.1487 [−0.2396, −0.0578]). **Missing for the primary spec.** Reviewer diagnostic: weighted **−0.0279 [−0.0528, −0.0030], p = 0.032** |
| Leave-one-zone-out + plot | MET | `leave_one_out.csv` (both specs), F4i |
| Vendors present throughout (A5) + PLAN-literal filters | PARTIAL | Equal-weight only (−0.4273, −0.4097). Not run for the primary spec. |
| Heterogeneity (hour band, weekday/weekend, dropoff, pass-through, distance tercile, airports) | MET | `heterogeneity.csv`, 38 rows, both specs |
| Confounders listed; spillover stated | MET | DECISIONS l.206 |
| Forecast counterfactual vs event-study path | MET | `counterfactual.csv`, F4d; computed in `causal/counterfactual.py`, tested by `tests/test_counterfactual.py` |
| A1 metric framework incl. weekly fee revenue | MET (one label bug) | `metric_framework.csv` guardrail row; `fee_revenue_weekly.csv` (90 complete weeks, mean $485,098). Its note mislabels a dollar figure as "CBD pickups" (see Fix 6). |
| A2 permutation + F4e | MET as specified; **interpretation invalid** (see Method sanity) | `power_mde.json` (both specs) |
| A3 elasticity / B5 trade-off | MET | `elasticity_tradeoff.json` |
| B1–B5 speed (incl. round-1 fix 6: placebo, alternative control, duration power) | MET | `speed_did.json → outcomes.*.placebo_in_time / control_manhattan_non_cbd`; `speed_power.json → by_control` |
| C1 app dispatch | MET | `app_dispatch_*.csv/json`, F4g |
| C2 weighted primary, weighted MDE, zone trends, wording | PARTIAL | Primary-spec checks missing (rows above). The zone-trend caveat is not stated with the result. The permutation wording is misleading. |
| C4 speed vs Brooklyn/Queens | MET (expected direction not met, reported) | `speed_did_outer.json` |
| C5 three shocks | MET | `shock_comparison.json`, F3b |
| All four PLAN figures render (+F4e/F4f/F4g/F4i) | MET (defects below) | |
| Report text states effect size with CI and design in one sentence | MET | `README.md` status block, citing `did_static.json` |

## Test output

- `ruff check .`: All checks passed!
- `make verify PHASE=4`: ruff PASS, pytest PASS (117 passed, 0 skipped), no_skips PASS, dbt_test PASS (`PASS=56 WARN=0 ERROR=0 SKIP=0`), outputs PASS (all 36 phase-4 files). Runtime 1m41s.
- `pytest -q tests/test_leakage.py` alone: 23 passed. It poisons future values and asserts the forecasts are unchanged; it is not a placeholder.
- `tests/test_demand_panel.py`, `test_counterfactual.py`, `test_causal.py`: 9 passed.
- Grep for `lag_1 | shift(1) | rolling(4)`: only `features.py` l.65/66/78, which shift daily same-hour series (≥ 24 h, reviewed in Phase 2). Nothing new.

## Number trace

The commit message has no numbers. README: −5.2% [−12.8%, +3.0%] = `did_static.json → pre_volume_weighted_not_preregistered.pct / pct_ci_*`; MDE 3.4% = `power_mde.json → pre_volume_weighted.mde_pct` 0.03354; 500 placebos = `n_draws`. OK.

| Number | Source | OK |
|---|---|---|
| F4: −5.2% [−12.8%, +3.0%], MDE 3.4%, "beyond 100%", p = 2e−17 | `figure_stats_phase4.json → demand_weighted`, `power_mde.json` (share 0.0), `placebo.json → …weighted….p_F_hotelling` 1.57e−17 | yes |
| F4b: −5.6% | `effect_map.cbd_median_relative` −0.05735 (expm1 = −5.57%) | yes |
| F4c: 10 of 15; 8 of 8 | recomputed from `heterogeneity.csv` (weighted, 15 subsets, 10 CIs span 0) and `speed_heterogeneity.csv` (8 donut speed rows, all coef > 0) | yes (wording issue, see Figures) |
| F4d: +2.0%, −40.5%, −11.3% | `counterfactual.mean_post_monthly_rel` 0.0198; mean of `event_study.csv` month k ≥ 0 = −0.5184 (main) and −0.1196 (weighted), expm1 → −40.5% / −11.3% (recomputed) | yes |
| F4e: −0.053 / 0% / 0.033; +0.019 / 6% / 0.028; −0.086 | `power_mde.json`, `speed_power.json`, `figure_stats_phase4.json → permutation` | yes |
| F4f: +1.9%, −4.0%, +15.4% → −2.6%, p = 6e−46 | `figure_stats_phase4.json → speed, speed_outer` (expm1 0.1435 = 15.4%, expm1 −0.0266 = −2.6%) | yes |
| F4i: −8.6% to −4.3%; −36.3% to −32.0% | `did_static.json → leave_one_zone_out*` (expm1 of −0.0900/−0.0443; −0.4509/−0.3853) | yes |
| F4g: 71–83%, 27%, r = 0.92 | `app_dispatch_summary.json` (C1; trace accepted from DECISIONS l.222, file present) | yes |
| DECISIONS l.231: sd 0.0118, range −0.033…+0.030, LOO −0.0900 (236) / −0.0443 (41), 10 of 15, subset CIs, pass-through +0.0990, zone trends +0.0415 / −0.2179 | `demand_placebo_draws.csv` (recomputed min −0.03264, max 0.02968), `did_static.json`, `heterogeneity.csv` | yes |
| DECISIONS l.217 zone growth (98.4 / 190.3 / 872.3 / 957.1 etc.) | `zone_growth.csv` (spot-checked zones 243, 236) | yes |
| `metric_framework.csv` fee row: "CBD pickups 370971 per week" | `fee_revenue_weekly.csv → fee_cbd_pickups` is **dollars of fee on CBD pickups**, not pickups | **mislabelled** |
| `did_static.json → levels.terms.treated_post.pct` = 1.8e+191 | expm1 of a level coefficient (440) | **garbage value in a results file** |
| C2 text "95% CI [−14%, +3%]" (Amendment 3) vs reported [−12.8%, +3.0%] | −0.1367 log points read as %; the Builder reports expm1. No DECISIONS line explains the difference | **missing decision line** |

## Method sanity (Phase 4)

- Formula, zone + week FE, CRV1 by zone, reference week 2024-12-29, effect with CI, heterogeneity table: all present.
- **Primary-spec checks were not re-run after C2.** Reviewer diagnostics, computed in the session scratchpad with `07b_demand.design/did/add_pre_volume_weight`. They are not results and must be regenerated by the Builder's code:

  | Weighted (primary) spec | β [95% CI] |
  |---|---|
  | as reported, donut control | −0.0534 [−0.1367, 0.0299] |
  | full Manhattan non-CBD control | −0.0098 [−0.0609, 0.0413] |
  | Brooklyn + Queens (no airports) | −0.7184 [−1.0461, −0.3906] (already in `heterogeneity.csv`, not reported as a robustness check) |
  | B+Q with airports | −0.0758 [−0.3188, 0.1673] (already in `heterogeneity.csv`) |
  | placebo in time 2024-01-07 (2023–2024 data) | −0.0279 [−0.0528, −0.0030], p = 0.032 |
  | placebo 2024-04-07 (2023-04 → 2025-01-04) | −0.0360 [−0.0612, −0.0108] |
  | placebo 2024-07-07 (2023-07 → 2025-01-04) | +0.0006 [−0.0177, 0.0190] |

  The primary estimate moves from −5.2% to −1.0% when the six straddle zones return to the control. The B+Q comparison swings by 64 log points depending on whether the airports are included. Both must be reported beside the primary estimate.
- **Permutation vs clustered CI (the Builder's open question).** With the real CBD/donut assignment and no policy, the 2024-01-07 placebo (−0.0279) is more extreme than 497 of the 500 random-zone weighted placebos. The 2024-04-07 placebo (−0.0360) is beyond all 500, the same "beyond 100%" status as the real estimate (`demand_placebo_draws.csv`, spec `pre_volume_weighted`, min −0.0326). The weighted event study shows the same: its pre-period monthly coefficients range −0.159 … +0.073 (`event_study.csv`), several times the permutation sd of 0.0118. The donut speed placebo in time (−0.0213, `speed_did.json`) tells the same story for speed. Random 38-of-69 Manhattan draws mix CBD and uptown zones and do not reproduce the spatially structured differential trend of the real assignment. So:
  - the A2 MDE (3.4%) understates the real noise of this design;
  - "outside all placebos" is not evidence of an effect.

  The clustered CI is the less wrong of the two, and itself rests on a failed pre-trend test (p = 1.6e−17).
- **Zone-specific trends** (`zone_trends_*`) are fitted on pre **and** post weeks, so they absorb part of any gradual effect. The docstring says this "is stated with the result", but it is stated in neither DECISIONS l.231 nor the `metric_framework.csv` note.
- The pre-trend size simulation still uses designs `[[38, 23], [20, 20]]` (`config causal.pretrend_size`). After the join fix the demand design has 38/25 clusters (63). DECISIONS l.227 calls 38/23 "the demand clusters". Stale.
- Weighted heterogeneity weights each subset by its own pre-period count, a reasonable choice that is recorded in the docstring and DECISIONS l.231.
- Process: Phase 3 is still formally un-passed (`reviews/phase_3.md` ESCALATE). F4d and C5 depend on it. Stanley's handling at Checkpoint 4 is not recorded as a Phase-3 verdict.

## Figures

- **F4** (event study, weighted): has the policy line, zero line, pre tint and post colour, % axis and a 2-line title. Defects:
  - (a) the title clause "yet beyond 100% of placebos" is misleading (Method sanity);
  - (b) the y-label "CBD pickups (%)" reads like a level. It should say it is the effect relative to the control and the reference week, e.g. "Effect on CBD pickups vs control (%)".
- **F4b**: extend arrow present, hatching from config, CBD outlined. Defect: the 0.95 colour quantile is hard-coded twice in `viz/figures.py` (l.408, l.440). The HTML version (l.440) computes the limit over **all** zones including the hatched < 50/wk ones, while the PNG and DECISIONS l.227 item 5 use the non-hatched zones only, so the two maps have different scales.
- **F4c**: titles wrapped, x-axes labelled. Defect: the title uses two different criteria, "CI includes zero" for demand and "positive (point estimate)" for speed. Under the same CI criterion, 4 of the 8 speed subsets include zero (t1, 00–06, 06–10, 10–16; `speed_heterogeneity.csv`). Use one criterion for both.
- **F4d**: OK. The pre-period (2024-H2) DiD points are shown and in-sample months are lighter.
- **F4e**: OK. Axes and ±MDE band are fine.
- **F4f**: defects:
  - (a) **colour encoding is ambiguous**: before the policy, the Brooklyn/Queens series uses the medium tint, which is the same colour the legend assigns to "vs donut control" after the policy. A reader will read the 2023–24 outer points as the donut series.
  - (b) the title is 3 lines. The same ≤ 2-line rule was applied to F4 in round 1.
- **F4g**: OK (sequential blues for a share, CBD outline, grey shades for control/other zones).
- **F4i**: OK.

## Decisions check

- Round-1 items 1–8: all recorded (DECISIONS l.227) and moved to config. OK.
- Missing or wrong:
  1. No line explains why the C2 CI is reported as [−12.8%, +3.0%] (expm1) when Stanley's phrase says [−14%, +3%] (log points).
  2. Zone-trend robustness: no line on the post-period-absorption caveat.
  3. `pretrend_size.designs` 38/23 described as "the demand clusters" (now 38/25).
  4. F4b colour quantile 0.95: in DECISIONS, but hard-coded in code (CLAUDE.md: no thresholds in code), and the HTML version contradicts the recorded rule.
  5. README (not DECISIONS) is stale:
     - the `causal` row says `07a`–`07d` but the Makefile also runs `07e`;
     - the `figures` row omits F3b, F4g and F4i;
     - the row for `shock` does not mention C5 (`06b`/per-event runs).

## Fix list

1. In `scripts/07b_demand.py`, run the PLAN checks on the primary (pre-volume-weighted) spec and save them in `results/did_static.json` / `results/placebo.json`:
   - full Manhattan non-CBD and Brooklyn + Queens (with and without airports) controls;
   - CMT + Curb vendors (A5);
   - PLAN-literal filters;
   - without weather;
   - placebo in time 2024-01-07.
2. In `scripts/07b_demand.py`, add a real-assignment placebo-in-time distribution for both specs: the CBD vs donut static DiD at every eligible fake week of the A2 window (same ≥ 26-week rule, pre-policy data only). Save it to `results/placebo.json` (or `results/demand_placebo_in_time.csv`) and report where the real estimate falls in it, beside the A2 random-zone result in `results/power_mde.json`. Record the rule in `DECISIONS.md`.
3. Rewrite the inference wording in `README.md`, the F4 title in `scripts/09_figures.py` and DECISIONS l.231 from the saved Fix-2 result. Do not present "beyond 100% of random-zone placebos" as evidence against the clustered CI when real-assignment pre-policy placebos reach the same region. Keep "no detectable change", never "no effect", and leave the final wording to Checkpoint 6.
4. Add a top-level `"primary": "pre_volume_weighted_not_preregistered"` key to `results/did_static.json` (written by `scripts/07b_demand.py`), so that `main` is not mistaken for the primary estimate.
5. In `src/taxi_shock/causal/did.py` (`DidResult.row`), set `pct`, `pct_ci_lo` and `pct_ci_hi` to null for non-log outcomes. `did_static.json → levels.pct` is currently 1.8e+191.
6. In `scripts/07c_metrics.py`, change the fee-revenue note from "CBD pickups … per week" to "fee on CBD pickups $… per week".
7. In `DECISIONS.md` and the `metric_framework.csv` note (`scripts/07c_metrics.py`), state that the zone-trend specifications fit the trends on pre and post weeks and can absorb a gradual effect.
8. In `config/project.yaml` (`causal.pretrend_size.designs`), change 38/23 to 38/25 and rerun `scripts/07d_pretrend_size.py`, or record in `DECISIONS.md` why 38/23 is kept. Correct the "demand clusters" wording in DECISIONS l.227 either way.
9. In `DECISIONS.md`, add a line on reporting the C2 CI as expm1 (−12.8%) instead of Stanley's log-point "−14%".
10. In `src/taxi_shock/viz/figures.py`, move the F4b colour quantile (0.95) into config, and make `f4b_effect_map_html` use the same non-hatched zone set as the PNG.
11. In `src/taxi_shock/viz/figures.py` / `scripts/09_figures.py`, fix F4f: use distinct colours or markers per control that do not change meaning between pre and post (e.g. tint for pre, but a different marker for the outer control), and shorten the title to ≤ 2 lines.
12. In `scripts/09_figures.py`, fix F4c's title to use one criterion for demand and speed (e.g. "95% CI excludes zero in n of N"). Fix F4's y-label to say it is an effect relative to the control.
13. In `README.md`, update the make-target table: `causal` runs `07a`–`07e`; `figures` includes F3b, F4g and F4i; `shock` includes the C5 runs.

## Escalation reasons

None for this round. Items for Stanley at Checkpoint 6 (already a human checkpoint), not blocking:

- (a) on reviewer evidence, the A2 random-zone MDE (3.4%) understates the noise of the CBD/donut design;
- (b) the primary estimate is sensitive to control choice (−5.2% donut vs −1.0% full Manhattan);
- (c) Phase 3's formal status is still ESCALATE.

## Amendments made

None. No numeric threshold, zone set, window, figure-layout or runtime change is indicated by the evidence. The issues are missing checks and wording, which the Builder can fix inside the plan.
