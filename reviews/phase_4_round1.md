# Phase 4 review — how much did demand change (causal)

Reviewer: phase-reviewer subagent (fresh context), 2026-11-09. Commit reviewed: 4762359 (with 34d52ab and 3150a56 for the Amendment-2 pre-registration).

## Verdict

**ESCALATE.** Checkpoint 4 is a mandatory human stop in any case. On top of that, both pre-registered primary outcomes fail their pre-registered pre-trend test by a wide margin. Under the reviewer rules that is an escalation trigger. The PLAN §6 response ("switch the primary control group") is a treatment/control change, which is outside the amendment bounds.

Separately, there is a real **bug** in the demand panel. It shifts the headline estimate and must be fixed before any number is shown to Stanley:
- `07b_demand.py` and `07c_metrics.py` inner-join `fct_weekly_zone_trip_stats`, which drops every zone-week with zero pickups.

There are also several FIX items (below). The Builder must apply them whatever Stanley decides.

Tooling is green: ruff, pytest (112 passed, 0 skipped), dbt test (56/56) and `make verify PHASE=4` all PASS.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| Panel 2023-01 → 2026-09, log1p(pickups) + levels | PARTIAL | `did_static.json → main / levels`. **The panel is not complete.** `load()` in `scripts/07b_demand.py` uses `join fct_weekly_zone_trip_stats` (inner), and that table has 100,425 rows against 106,515 in `fct_weekly_zone_panel`. As a result: zones 103 and 104 (donut control) drop out entirely; zone 105 keeps 28 of 195 weeks (only weeks with a pickup); zones 120, 128 and 153 lose weeks. The static sample is 8,538 rows, not 63 × 142 = 8,946. The design selects on the outcome. |
| Treatment `is_cbd`, donut primary control, full Manhattan non-CBD + B+Q robustness | MET (except the bug above) | `did_static.json`: `control_manhattan_non_cbd` −0.3720, `control_outer_boroughs` −0.7617. The B+Q run loses 114 zero-pickup zone-weeks through the same join (23,458 vs 23,572 rows). |
| Zone FE, week FE, weather controls, SE clustered by zone, formula recorded | MET | `formula: log1p_pickups ~ treated_post + tr_mean_temp_f + tr_total_precip_in \| zone_id + week_start`, `vcov: CRV1 by zone_id`. Weather × treated is justified by collinearity with week FE (DECISIONS l.204). |
| Reference = week before 2025-01-05; monthly bins (figure); weekly bins (appendix) | MET | `event_study.bins()` masks `event_week == −1` (week of 2024-12-29), tested in `test_bins_reference_week_and_months`. `event_study.csv` has `bins ∈ {month, week}`. |
| Static DiD with 95% CI; post split 2025-H1 / H2 / 2026 | MET | main −0.5047 [−0.7356, −0.2738]; persistence −0.3603 / −0.5257 / −0.5832 |
| Pre-trend joint test | MET (saved); **result rejects** | `placebo.json → pretrend_tests.event_study_month`: F(24,60) = 19.44, p = 4.4e−20, Hotelling F* p = 4.4e−11. Weekly test not computable (rank), documented. |
| Placebo in time 2024-01-07 on 2023–2024 | MET (saved); **result significant** | `placebo.json → placebo_in_time`: −0.1789 [−0.2681, −0.0897] |
| Leave-one-zone-out "(plot distribution)" | PARTIAL | Numbers are in `leave_one_out.csv` (61 rows, −0.5351 … −0.4629). **No plot of the distribution exists.** PLAN asks for one. |
| Alternative controls | MET | see above |
| Vendors present throughout (CMT + Curb) and PLAN-literal filters (CP1 / A5) | MET | −0.5055 [−0.7382, −0.2729]; −0.4798 [−0.7025, −0.2571] |
| Heterogeneity: hour band, weekday/weekend, dropoff-in-CBD, pass-through, distance tercile, airports | MET | `results/heterogeneity.csv` (19 rows; fare terciles added) |
| Confounders: TLC 2025 notices listed; spillover stated | MET | DECISIONS l.206 (states that the index page was 404; list is non-exhaustive) |
| Forecast counterfactual vs event-study path | MET | `counterfactual.csv`, F4d. In-sample 2024 months are flagged. |
| A1 metric framework | PARTIAL | `metric_framework.csv` has the primary, speed, spillover, mean-fare, pass-through and B4 rows. **The guardrail "weekly congestion-fee revenue" is missing.** Fee revenue exists only quarterly, in `elasticity_tradeoff.json`. |
| A2 permutation power (demand) + F4e | MET | `power_mde.json`: sd 0.0360, MDE 0.1008, share 0.000; `demand_placebo_draws.csv` |
| A3 elasticity + trade-off (B5 replaces lost fare) | MET | `elasticity_tradeoff.json` |
| A5 vendor robustness | MET | see above |
| B1 speed/duration: static + monthly ES, pair FE, week FE, clustered, donut | MET | `speed_did.json`, `speed_event_study.csv` |
| B1 speed: placebo + alternative-control robustness + A2-style power | **PARTIAL** | Missing: (a) no placebo-in-time for speed/duration; (b) no alternative control for speed (e.g. full Manhattan non-CBD with the donut zones, or the treated-pair definition against B+Q-internal pairs); (c) permutation power only for speed, **not for duration** (`speed_power.json` has `outcome: log_mean_speed_mph` only). |
| B2 entering / leaving / passing-through; hour bands | MET | `entering_cbd`, `leaving_cbd`; `passing_through: "not identifiable…"`; `speed_heterogeneity.csv` |
| B3 terciles on 2024 quantiles + distance control; exclusions by month and group | MET | `distance_control`, dist_tercile rows, `speed_exclusions.csv` |
| B4 / B5 | MET | `metric_framework.csv` rows; `b5_rider_tradeoff`; NBER comparison in DECISIONS l.207/214 |
| Outputs listed in PLAN Phase 4 | MET | `make verify PHASE=4` outputs PASS |
| DoD: pre-trend test and placebo saved | MET | |
| DoD: all four figures render | MET (with defects, see Figures) | F4, F4b (+ html), F4c, F4d, plus F4e, F4f |
| DoD: **report text states effect size with CI and the design in one sentence** | **NOT MET** | No `reports/analysis.md` and no results paragraph anywhere. The README says "no wording of findings before Checkpoint 4". Which estimate to state is now a human decision (see Escalation), so this cannot be completed by the Builder alone. |

