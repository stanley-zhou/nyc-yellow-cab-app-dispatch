# Phase 4 review (round 3): how much did demand change (causal), with Amendment 3 C1/C2/C4/C5

Reviewer: phase-reviewer subagent (fresh context), 2026-11-11. Commit reviewed: fa8c7ab (working tree clean). C3 (`07f_synth_control.py`) has not been run and is **not** reviewed. C6 has not started. Earlier rounds: `reviews/phase_4_round1.md` (ESCALATE, Checkpoint 4) and `reviews/phase_4_round2.md` (FIX). This is the second fix round.

## Verdict

**ESCALATE.**

All 13 round-2 fix items were applied, and every number traces to `results/`. The remaining problem is the headline demand wording.

The Builder recorded the C2 inference question as "settled" (DECISIONS l.233) and wrote "no detectable change" in the README and the F4 title. The evidence the Builder saved does not support settling it:

1. **Time-only placebos.** These keep the real CBD/donut assignment and move the fake policy date. The real estimate −0.0534 is outside **all 54** of them (`power_mde.json → time_only_real_assignment.pre_volume_weighted.share_abs_ge_abs_beta = 0.0`). The README and the F4 title give the placebo range (−3.8% to +2.8%) next to "no detectable change" but never say that the estimate lies outside it. DECISIONS l.233 leaves out the share entirely.
2. **The "below the time-only MDE" argument is a statistical error.** An MDE is a power quantity, not a test threshold. With the Builder's own sd of 0.0196, |β̂| = 0.0534 is above the 5% critical value 1.96 × 0.0196 = 0.0384. Measured from the placebo mean (−0.0124), z = −2.1.
3. **The placebos are not fitted on the reported specification.** `estimate_w` / `quick_beta` in `scripts/07b_demand.py` fit them **without** the weather × treated controls that the reported −0.0534 includes. Reviewer diagnostic, using the Builder's own functions on the reported specification (scratchpad, not a result):
   - mean −0.0200, sd **0.0109**, range **−0.0360 to +0.0075**;
   - implied MDE ≈ 0.031 (3.1%);
   - 0 of 54 placebos as large as |β̂|.

   The 2024-04-07 placebo is −0.0360 with weather and −0.0082 without, which is why round 2 and the saved file disagree.
4. **The pre-specified A2 permutation** (Amendment 1: "the primary placebo check") also gives MDE 3.4% < |β̂| and 0 of 500.

Only the clustered CI (p = 0.21) supports "no detectable change". Against it:
- every placebo-based inference places −5.2% in or beyond the tail;
- the weighted pre-trend test rejects (F* p = 1.6e−17);
- the estimate shrinks to −1.0% with the full Manhattan non-CBD control.

Stanley's prescribed C2 phrase ("no detectable change; 95% CI …; permutation MDE = X%") becomes self-contradictory with X = 3.4%. `metric_framework.csv` row 1 now prints exactly that: "no detectable change; permutation MDE 0.0330" beside −0.0534.

