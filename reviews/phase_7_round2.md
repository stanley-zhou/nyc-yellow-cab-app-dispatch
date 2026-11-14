# Phase 7 review (round 2)

Reviewed at HEAD `991f1f1` (the round-1 fix commit) against PLAN.md "Phase 7", Amendment 6 (sections A and B mandatory; `reviews/checkpoint_7_advisor.md`), CLAUDE.md, DECISIONS.md and `reviews/phase_7_round1.md`. Working tree left clean: my `make figures` run changed only the timestamp in `results/presentation_numbers.json` and the Plotly div id in `F4b_effect_map.html`, and I restored both with `git checkout`.

## Verdict

**FIX.** Tests, dbt and ruff are green. `make figures` reproduces every PNG/SVG byte for byte. Round-1 fixes 2–12 are applied. Fix 1 (the designs table) is mostly applied, but the restated table still misstates the record in two places:
- It labels the app-share DiD/event study as "not pre-registered" and counts it among "the 3 designs I added after seeing earlier results". Amendment 4a D5b names "an event study around 2025-01-05" as the pre-specified test, and the Builder's own D5b DECISIONS entry does not mark it as post hoc.
- The main-text row for Lyft's levels design omits that its pre-registered Uber outcome fails its pre-trend test.

Smaller problems: one untraceable number ("4.3 times"), an F4c title count that does not match the panels drawn, an axis label that runs into the title in F4d, and a main text that grew to about 1,975 words against "about 1,800 or fewer". Everything is fixable inside the plan. This is the second fix round. If the designs-table record is still wrong after it, it becomes ESCALATE under CLAUDE.md.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| `make all` reproduces every figure from `results/` | PARTIAL | `make figures`: exit 0, 2 min 18 s, every PNG/SVG byte-identical to HEAD. The warehouse read is gone (round-1 Fix 10 done: `scripts/06c_weather_daily.py` → `results/weather_daily.csv`). But the map figures (F1, F4b, F4g, F6b) also read `data/raw/lookup/taxi_zones.shp` (`scripts/09_figures.py:87, 379, 535, 684`), so the "from results/ only" wording in the Makefile help and the README is still not literally true. Full `make all` not run (it includes the raw download). |
| README renders on GitHub | MET | Relative links resolve. The hero figure and the 2×2 grid point at existing PNGs. The anchor `#4-what-the-data-could-not-identify` matches the heading. |
| CI runs ruff, pytest, `make smoke` | PARTIAL (external) | `.github/workflows/ci.yml` has the three steps. `gh run list`: the last three pushes all end in `startup_failure` after 0 s (account level; advisor D2; `deferred_items.md` #15). Not the Builder's to fix. |
| viz/style.py figure system | MET with defects | See Figures. |
| Interactive F4b `.html` | MET | `reports/figures/F4b_effect_map.html` |
| analysis.md: structure, links, prior studies, overlap/new | MET | Amendment 6 B1 order; four references; "What overlaps and what is new" paragraph; citations corrected (round-1 Fix 4). |
| A4 experiment design + executive summary | MET | §6 and `experiment_design.json`. The summary has three findings, what was not identified, and one recommendation. Every summary sentence is ≤ 30 words (checked by script). |
| README sections (summary, figures, targets, hardware, runtimes, licences, limitations) | MET | README follows B5 order. Placeholder for "How this project was built" is present. |
| Amendment 6 A1–A12 | MET | Unchanged from round 1. A5 is now also met in the table row: "lead placebo fails in Manhattan outside the CBD (p = 9.8e−05)". |
| B1 (main text ≈ 1,800 words + appendix) | PARTIAL | `reports/analysis.md` up to References, excluding table rows, image lines and link targets: **1,975 words** (round 1: 1,854). The round-1 additions pushed it about 10% over "about 1,800 or fewer". |
| B2 (one table, gate count) | PARTIAL | Table restated with a "Pre-registered" column, and the Lyft levels design and the D5b step comparison are now represented. Still wrong: D5b's event study is marked as post hoc, and the Lyft row's gate cell omits the Uber failure (Fixes 1 and 2). |
| B3–B6 | MET | Numbers traced below. First person; definitions on first use. |
| Round-1 fixes 2–12 | MET | 23 weighted control zones (appendix A5, F4 note). DECISIONS count 232 (my regex count: 232). Citations, test-size wording (9.5% "still above 5%"), F3b shared y label, F4h "16 units (CBD and 15 donors)" with the axis ending at the data, F4g footnote, "estimate" axis labels, gate α in `config/project.yaml:162`, deferred list. |

## Test output

- `make verify PHASE=7` (5 min 33 s): ruff PASS; pytest PASS (135 tests, 0 skipped, 0 failures per `verify_junit.xml`); dbt test PASS=62 WARN=0 ERROR=0; outputs PASS.
- `pytest -q tests/test_leakage.py`: all pass. Future-poisoning test with power checks; not a placeholder.
- `make figures`: pass; PNG/SVG byte-identical.
- CI: `startup_failure` (external, see DoD).

## Number trace

Traced, all matching (rounding checked):
- **Citywide and by-area accounting:** 27.3%, 703,268 → 895,177, +199,068, −7,159 (−1.1%); CBD +99,063 / +104,958 / −5,896; Manhattan outside the CBD +50,537 / +51,230 / −692; outer +43,526 (8,277 → 51,803, ratio 6.26 → "about six-fold") / +42,811 / +715. Source: `presentation_numbers.json → citywide_accounting`.
- **January 2025 step:** step table values; ratios 2.06–2.73 → "2.1- to 2.7-fold"; street changes −2.7% to +7.8%; steps 5.6 / 5.4 / 10.9 / 7.2 / −5.9. F0 annotation "11% → 22%" (0.1119 → 0.2206). Source: `→ january_2025_step`.
- **Supply:** 25.6% / 24.0%; 104,422 → 131,133; 7,040 → 8,720; 14.0–15.0; 2022: 5,930 and 18.3. Sources: `→ supply`, `incrementality_dml.json → supply`.
- **CBD ride market and scale:** CBD ride market table, +1.8%, 12.5 / 9.3 / 17.8%; scale 341,589,889 + 904,683,847. Source: `presentation_numbers.json`.
- **2024 external app share:** 4.8–13.1%, 3 / 8 / 1 months. Source: `→ external_app_share_2024`.
- **Alarms and storms:** 7.5 / 5.5 / 3.6 in; −50.6 / −72.7%. 2026-Q1 storm share of absolute error 8.9–11.1% (s0, s1, s4, s6), quoted as "9–11%". WAPE without storm days 17.0–17.6%. Sources: `→ alarm_weather_check`, `alarm_weather_check.csv`.
- **Designs table:** every p-value and estimate matches `presentation_numbers.json → preregistered_checks` and its source files. Counts are 10 / 8 / 2 / 3 / 3 (but see Method sanity on the classification).
- **Leave one out:** F4i weighted −8.6% to −4.3% and equal −36.3% to −32.0% (recomputed from `leave_one_out.csv`, 61 and 63 rows).
- **F4c:** "4 of 8" speed subsets with CIs that include zero (recomputed from `speed_heterogeneity.csv`). "10 of 15" demand: see Figures.
- **Unchanged from round 1 and re-checked at random:** −34.6% [−47.7, −18.3]; −5.2% [−12.8, +3.0]; pre-trend 2.7e−10 / 1.6e−17; −13.8%; +2.0%; 0.90 [0.74, 1.06]; 0.52–2.62; DML-lead p 9.8e−05 / 0.60; 16.4 / 16.2 / 23.7%; 0.23 pp; outer-borough bias −10.8 / −7.0 / −6.0%.
- **Repository counts:** 232 DECISIONS entries (regex `^- \[YYYY-MM-DD[\] ]` → 232); 135 tests (junit).

**Untraceable:**
1. "Curb cabs carry 4.3 times CMT's volume" (`reports/analysis.md` §4, `reports/appendix.md` A4). No results file holds 4.3.
   - `lyft_entry.json → curb_cmt_weekly_ratio.*.total` gives weekly ratios: 2025 range 3.98–4.58 (mean 4.21, 31 weeks); all 70 weeks mean 4.38; 2026 mean 4.52.
   - DECISIONS [D3] quotes "~4.3×" and "4.02–4.39 through 2025". That range does not match the file's 2025 range either.
2. Commit message `991f1f1` carries counts only (10 / 8 / 2 / 3; 23 zones); all trace to `presentation_numbers.json` and `did_static.json`.

## Method sanity

- **D5b's event study classified as post hoc.**
  - Amendment 4a D5b, written before D5b was run, specifies the test as "weekly app share of yellow pickups by trip type … 2024-07 → 2025-06, as an event study around 2025-01-05", read through the step comparison.
  - DECISIONS [D5b] (2026-11-13) flags only the volume weighting of the log-count regressions as "added after seeing them". It does not flag the app-share DiD/event study.
  - Yet `presentation_numbers.json` row "DiD, app share (secondary)" has `preregistered: false`. Analysis §4 then says "the 3 designs I added after seeing earlier results". For this row that is false.
  - The round-1 instruction was to show it as a *secondary reading*, not as a post-hoc design.
  - The row-classification rule in DECISIONS [P7] 2026-11-14 ("designs added after seeing an earlier result are rows with preregistered = false") is applied inconsistently with the Builder's own D5b record.
  - The counts change accordingly. Either D5b is one pre-registered design with a primary reading (answered) and a secondary reading (fails its pre-trend test), or the event study is a separate pre-registered row. Either way, the post-hoc set is 2 (weighted demand DiD, Lyft log specification), not 3.
- **Lyft levels row.**
  - Amendment 4 D3 lists three outcomes: total, Uber-dispatched and street-hail pickups.
  - The main-text table gate cell shows only total / app / street (pass). The Uber outcome's pre-trend test fails (p = 1.9e−13; `lyft_entry.json`; `presentation_numbers.json` row note).
  - The appendix states the Uber failure, but the main table, which a reader skims, does not. Show it in the cell: "pass on total / app / street; Uber fails".
  - "Passed" is defensible for the incrementality estimand, which uses total pickups. The displacement outcome did not pass.
- **Synthetic-control gate.** Matches DECISIONS [P4b] 2026-11-12 (fit + no invented gap, fixed before the run). The stored `p_value: null` is correct now.
- **Forecasting, monitoring and storm attribution:** consistent with the files.
- **Leakage test:** real and green.
- **Causal wording:** no figure or sentence states that app dispatch caused growth or that congestion pricing had or had no effect.

## Figures

Opened: F0, F3b, F4, F4c, F4d, F4g, F4h, F4i, F5, F6c (all those changed in the round-1 commit, plus the hero and F5).
- **F4d:** the y-axis label "CBD pickups vs counterfactual or control (%)" runs into the third line of the four-line title. "(%)" overlaps "pre-registered". Fix: shorten the label or the title, or add top margin.
- **F4:** the y-axis label "DiD estimate, CBD pickups vs control (%)" reaches the second title line ("outside every …"); it touches the title. Same remedy.
- **F4c:** the title says "10 of 15 trip subsets for weighted demand". The figure draws six demand panels with 17 subsets. The count in `scripts/09_figures.py:405` uses only the first five panels, so it leaves out pass-through. Across all 17 drawn subsets, 11 include zero. State which panels are counted, or count what is drawn.
- **F3b:** the shared y label is fixed. Cosmetic, optional: the panel-3 alarm label still runs past the axis; the end labels sit on the lines in panels 1–2.
- **F4h, F4g, F4i, F6c, F0, F5:** round-1 defects resolved. Palette and policy line are consistent with `style.py`; no misleading truncated axes. F6c's primary DML is now near-black. Optional: F5's app-share strategy is still drawn in teal.

## Decisions check

- Present: gate α (`config/project.yaml:162`, DECISIONS [P7] 2026-11-14), row-classification rule, storm rule, DECISIONS count regex, `06c_weather_daily.py`.
- Missing or inconsistent:
  - (a) The row-classification rule is not applied as written to the D5b event study (Method sanity).
  - (b) No line records that the F4c title count excludes the pass-through panel.
  - (c) DECISIONS [D3]'s "4.02–4.39 through 2025" does not match `lyft_entry.json → curb_cmt_weekly_ratio` (2025: 3.98–4.58).

## Fix list

1. Restate D5b in `scripts/23_presentation_numbers.py → checks` so the record matches Amendment 4a and DECISIONS [D5b]: the app-share event study/DiD is part of the pre-specified D5b test (a secondary reading), not a design added after seeing results. Then:
   - regenerate `results/presentation_numbers.json`;
   - update the counts and the sentence "the 3 designs I added after seeing earlier results" in `reports/analysis.md` (summary, §4 opening and table, §7) and `README.md` ("What was tested", Limitations) to the counts the file now gives;
   - add a DECISIONS line stating how a pre-specified design with two readings is counted.
2. In `reports/analysis.md` §4, change the Lyft levels row's gate cell to show the Uber outcome's failed pre-trend test (p = 1.9e−13) next to the three passes. In `scripts/23_presentation_numbers.py`, make the row's `passed` reflect "3 of 4 pre-registered outcomes pass", or a field that says so.
3. Save a summary of the Curb/CMT weekly ratio (the period used and its mean and range) to `results/lyft_entry.json` or `presentation_numbers.json`. Quote that value instead of "4.3 times" in `reports/analysis.md` §4 and `reports/appendix.md` A4. Correct the range in DECISIONS [D3] or add a dated correction line.
4. In `scripts/09_figures.py` (F4c), make the title count match the panels drawn: count all 17 demand subsets, or name the five panels counted. Record the choice in DECISIONS.
5. In `scripts/09_figures.py` / `src/taxi_shock/viz/figures.py`, stop the F4d (and F4) y-axis labels from overlapping the title, by shortening the label or the title or adding top space.
6. Trim `reports/analysis.md` back to about 1,800 words of main text (1,975 now, excluding tables and references), moving detail to `reports/appendix.md`.
7. Correct the Makefile `figures` help text and the README make-target row: the map figures read the zone shapefile under `data/raw/lookup/` as well as `results/`. Alternatively, write the zone geometry the figures need to `results/` or `data/processed/` and read it from there.

## Escalation reasons

None now. The designs-table issue (round-1 Fix 1) has survived one fix round in reduced form. If any part of Fix 1 or Fix 2 above is still wrong at the next review, CLAUDE.md's two-round limit makes it ESCALATE. CI `startup_failure` stays outside the Builder's control (advisor D2).

## Amendments made

None.