## Test output

- `ruff check .` → `All checks passed!`
- `pytest -q` (via verify) → 112 passed, 0 skipped. Only warnings: pandas `inplace` deprecation inside pyfixest.
- `dbt test` → `PASS=56 WARN=0 ERROR=0 SKIP=0`. This includes the new `assert_speed_sample_matches_trips` and `assert_trip_stats_match_weekly`.
- `make verify PHASE=4` → ruff PASS, pytest PASS, no_skips PASS, dbt_test PASS, outputs PASS (26 files).
- `pytest -q tests/test_leakage.py` alone → 23 passed. It poisons future pickups with 1e6/NaN and exogenous data beyond the target day, and asserts identical forecasts. The power checks show that past poisoning changes the forecasts. Not a placeholder.
- Grep `lag_1|shift(1)|rolling(4)`: only `features.py` daily `.shift(1)` on same-hour day series (≥ 24 h; reviewed in Phase 2). Nothing new in Phase 4.
- `tests/test_causal.py` checks recovery of a known effect, flat pre-trends, a planted pre-trend being detected, the reference week, and the placebo helpers. **Missing:** a test that the estimation panel is balanced (every zone × every complete week, zeros included). Such a test would have caught the inner-join bug.

## Number trace

The commit message and README contain no Phase-4 numbers. Figure titles all trace to `results/figure_stats_phase4.json`:

| Number | Source | OK |
|---|---|---|
| F4: +3.5% / −12.8% / −47.2%, p = 4e−20 | `figure_stats_phase4.json → demand_mean_monthly_coef` (expm1 of 0.0343 / −0.1371 / −0.6395), `demand_pretrend_p_F`. I recomputed −0.6395 from `event_study.csv` (main, month, k ≥ 0). | yes |
| F4b: −5.6% | `effect_map.cbd_median_relative` −0.05735 | yes |
| F4c: 15 of 15, 8 of 8 | `heterogeneity` counts; matches `heterogeneity.csv` and `speed_heterogeneity.csv` | yes |
| F4d: +2.0%, −47.2%, −11.3% | `counterfactual.mean_post_monthly_rel` 0.01983 (recomputed from `counterfactual.csv`), `did_weighted_post_mean` −0.1196 | yes |
| F4e: −0.505, 100% of 500, MDE 0.101; +0.019, 6.4%, 0.028 | `power_mde.json`, `speed_power.json` | yes |
| F4f: +1.9% [+0.3%, +3.6%], −2.4%, p = 1e−32 | `figure_stats_phase4.json → speed` | yes |
| DECISIONS l.205 (pairs 1,444/485, 72,448,465 trips; +0.0190, −0.0243, H1/H2/2026; ES k = −24/−12/0/12 and Dec-2024 bin) | `speed_did.json`, `speed_event_study.csv` | yes |
| DECISIONS l.208: β, levels, F, placebo | `did_static.json`, `placebo.json` | yes |
| DECISIONS l.208: CBD +11.6%, Manhattan non-CBD +13.6% | derivable from `effect_map.csv` (Σpost/Σpre by is_cbd) | yes (derived) |
| DECISIONS l.208: **Washington Heights North 98 → 190 → 872, Inwood 40 → 81 → 380, Central Harlem North 599 → 1,077 → 2,762, UES North 30,081 → 32,545 → 35,335** (2023 / 2024 / 2025 means) | Only the 2024 values roughly match `effect_map.pre_mean_weekly` (52 pre weeks). **The 2023 and calendar-2025 means are in no `results/` file.** `effect_map.post_mean_weekly` is 908 / 392 / 2,891 / 34,609, not 872 / 380 / 2,762 / 35,335. | **NO** |
| DECISIONS l.208: "carried by the incumbent vendors CMT and Curb (not Helix)" for uptown zones | No zone-level vendor result file | **NO** |
| DECISIONS l.209: control mean +0.71, high-volume zones ≈ −0.65 | `effect_map.csv` (`control_mean_log_change` 0.7102; zones with pre > 5,000/wk have mean `relative_log_change` −0.61) | yes (approx.) |
| DECISIONS l.210 (60%, 80%, 13%, 8.5%, p-values, 0.0018) | `pretrend_test_size.json`, `placebo.json`, `speed_did.json` | yes |
| DECISIONS l.212 / 213 / 214 / 215 | `did_static.json`, `power_mde.json`, `heterogeneity.csv`, `speed_heterogeneity.csv`, `metric_framework.csv`, `elasticity_tradeoff.json`, `counterfactual.csv`, `speed_exclusions.csv` (2.07% / 0.65% / 1.42% / 0.007% and group shares recomputed) | yes |

**Caveat:** every demand number in DECISIONS l.208, l.212–215 and in the figure titles was produced on the unbalanced panel and will change after the join fix. Reviewer diagnostic only, not a result: on the balanced `fct_weekly_zone_panel` the main estimate is −0.4253 [−0.6488, −0.2019] with zones 103/104 included, and −0.4788 [−0.7069, −0.2507] with them dropped. These were computed in the session scratchpad with `07b_demand.design/did`.