Choosing which inference governs the primary result, and what the headline says, is a storyline and metric decision outside the amendment bounds. It needs Stanley. A third rewording by the Builder is not the way to settle it.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| Panel 2023-01 → 2026-09, log1p + levels, balanced | MET | `did_static.json → main` (63 × 142 = 8,946); `tests/test_demand_panel.py`; levels `pct` now null |
| Treatment `is_cbd`; donut primary; full Manhattan + B+Q robustness | MET | both specs: `did_static.json → control_*`, `pre_volume_weighted_control_*` (−0.0098; −0.7184; with airports −0.0758) |
| Zone FE, week FE, weather, SE by zone, formula recorded | MET | `formula`, `vcov: CRV1 by zone_id` in every estimate |
| Reference week before 2025-01-05; monthly + weekly bins | MET | `event_study.csv`, `placebo.json → event_study_week` (test not computable, documented) |
| Static β with 95% CI; persistence | MET | weighted −0.0534 [−0.1367, 0.0299]; −0.0150 / −0.0255 / −0.0965 |
| Pre-trend joint test saved | MET (rejects) | `placebo.json`: equal-weight F* p = 2.7e−10; weighted F* p = 1.6e−17 |
| Placebo in time 2024-01-07 | MET (both specs; both significant) | equal −0.1487 [−0.2396, −0.0578]; weighted −0.0279 [−0.0528, −0.0030] |
| Leave-one-zone-out + plot | MET | `leave_one_out.csv`, F4i |
| A5 vendors + PLAN-literal filters | MET (both specs) | weighted −0.0496 / −0.0421 |
| Heterogeneity table | MET | `heterogeneity.csv`, both specs |
| Confounders; spillover stated | MET | DECISIONS l.206 |
| Forecast counterfactual vs event-study path | MET | `counterfactual.csv`, F4d |
| A1 metric framework incl. weekly fee revenue | MET | `metric_framework.csv` (fee note now in dollars) |
| A2 permutation + F4e | MET (as specified) | `power_mde.json`; `demand_placebo_draws.csv` |
| A3 / B5 trade-off | MET | `elasticity_tradeoff.json` |
| B1–B5 speed | MET | `speed_did.json`, `speed_power.json` |
| C1 app dispatch | MET | `app_dispatch_*` |
| C2 weighted primary, MDE, zone trends, wording | **NOT MET: needs a human decision** | wording rests on a placebo distribution that is fitted off-spec and misread (Verdict items 1–4) |
| C4 speed vs Brooklyn/Queens | MET (expected direction not met; reported) | `speed_did_outer.json` |
| C5 three shocks | MET | `shock_comparison.json`, F3b |
| All PLAN figures render | MET (defects below) | F4, F4b(+html), F4c, F4d, plus F4e/F4f/F4g/F4i |
| Report text: effect with CI and design in one sentence | PARTIAL | `README.md` l.4–10 has the sentence, but its inference clause is the disputed one |

## Test output

- `ruff check .`: All checks passed!
- `make verify PHASE=4` (1m38s): ruff PASS, pytest PASS (117 passed), no_skips PASS (0 skipped), dbt_test PASS (`PASS=56 WARN=0 ERROR=0 SKIP=0`), outputs PASS (36 files).
- `pytest -q tests/test_leakage.py`: 23 passed. It poisons values at and after the origin and asserts unchanged forecasts. It is not a placeholder.
- Grep `lag_1 | shift(1) | rolling(4)`: only `features.py` l.65/66/78, which shift daily same-hour series (≥ 24 h, cleared in Phase 2).

## Number trace

The commit message has no numbers.

| Number | Source | OK |
|---|---|---|
| README −5.2% [−12.8%, +3.0%]; −0.053 [−0.137, +0.030] | `did_static.json → pre_volume_weighted_not_preregistered` | yes |
| README "38 CBD vs 25 donut" | `did_static.json → n_treated_zones / n_control_zones` | yes |
| README / F4 "−3.8% to +2.8%" | expm1 of `placebo_time_distribution.csv` min −0.039021 / max 0.0277584 (`figure_stats_phase4.json → demand_weighted_time_placebo_range`) | yes (but placebos are off-spec; see Verdict) |
| README −1.0% full Manhattan | `did_static.json → pre_volume_weighted_control_manhattan_non_cbd` −0.009776 | yes |
| README 103 zones, 99.04%; 48%, 0.4816 / 0.4635 / 0.4488 | `modeled_zones.json`, `citywide_yearly.csv` | yes |
| DECISIONS l.233: mean −0.0124, sd 0.0196, MDE 0.0548 / 5.6%, range, equal-weight mean −0.1192 (all negative) | `power_mde.json → time_only_real_assignment`, `placebo_time_distribution.csv` (0 non-negative) | yes |
| DECISIONS l.233: −0.0279, −0.0529, −0.0496, −0.0421, −0.0098, −0.7184, −0.0758 | `placebo.json`, `did_static.json` | yes |
| DECISIONS l.233 size simulation: 56% / 34% / 9.5% / 1.5% / 0.00071 | `pretrend_test_size.json` (38/25) | yes |
| F4c 10 of 15 / 4 of 8; F4d +2.0% / −40.5% / −11.3%; F4e; F4f; F4i | `figure_stats_phase4.json` (verified in round 2, unchanged inputs) | yes |
| `metric_framework.csv` row 1 "no detectable change; permutation MDE 0.0330" | `power_mde.json → pre_volume_weighted.mde` | traceable, but contradicts itself (MDE < \|β̂\| = 0.0534) |

