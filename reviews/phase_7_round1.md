# Phase 7 review (round 1)

Reviewed at HEAD `270ce55` against PLAN.md "Phase 7", Amendment 6 (sections A and B mandatory; `reviews/checkpoint_7_advisor.md`), CLAUDE.md and DECISIONS.md. Working tree left clean (volatile outputs of my `make figures` / `make smoke` runs restored with `git checkout`).

## Verdict

**FIX.** Tests, dbt and ruff are green; `make figures` reproduces every PNG/SVG byte-for-byte; about 120 numbers traced, all present in `results/`. But the report's and README's central claim about the causal designs is wrong as stated: "All 11 pre-registered designs stopped at their pass/fail check" counts a design that is not pre-registered, swaps the pre-registered Lyft design (which passed its pre-trend tests) for a post-hoc alternative, and counts D5b as stopped although the report uses D5b's pre-specified result as a finding. On top of that: a miscounted DECISIONS total, a wrong control-zone count, several wrong citations, a figure with overlapping axis labels, and a `make figures` target that is not "from results/ only" as documented. Everything here can be fixed inside the plan. Nothing calls for ESCALATE: CI's `startup_failure` is an account-level block that Stanley already acknowledged (advisor D2).

## DoD table

| Item | Status | Evidence |
|---|---|---|
| `make all` reproduces every figure from `results/` | PARTIAL | `make figures` ran in 28 s, exit 0; every PNG/SVG byte-identical to HEAD (only the timestamp in `presentation_numbers.json` and the Plotly div id in `F4b_effect_map.html` changed). But `scripts/23_presentation_numbers.py:79` opens the warehouse (weather view), so `make figures` is not "from results/ only" as the Makefile help and the README make-target table say. Full `make all` not run (it includes the raw download). |
| README renders on GitHub | MET | `scripts/21_check_links.py`: 0 dead links; the hero image and the 2×2 grid point at existing PNGs; the anchor `#4-what-the-data-could-not-identify` matches the heading. |
| CI runs ruff, pytest, `make smoke` | PARTIAL (external) | `.github/workflows/ci.yml` has all three steps. `gh run list`: every run ends in `startup_failure` after 0 s (account level; advisor D2, `reports/deferred_items.md` #15). Locally `make smoke` passed in 26.0 s. |
| viz/style.py figure system (palette, policy line, direct labels, title = finding) | MET with defects | Palette in `src/taxi_shock/viz/style.py`; policy line drawn on every calendar time axis checked (F0, F1b, F1c, F3, F4, F4d, F4h, F5, F6a, F6e). Defects under Figures. |
| Interactive F4b `.html` | MET | `reports/figures/F4b_effect_map.html`. |
| analysis.md: structure, every number linked, prior studies cited, overlap/new stated | PARTIAL | Structure follows Amendment 6 B1; four references; the "What overlaps" paragraph is present. Several numbers cite the wrong file (Fix 4). |
| A4 experiment design + executive summary | MET | analysis §6, `results/experiment_design.json` (3,756–5,922 zone-blocks, 4.7–7.4 days); the summary has three findings, what could not be identified, and one recommendation. |
| README: summary, figures, make targets, hardware/runtime, licences, limitations | MET | Every runtime traced to `results/runtimes.json` (47.6 s, 1905.4 s, 11661 s, 4716 s, 16190 s, 652.1 s, 9964.5 / 8242.8 / 18102.6 s, 203 s). |
| Amendment 6 A1 (citywide headline) | MET | `presentation_numbers.json → citywide_accounting.all`. |
| A2 (January 2025 step) | MET | `presentation_numbers.json → january_2025_step`; F6a annotated. |
| A3 (alarms, three-shock column, +7.3 vs +6.3) | MET | `alarm_weather_check.csv`, appendix A7, F3/F3b titles. |
| A4 (one DiD headline) | MET | −34.6% / −5.2% everywhere; event-study means labelled. |
| A5 (lead-placebo location) | PARTIAL | Correct in the prose, F6c title and dashboard View 3. The §4 table row still puts p = 9.8e−05 next to the CBD estimate 0.90 without naming the area: the misreading A5 was meant to remove. |
| A6 (internal labels; WAPE %) | MET | No D/C/B/S/Phase labels in the main text or README outside the make table; figures use descriptive names. |
| A7 (F2 title) | MET | F2 leads with past weather; 0.164528 → 16.5% (`backtest_2024.csv`). |
| A8 (references) | MET | Four references; DECISIONS [P7] 2026-11-14 records the publisher-page check. |
| A9, A10, A11, A12 | MET | Correction block gone; status line gone; dashboard line 3 neutral; supply rounded, 14.0–15.0 range; outer-borough row in change (levels) format. |
| B1 (main text + appendix) | MET | `reports/appendix.md` A1–A9. Main text 1,854 words excluding tables and references (my count includes headings and link text; the Builder reports 1,796 words of prose). Close enough to "about 1,800". |
| B2 (one table, gate count) | NOT MET | The count and the "pre-registered" framing are wrong (Fix 1). |
| B3a–h | MET | All traced (see Number trace). |
| B4 (figures) | MET with defects | See Figures. |
| B5 (README front page; repository counts) | PARTIAL | Order followed and the placeholder is present. "215 entries" is wrong (Fix 3). |
| B6 (first person, definitions, ≤ 30-word sentences) | MET | |

## Test output

- `make verify PHASE=7` (3 min 36 s): ruff PASS; pytest PASS (135 tests, 0 skipped); dbt test PASS=62 WARN=0 ERROR=0; outputs PASS (README, analysis, appendix, presentation_numbers.json, alarm_weather_check.csv, F4b html, ci.yml).
- `pytest -q tests/test_leakage.py tests/test_phase7.py`: all pass. `test_leakage.py` poisons future values and asserts unchanged forecasts (`test_future_poisoning_does_not_change_forecasts`), with power checks (`test_past_poisoning_changes_forecasts`, `test_target_day_weather_is_used`). It is not a placeholder.
- `make smoke`: pass, 26.0 s (limit 600 s).
- `make figures`: pass, PNG/SVG byte-identical to HEAD.

## Number trace

Traced to the named rows; all match (rounding checked):
- Citywide and by-area accounting, the January-2025 step, steps 5.6/5.4/10.9/7.2/−5.9, supply 25.6%/24.0%/14.0–15.0/18.3/5,930/7,040/8,720, scale 1,246,273,736, CBD ride market, platform shares 12.5/9.3/17.8, external 2024 share 4.8–13.1% (3/8/1 months): `presentation_numbers.json`.
- −34.6% [−47.7, −18.3], p 0.0004; −5.2% [−12.8, +3.0]; LOO −36.3 to −32.0 (exp of −0.4509 / −0.3853); −1.0% full control: `did_static.json`. Pre-trend 2.7e−10 (Hotelling), 1.6e−17: `placebo.json`. Placebo in time −13.8%: `placebo.json → placebo_in_time`.
- 56% / 9.5%: `pretrend_test_size.json` (38/25 design). F4 title −3.5% to +0.8% and 500/54 placebos: `power_mde.json`.
- +2.0%, −40.5%, −11.3%, F4b +377% / +13.1% / +103% / +19.7%: `figure_stats_phase4.json`.
- Synthetic control −1.2%, rank 11, p 0.69, +4.6%: `synth_control.json`. Speed +1.9% / −4.0%: `speed_did*.json`. Channel DiD −3.1 / +12.2, app share +3.0 pp and its p-values: `did_by_channel.json`, `app_share_policy_step.json`. Step by trip type 11.3/11.1/8.1/10.6: `app_share_policy_step.json`.
- DML 0.90 [0.74, 1.06], range 0.52–2.62, lead p 0.60 / 9.8e−05; panel 0.52 (0.49–0.56): `incrementality_dml.json`. Lyft 0.68 [0.09, 1.23], −1.12, p 2.3e−07: `lyft_entry.json`. FHV p 2.3e−18: `fhv_did.json`. Cross-platform −0.166 / −0.381 / +4.388: `cross_platform.json`.
- r 0.92 (63) / 0.90 (200) / Spearman 0.85, median CBD 27%: `app_dispatch_summary.json`. 71–83%: `figure_stats_phase4b.json → c1.fastest_donut_zones_share_range` (not the file the report cites).
- 2024 WAPE 16.5 / 16.7 / 24.1, 0.1645 sensitivity, coverage 82% / 79%: `backtest_2024.csv`, `forecast_summary.json`. 31.5 / 30.5%: `presentation_numbers.json`. 99.04%, 103 zones: `modeled_zones.json` (not the cited file).
- Phase-5 table, gaps 0.23 / 0.29 / 0.24 / 0.01, outer 39.5 / 40.3 / 41.2, airports 17.5 / 17.9, Manhattan 14.7 / 14.2, bias by area, 384 / 411 / 720 / 250 s: `adaptation_summary.json`, `adaptation_gaps.csv`, `presentation_numbers.json → bias_pct_by_area`.
- F3: 6.29 / 5.34, day 14, 2024-09-10: `figure_stats_phase3.json`. Storms 7.496 / 3.638 / 5.484 in, −50.6 / −72.7%: `alarm_weather_check.csv`. Three shocks −56.0 / +9.7 / +7.3, days 13 / 162 / 354: `shock_comparison.json`.
- 331,436,471, 2.97%: `data_quality.json`. 87.8%: `channel_label_validation.json` (0.87767). 12.5 GB / 11.68 GiB: `machine_resources.json`.

**Numbers that are wrong or untraceable:**
1. README "215 entries" (`presentation_numbers.json → repository.decisions_entries`): DECISIONS.md has 231 entries. The regex in `scripts/23_presentation_numbers.py:239` (`^- \[\d{4}-\d{2}-\d{2}\]`) drops the 16 timestamped entries (`[2026-11-11 03:20 EST]` …).
2. Appendix A5 and the F4 note: "the 25 Manhattan control zones" for the volume-weighted DiD. `did_static.json → pre_volume_weighted_not_preregistered.n_units` = 61, so 23 controls carry weight; F4i's own note says so.
3. "11 of 11 stopped": see Method sanity.
4. Commit messages for this phase carry no numbers.

## Method sanity

- **The pre-registered gate table (analysis §4, summary, README "What was tested", README and report Limitations) misstates the record.**
  - *Volume-weighted demand DiD* is not pre-registered: the result key is `pre_volume_weighted_not_preregistered`, and Amendment 3 C2 introduced it after the equal-weight result. The sentence "Every design had an expected direction and a pass/fail check … fixed before it was run" is false for it.
  - *Lyft entry.* The pre-registered design (Amendment 4/4a, levels, clean windows) **passed** its pre-trend tests on total (p 0.26), app (0.27) and street (0.22) and failed only on the Uber outcome (1.9e−13) (`lyft_entry.json → primary_clean_windows.pretrend`; DECISIONS [D3]). It is "not credible" because the levels are misspecified in scale, not because it failed its gate. The table instead lists the log specification, which Amendment 5 calls a "labelled alternative" and DECISIONS marks as "added after seeing the levels result", and counts it as a pre-registered design that failed.
  - *D5b.* The pre-specified test (Amendment 4a: compare the step across trip types) gave an answer, and §2 relies on it ("The fee difference between taxis and FHVs does not explain it"). The table counts D5b as "stopped" through the app-share DiD's pre-trend test, which was not D5b's pre-specified reading.
  - *Synthetic control.* README "every design fails its pre-trend test" is wrong for the synthetic control, whose gate is the fake-date gap (it fails narrowly: 0.0464 vs 0.0432 RMSPE). `presentation_numbers.json` also stores a fabricated `p_value: 0.0` for this boolean gate.
- **Test size.** "The corrected test about right (9.5%)": 9.5% at a nominal 5% over 200 replications (MC SE ≈ 1.5 pp) is about three standard errors above nominal. That is not "about right".
- **January 2025 step.** The week of 2025-01-05 is the first week after the holidays, so both channels rebound seasonally. "It did not relabel street hails" is stronger than one week-pair supports; "not mainly relabelled street hails" is what the numbers carry (optional wording).
- Forecasting, monitoring and storm attribution: consistent with the files. The storm rule (≥ 2 in) and window (3 days) are in config and DECISIONS.
- Leakage test is real and green (see Test output).

## Figures

Opened: F0, F1b, F1c, F2, F2b, F3, F3b, F4, F4b, F4d, F4g, F4h, F4i, F5, F6a, F6b, F6c, F6e.
- **F3b:** the y-axis labels of the three stacked panels overlap ("(%)Actual vs forecast (%)" runs into the next panel). Fix. The end labels "CBD" / "Rest of the city" sit on the lines in panels 1–2, and the panel-3 alarm label runs past the axis (cosmetic).
- **F4, F4d, F4i:** the axis label "Effect on CBD pickups (%)" (F4i "Static DiD effect …") names the quantity as an effect of the policy. Amendment 5 forbids figure wording that says congestion pricing had an effect. Relabel as an estimate or difference.
- **F4 note:** "25 Manhattan control zones" for the weighted path (23 carry weight; see Number trace).
- **F4g footnote:** "other codes undocumented, not counted" contradicts appendix A1 (EH0004 / EH0010 = Curb and Arro apps; only A and CC undetermined).
- **F4h title:** "rank 11 of 16 donors": there are 15 donors (the caption says so); 16 is the units including the CBD. The x-axis also runs about four months past the data.
- Cosmetic, optional: F3 title is four lines and F5 three; F5 and F6c draw non-channel series (app-share-feature strategy, primary DML) in the app teal, which `style.py` reserves for "app".
- Units, policy line and CBD/non-CBD colours are otherwise consistent with `style.py`; no truncated axes that mislead (F2 outer-borough panel has its own scale and the note says so).

## Decisions check

- Phase-7 rules with DECISIONS lines: storm rule and window, rounding to ten, APP_CMAP, external-share comparison, F6b map drop, F4g multiples, compaction, conformal unification. Present.
- Missing: the gate rule `p >= 0.05` hard-coded in `scripts/23_presentation_numbers.py:227` (not in config, no DECISIONS line), and the classification rules behind "11 designs" (which row represents which pre-registered design). Both need lines once Fix 1 is done.

## Fix list

1. In `scripts/23_presentation_numbers.py → preregistered_checks`, `reports/analysis.md` (summary, §4 opening and table, §7) and `README.md` ("What was tested", Limitations), restate the gate table from the record:
   - mark the volume-weighted demand DiD as not pre-registered (added in Amendment 3 C2);
   - represent Lyft's entry by the pre-registered levels design: −1.12 [−1.37, −0.87]; pre-trend total / app / street p 0.26 / 0.27 / 0.22 (pass), Uber p 1.9e−13 (fail); not credible because the levels are misspecified in scale. Show the log specification as a labelled alternative;
   - show D5b's pre-specified step comparison as answered (same step for trips touching neither end), with the app-share DiD as a secondary that fails its pre-trend test;
   - replace "every design fails its pre-trend test" with wording that fits the synthetic control's fake-date gate;
   - store the synthetic-control gate as `p_value: null`, `passed: false` plus its two numbers (0.0464 gap vs 0.0432 pre-RMSPE), not `0.0`;
   - recount, and quote the new counts with their file;
   - name the area of the failed lead placebo (Manhattan outside the CBD) in the DML table row.
2. In `reports/appendix.md` A5 and the F4 note (`scripts/09_figures.py`), state 23 weighted control zones (61 units; zones with no pre-period pickups carry no weight), not 25.
3. In `scripts/23_presentation_numbers.py → repo_counts`, count DECISIONS entries with optional time stamps (`^- \[\d{4}-\d{2}-\d{2}[\] ]`), regenerate, and update README "215 entries" (231 at HEAD).
4. Fix citations in `reports/analysis.md`:
   - §5 "103 zones … 99.04%" → `modeled_zones.json`;
   - §5 "CBD app share rose from about 18% to about 30%" → `channel_restatement.json`;
   - §3 "71–83% … median CBD zone 27%" → `figure_stats_phase4b.json → c1` (range) and `app_dispatch_summary.json` (27%).
5. In `reports/analysis.md` §3 item 1 and `reports/appendix.md` A6, replace "about right (9.5%)" with the measured statement: 9.5% at a nominal 5% (200 replications), still above nominal but far below 56%.
6. In `scripts/09_figures.py`, give F3b one shared y-axis label (`fig.supylabel`) so the panel labels no longer overlap.
7. In `scripts/09_figures.py`, change the F4h title to "rank 11 of 16 units (CBD and 15 donors)" and end its x-axis at the last data week.
8. In `scripts/09_figures.py`, fix the F4g footnote: EH0004 / EH0010 are Curb's and Arro's apps; only A and CC are undetermined; none of these is counted as Uber/Lyft.
9. In `scripts/09_figures.py`, relabel the F4, F4d and F4i axes from "Effect on CBD pickups (%)" to non-causal wording, e.g. "DiD estimate / difference from counterfactual, CBD pickups (%)".
10. Make `make figures` read `results/` only, as the Makefile help and README say. Move the warehouse weather read of `scripts/23_presentation_numbers.py` into an earlier target (e.g. `shock` or `report`) that writes `alarm_weather_check.csv`, and have the figures step read that file. Otherwise correct the Makefile and README wording and record why.
11. Update `reports/deferred_items.md`: item 18 (the references are now four; close it), items 10 and 14 (section numbers changed: methods case §3, experiment §6, D5b now quoted in §2).
12. Move the gate significance level (0.05) in `scripts/23_presentation_numbers.py` to `config/project.yaml`, and add DECISIONS lines for it and for the row classification in Fix 1.

## Escalation reasons

None. (CI `startup_failure` is outside the Builder's control and already ruled on in `reviews/checkpoint_7_advisor.md` §D2; it stays PARTIAL until the account or visibility changes.)

## Amendments made

None.