## Method sanity (Phase 4)

- Formula string recorded: yes (every estimate carries `formula`, `vcov`, `weights`).
- Zone and week FE: yes. Speed uses pair FE + week FE, two-way clustered pu/do zone as pre-registered (DECISIONS l.204), with one-way reported beside it.
- SE clustered by zone: yes (61 clusters; Hotelling small-sample correction added, with its size simulated in `pretrend_test_size.json`).
- Reference week = 2024-12-29 week (the week before 2025-01-05): yes. Note that it is a holiday week. DECISIONS l.205 itself shows the speed gap at its seasonal low there. A single atypical reference week does not change the joint test, but it shifts every plotted coefficient. Keep this in mind when the figure is read.
- Pre-trend, placebo, alternative control, LOO saved as numbers: yes. LOO plot missing.
- Effect with CI: yes in JSON. No report sentence.
- Heterogeneity table: yes. `causal.unit` in config says "zone_day for heterogeneity", but heterogeneity runs on zone-week with no DECISIONS line.
- **Substantive findings (reported honestly by the Builder; they drive the escalation):**
  - Demand: the log1p equal-weight β (−0.505) has the opposite sign to levels (+317, CI spans 0). It shrinks to −0.053 [−0.137, 0.030] when weighted by pre-volume, which is not pre-registered. The placebo in time is −0.179 and significant. The pre-trend test rejects under both weightings (weighted F* p = 1.6e−17).
  - Speed: +0.0190 [0.0028, 0.0351]. The effect sits entirely in 2025-H1 (+0.0557; H2 +0.0009, 2026 +0.0049), and the event study shows a January spike in **every** year (k = −24, −12, 0, 12). With treated × month (not pre-registered) speed is +0.0119 [−0.0040, 0.0279]. The permutation share is 6.4% > 5% and β is below the MDE of 0.0275.
  - The counterfactual (+2.0%) contradicts both DiD paths.
- Permutation design: 38 random Manhattan zones (the pool includes the real CBD, which is fine pre-policy). Fake week has ≥ 26 weeks on each side. Matches A2.
- Fee revenue: quarters are assigned by `week_start`. Weeks that straddle a quarter boundary go to the earlier quarter, and the partial last week (2026-09-27) is included. No decision line covers this.

## Figures

- **F4** (7 × 4.2): coefficients ± CI, zero line, policy line, pre tint / post full CBD colour. That complies with PLAN's "nothing else". Defect: the title reports % (expm1 of mean log coefficient: −47.2%) while the y-axis is "log pts × 100" (points near −65). A reader cannot reconcile the two. Use one unit. The title is 3 lines at 7 in; shorten it.
- **F4b**: diverging blue–white–red centred at 0 with the CBD outlined, as required. Defects:
  - The colour limit is the 95th percentile of |v| (≈ 0.8) while the data reach +1.39 (Inwood, Washington Heights North, Inwood Hill Park, Highbridge Park). Values are clipped silently: the colourbar has no `extend` arrow and the note does not mention it.
  - The hatch threshold of 50/wk is hard-coded in `scripts/09_figures.py` (`min_pre = 50.0`).
  - The 95th-percentile limit has no DECISIONS line.
  - The HTML hover has zone, pre/post means, change and relative change. The CI is omitted, with a stated reason.
- **F4c**: small multiples. Defects:
  - The panel titles "Demand: CBD pickups by dropoff" and "Demand: distance tercile" run into each other.
  - No x-axis carries a label or unit; "%" appears only in the footnote.
- **F4d**: units on y, policy line, direct labels, in-sample months lighter. OK. The footnote says the counterfactual has no control group only implicitly. Acceptable.
- **F4e**: axes labelled, ±MDE band, real estimate marked. OK. Title wording "lies beyond 100% of 500 placebos" is awkward ("no placebo as large").
- **F4f**: two panels, own y-axes, policy line on both, units. OK. The title statement "the monthly gap to the control is seasonal" is supported by the plotted January peaks.
- Missing: a leave-one-zone-out distribution plot (PLAN).