No untraceable numbers.

## Method sanity (Phase 4)

- Formula, zone and week FE, CRV1 by zone, reference week 2024-12-29, CI, heterogeneity, placebo, alternative controls and LOO are all saved as numbers, for both specs.
- **Off-spec placebos.** The time-only and A2 placebos (`quick_beta`, `estimate_w`) omit weather × treated. The real estimate includes it. Reviewer diagnostic (a scratch file `tp_weather.csv`, not kept), one row per fake week:

  | Weighted time-only placebos | mean | sd | min | max | share ≥ \|β̂\| |
  |---|---|---|---|---|---|
  | saved (no weather) | −0.0124 | 0.0196 | −0.0390 | +0.0278 | 0/54 |
  | reported spec (weather × treated) | −0.0200 | 0.0109 | −0.0360 | +0.0075 | 0/54 |

  Lag-1 autocorrelation of the 54 draws is 0.98 / 0.96: there are only a few independent draws. Neither distribution supports a precise tail probability. Both put β̂ outside every draw.
- The "MDE > |β̂| ⇒ not detectable" reasoning in DECISIONS l.233 is invalid (Verdict item 2).
- Zone-trend caveat now stated (`metric_framework.csv`, DECISIONS l.233 (4)). OK.
- `pretrend_size` design corrected to 38/25 and rerun. OK.
- Process: Phase 3 is still formally ESCALATE (`reviews/phase_3.md`). F4d and C5 depend on it.

## Figures

- **F4.** Policy line, zero line, pre tint and % axis are present. Defects:
  - the title states "no detectable change" (disputed);
  - the title puts the placebo range beside the estimate without saying the estimate lies outside it;
  - the title does not mention the visibly failing pre-period (monthly coefficients −15% … +8%).

  The y-label "Effect on CBD pickups (%)" is acceptable with the footnote.
- **F4f.** Now two lines and coloured by control, but it misuses the semantic palette (`scripts/09_figures.py` l.299–302):
  - the **pre-registered** donut series is drawn in `non_cbd` grey, the de-emphasised control colour;
  - the C4 robustness series takes the `cbd` accent.

  Both series are CBD effects. The primary series should carry the accent, and the comparison series a distinct non-semantic colour or marker.
- **F4d.** The volume-weighted path (now the primary spec) is drawn in the light "pre" tint across the whole axis. That tint means "before the policy" everywhere else (`style.py`).
- **F4c.** OK. One criterion (CI includes zero) for both outcomes; axes labelled.
- **F4e.** OK as the A2 figure.
- **F4b / F4b.html.** The colour quantile is now in config and both versions use the same zones. OK.
- **F4g / F4i.** Unchanged, OK.

## Decisions check

- Round-2 items 1–9 and 13 are recorded (DECISIONS l.233).
- Missing:
  1. No line records that the time-only and A2 placebos are estimated **without** the weather × treated controls of the real estimate, or why.
  2. No line explains the choice to use the time-only MDE (5.6%) instead of the pre-specified A2 MDE (3.4%) in the inference argument.