## Decisions check

Present: pre-registration (timestamped before the results), the 65 mph cap, two-way clustering, terciles, weather × treated, not-pre-registered additions labelled, pre-volume weighting, F4b reference, size simulation, TLC notices, NBER benchmark, ES implementation notes.

Missing or wrong:
1. `causal.permutation.min_side_weeks: 26` (and the placebo static window of `pre_weeks: 52` inside the permutation): no DECISIONS line.
2. `scripts/07d_pretrend_size.py`: AR(1) rho 0.5, innovation sd 0.05, 200 reps and the 20/20 comparison design are hard-coded in the script, not in config, and are not in DECISIONS.
3. `scripts/07c_metrics.py`: `FEE = 0.75` and `VOT = [20, 30, 40]` are hard-coded (CLAUDE.md: no thresholds in code).
4. `scripts/09_figures.py`: `min_pre = 50.0` is hard-coded. The DECISIONS line mentions it but gives no reason and no rejected alternative.
5. F4b colour limit (95th percentile of |v|): no line.
6. Fee revenue quarter assignment by week start, with the partial last week included: no line.
7. Heterogeneity on zone-week instead of config's `zone_day for heterogeneity`: no line.
8. DECISIONS l.208 says the donut control has "23 zones with pickups; 103/104 never have any". This is wrong on both counts. Zone 104 has 1 pickup. The two zones were dropped by the inner join, not by any rule. Zone 105 (187 pickups in 405 weeks) is kept on 28 weeks only.

## Fix list

1. In `scripts/07b_demand.py` (`load`) and `scripts/07c_metrics.py` (`guardrails`), change the `fct_weekly_zone_trip_stats` join to a LEFT join from `fct_weekly_zone_panel` and fill counts/sums with 0. Make the estimation panel balanced (every zone × every complete week). Then decide by a recorded rule whether never-served zones (103, 104, 105) belong in the donut control. Write the rule in `DECISIONS.md` and the `causal.control_groups` config, and correct DECISIONS l.208.
2. Add a test in `tests/test_causal.py` (or a new `tests/test_causal_panel.py`) asserting that the demand design panel has n_zones × n_weeks rows with explicit zeros for both the donut and the B+Q designs. It would have failed on the current code.
3. Re-run `make causal` and `make figures` after fix 1. Update every demand number in `DECISIONS.md` (l.208, 212–215) and the figure titles from the regenerated `results/`.
4. Save the uptown-growth diagnosis to `results/`, e.g. `results/control_growth_diagnosis.csv` with per-zone yearly mean weekly pickups 2023/2024/2025 and vendor shares, written by `scripts/07b_demand.py`. Cite that file in DECISIONS l.208, or delete the untraced numbers and the CMT/Curb claim.
5. Add a leave-one-zone-out distribution plot to `src/taxi_shock/viz/figures.py` / `scripts/09_figures.py` (e.g. a panel in F4e or `F4g_leave_one_out.png`), and list it in `config/phase_outputs.yaml`.
6. Complete B1 in `scripts/07a_speed.py`:
   - placebo-in-time for speed and duration (fake 2024-01-07, 2023–2024 data);
   - an alternative-control speed DiD (at least the full Manhattan non-CBD control);
   - the permutation power analysis for `log_mean_duration_min` as well as speed.
   Save all three in `results/speed_did.json` / `results/speed_power.json`.