- Hex literals at `viz/figures.py` l.133 (vendor colours, F1c, Phase 1) contradict DECISIONS l.57 ("no figure code uses hex literals"). This is pre-existing and not a Phase-4 item; fix in Phase 7.
- README make-target table runs ahead of the code:
  - it lists `07f` under `causal`, but the Makefile `causal` target does not run `07f`;
  - it lists F4h under `figures`, but F4h does not exist (C3 has not been run).

## Fix list (apply regardless of Stanley's decision)

1. In `scripts/07b_demand.py`, estimate the time-only real-assignment placebos with the **same specification as the reported estimate** (weather × treated; use `did(...)`, not `quick_beta`). Either do the same for the A2 permutation, or save the real estimate without weather beside it as the comparison. Save both variants to `results/placebo_time_distribution.csv` and `results/power_mde.json`, and record the rule in `DECISIONS.md`.
2. In `DECISIONS.md` l.233, remove the claim that "below the time-only MDE" supports "no detectable change". State the share of time-only placebos as large as |β̂| (0/54) and the dependence of the draws (lag-1 autocorrelation ≈ 0.97).
3. In `README.md` (status block) and the F4 title (`scripts/09_figures.py`), do not juxtapose the placebo range with "no detectable change" unless you also state that the estimate lies outside it. Use the wording Stanley chooses (see Escalation).
4. In `scripts/07c_metrics.py`, change the `metric_framework.csv` primary-row note so it does not print "no detectable change" beside an MDE smaller than |β̂| without comment.
5. In `scripts/09_figures.py` (F4f), give the pre-registered donut series the `cbd` accent and the Brooklyn/Queens series a distinct non-semantic colour or marker. In F4d, draw the volume-weighted path in a full colour, not the "pre" tint.
6. In `README.md`, list `07f` and F4h only once the Makefile runs `07f` and F4h exists, or mark them "(C3, pending)".

## Escalation reasons

1. **The result conflicts with the prescribed C2 wording and needs a human decision.**
   - The pre-specified A2 permutation places the primary weighted estimate outside all 500 placebos (MDE 3.4%).
   - The real-assignment time-only placebos place it outside all 54, with or without weather controls (implied MDE 3.1% on the reported spec).
   - The clustered CI (p = 0.21) does not reject.
   - Pre-trends fail, and the estimate is −1.0% with the full Manhattan control.

   "No detectable change; permutation MDE = 3.4%" is internally inconsistent. Which inference governs, and whether the headline becomes "inconclusive: the design cannot separate a ~5% decline from differential trends", is a storyline and metric choice outside the amendment bounds.
2. **The Builder settled a question it had correctly reserved for Checkpoint 6** (DECISIONS l.231), using an off-spec placebo and an MDE-as-threshold argument. The inference-wording item (round-2 Fix 3) is therefore still defective after its fix round.

Options for Stanley, from the evidence:
- (a) Headline "inconclusive", reporting the clustered CI, both placebo results and the control sensitivity side by side.
- (b) Keep "no detectable change by the clustered CI", with an explicit statement that the placebo-based inferences disagree and why they may understate noise. This needs a specific, fixed reason.
- (c) Defer the demand headline to C3 (synthetic control, with its own in-space placebos) and treat the DiD as descriptive.

Per CLAUDE.md the run stops here. Whether C3 proceeds before this decision is for Stanley. In any case, no demand wording is final until he decides.

## Amendments made

None. The open issue is an inference and wording choice for the primary outcome. That is outside the reviewer's amendment bounds.

## Closing note (2026-11-13, Stanley's ruling — PLAN Amendment 5)

Phase 4 is **closed**. The ESCALATE verdict above is resolved by Stanley's rulings: option (a) "inconclusive / not identified" at the round-3 escalation (DECISIONS 2026-11-12), confirmed at Checkpoint 6 (Amendment 5). Results are reported as found. The review is not re-run.