7. Add a weekly congestion-fee revenue guardrail to `results/metric_framework.csv` (A1), e.g. the weekly series in a new `results/fee_revenue_weekly.csv` with a summary row in the framework, produced by `scripts/07c_metrics.py`.
8. Move `FEE`, `VOT` (`scripts/07c_metrics.py`), `min_pre` (`scripts/09_figures.py`) and the simulation parameters (`scripts/07d_pretrend_size.py`) into `config/project.yaml`. Add a DECISIONS line for each item in "Decisions check" 1–7.
9. Fix F4b in `src/taxi_shock/viz/figures.py`: add `extend` arrows to the colourbar (or a note stating which zones exceed the limit and their max), and record the limit rule.
10. Fix F4c in `src/taxi_shock/viz/figures.py`: stop the panel titles colliding (wrap or shorten), and add x-axis labels with units ("effect, %").
11. Fix F4 in `src/taxi_shock/viz/figures.py` / `scripts/09_figures.py`: state the title numbers in the y-axis unit (log points × 100), or put the axis in %. Shorten the title to at most 2 lines at 7 in.
12. Move the counterfactual computation from `scripts/07c_metrics.py` into `src/taxi_shock/causal/counterfactual.py` (PLAN §3 layout). Its current docstring still says "Not implemented yet".
13. In `README.md`, remove `causal` from the row "`causal`, `adapt`, `report`, `all` | added in their phases; they fail with a message until then" (`make causal` is implemented).
14. After Stanley's decision at Checkpoint 4, write the DoD sentence (effect size with CI + design in one sentence) in a results paragraph (README status block or a `reports/analysis.md` stub), citing the `results/` file.

## Escalation reasons

1. **Pre-trends are significant for both pre-registered primary outcomes.** This is an explicit reviewer escalation trigger. Demand monthly pre-trend F(24,60) p = 4.4e−20, corrected F*(24,37) p = 4.4e−11 (`results/placebo.json`). Speed p = 1.3e−32 / 1.1e−18 and duration p = 3.1e−32 / 1.9e−18 (`results/speed_did.json`). The simulation in `results/pretrend_test_size.json` shows the corrected test is oversized (13%) but never produced p below 0.0018 under the null, so the rejections are real. PLAN §6 prescribes switching the primary control group. That is a treatment/control definition change and needs Stanley.
2. **The pre-registered demand estimate is not interpretable as a policy effect, and choosing another estimand is a metric/design decision.** The evidence:
   - log1p equal-weight −0.5047 against levels +317.1 [−116.2, 750.5];
   - pre-volume-weighted −0.0534 [−0.1367, 0.0299];
   - placebo in time −0.1789 [−0.2681, −0.0897] (`results/did_static.json`, `results/placebo.json`);
   - forecast counterfactual +2.0% (`results/figure_stats_phase4.json`).
   The Builder kept the pre-registered estimate as primary and did not pick a new one. That was correct. Options for Stanley:
   - (a) a pre-volume-weighted / aggregate-pickups estimand as primary;
   - (b) a control restricted to high-volume zones;
   - (c) report the demand DiD as unidentified and lead with the MDE.
   All of these are outside the amendment bounds.
3. **The Amendment-2 storyline ("Faster, Not Fewer", B6) is not supported as stated.** On "faster":
   - the speed effect is +1.9% [+0.3%, +3.6%], but it is concentrated in 2025-H1, which coincides with a January treated−control speed spike seen in every year (`results/speed_event_study.csv`);
   - with treated × month seasonality (not pre-registered) it is +0.0119 [−0.0040, 0.0279];
   - the permutation share is 6.4% and β is below the MDE of 0.0275 (`results/speed_power.json`).
   "Not fewer" depends on which demand estimand is chosen (reason 2). The final title and executive-summary wording are Stanley's call at Checkpoint 4.
4. Process note: Phase 3 is still un-passed (ESCALATE, `reviews/phase_3.md`), and Phase 4's counterfactual (F4d) uses the Phase-3 frozen model. Stanley should settle Phase 3 alongside Checkpoint 4.

## Amendments made

None. No change in the evidence falls inside the reviewer's amendment bounds. The needed changes (control group, estimand, storyline) are outside them.
