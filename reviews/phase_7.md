# Phase 7 review (round 3, final)

Reviewed at HEAD `715dd6e` (the round-2 fix commit) against PLAN.md "Phase 7", Amendment 6 (sections A and B mandatory; `reviews/checkpoint_7_advisor.md`), CLAUDE.md, DECISIONS.md and `reviews/phase_7_round2.md`. Working tree left clean: my `make figures` run changed only `generated_utc` in `results/presentation_numbers.json` and the Plotly div id in `F4b_effect_map.html`, and I restored both with `git checkout`.

## Verdict

**PASS.** Tests, dbt and ruff are green. `make figures` reproduces every PNG/SVG byte for byte. All seven round-2 fixes are applied. The designs table now matches the record:
- D5b is one pre-registered design. Its event study is a secondary reading, shown but not counted.
- Lyft's levels design shows the failed Uber pre-trend test and is recorded as `passed = "partial"` (3 of 4 outcomes).
- Every new number traces to a file.

The issue that survived round 1 (the designs table) is resolved, so the two-round limit does not trigger. The remaining observations are optional and do not block.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| `make all` reproduces every figure from `results/` | MET (with stated exception) | `make figures`: exit 0, 36 s. Every PNG/SVG is byte-identical to HEAD. The maps also read the TLC zone shapefile, a lookup. The Makefile help (`figures` target) and README make-target row now say so, which was the round-2 Fix 7 option. I did not run the full `make all`, because it includes the raw download. |
| README renders on GitHub | MET | Relative links and the `#4-what-the-data-could-not-identify` anchor resolve. Hero and 2×2 grid PNGs exist. |
| CI runs ruff, pytest, `make smoke` | PARTIAL (external) | `.github/workflows/ci.yml` has all three steps. `gh run list`: the last 4 pushes, including `715dd6e`, end in `startup_failure` after 0 s. This is an account-level problem (advisor D2; `reports/deferred_items.md` #15) and outside the Builder's control. |
| viz/style.py figure system, policy line, palette | MET | See Figures. |
| Interactive F4b `.html` | MET | `reports/figures/F4b_effect_map.html` |
| analysis.md: order, links, prior studies, overlap/new | MET | Follows the Amendment 6 B1 order. Four references and the "What overlaps and what is new" paragraph are present. |
| A4 experiment design + executive summary | MET | §6 and `results/experiment_design.json`. The summary has 3 findings, what was not identified, and 1 recommendation. |
| README sections | MET | Unchanged from round 2. The "How this project was built" placeholder is left for Stanley. |
| Amendment 6 A1–A12 | MET | Unchanged since round 2. The D2 wording matches the amended sentence verbatim (analysis §4). |
| B1 main text ≈ 1,800 words + appendix | MET | My count, up to References, excluding table rows, image lines and link targets: **1,735**. The Builder reports 1,794 with headings and link text included. Either way it is ≤ 1,800. The moved sentences appear in `reports/appendix.md` A1, A2, A6 and A8, so nothing was dropped. |
| B2 one table, gate count | MET | 13 rows: 10 pre-registered primary, 1 secondary reading, 2 not pre-registered. Counts are 10 / 8 stopped / 1 passed / 1 partial; 2 post hoc, both failed (`presentation_numbers.json → preregistered_checks`). The summary, §4, README "What was tested" and README Limitations all state the same counts. |
| B3–B6 | MET | Numbers traced below. Writing is in the first person. No causal claim about app dispatch or congestion pricing. |
| Round-2 fixes 1–7 | MET | Details in Method sanity, Number trace and Figures. |

## Test output

- `make verify PHASE=7` (3 min 56 s, exit 0): ruff PASS; pytest PASS (junit: 135 tests, 0 failures, 0 errors, 0 skipped); no_skips PASS; dbt test PASS=62 WARN=0 ERROR=0; outputs PASS.
- `pytest -q tests/test_leakage.py`: all pass. It is the real future-poisoning test, not a placeholder.
- `make figures`: exit 0. PNG/SVG unchanged, so the run is byte-reproducible.
- CI: `startup_failure` (external).

## Number trace

New or changed numbers in this round:
- **Designs counts (10 / 8 / 1 / 1; 2 post hoc, both failed).** Recomputed from `presentation_numbers.json → preregistered_checks.rows` using the stored counting rule. Each row's p-value matches its `gate_values`; spot-checked against round 2's sources.
- **"about 4.4 times" and "range 4.0–5.3".** Source: `presentation_numbers.json → lyft_curb_cmt_ratio`: `pre_mean` 4.380, `pre_min` 3.984, `pre_max` 5.306, 58 weeks over 2025-06-01 → 2026-07-08. Derived from `lyft_entry.json → curb_cmt_weekly_ratio`; I recomputed it.
- **Lyft gate cell.** p = 0.26 / 0.27 / 0.22 / 1.9e−13 match `gate_values.p_value_by_outcome`; `outcomes_passed` = "3 of 4".
- **D5b secondary reading.** +3.0 points, p = 3.9e−27 (`app_share_policy_step.json` via `presentation_numbers.json`).
- **F4c title "11 of 17" / "4 of 8".** Source: `figure_stats_phase4.json → heterogeneity`. The code now counts every drawn demand cut (`scripts/09_figures.py`, `sub = hw[hw["cut"].isin(list(names))]`).
- **"233 entries" (README).** Source: `presentation_numbers.json → repository.decisions_entries` = 233. My regex count is also 233.
- **"135 tests".** Matches `repository.tests_collected` and junit.
- **Commit message `715dd6e`.** "3 of 4" and "1,794 words". The word count describes the report itself rather than a result; my independent count (1,735) confirms it is under the target.

Unchanged numbers, re-checked at random against round-2 sources (all match): 27.3%, 703,268 → 895,177, +199,068, −7,159; 2.3% → 29.6%; 25.6% / 24.0%, 14.0–15.0; 16.4 / 16.2 / 23.7%; −34.6% [−47.7, −18.3]; −5.2% [−12.8, +3.0]; 2.7e−10; −13.8%; +2.0%; 0.90 [0.74, 1.06]; 0.52–2.62; 9.8e−05.

No untraceable number in README, analysis.md, appendix.md, figure titles or the commit message.

## Method sanity

- **Designs table (round-2 Fixes 1, 2).**
  - D5b is now `preregistered: true`. The step comparison has `reading = "primary"` (passed). The event study has `reading = "secondary"` (fail) and is not counted. This is consistent with Amendment 4a, which names the event study within the D5b test.
  - The post-hoc set is now exactly the volume-weighted demand DiD (Amendment 3 C2) and the Lyft log specification. This is correct.
  - The Lyft levels gate is now "each pre-registered outcome (total, app, street, uber)", with `passed = "partial"`. The main-text gate cell states the Uber failure.
  - The counting rule is stored in the JSON (`counting_rule`) and in DECISIONS [P7] 2026-11-14 round-2 entry. `tests/test_phase7.py` enforces the identity passed + stopped + partial = pre-registered primary.
- **Lyft "partial" judgement.** This is defensible. The incrementality estimand uses total pickups, which passes; the displacement outcome (Uber) fails. Both facts are stated wherever the row appears: summary, §4 table and text, appendix A4 and README.
- **Storyline rules (Amendment 5/6).** No sentence states that app dispatch caused growth or that congestion pricing had or had no effect. The §3 title wording ("an effect that was not there") is the Amendment 3 C8 wording, applied to the artefact.
- **Forecasting, monitoring, leakage.** Unchanged since round 2 and consistent with the files. The leakage test is green.

## Figures

I opened F4, F4c and F4d, the figures changed in this round.
- **F4.** The y label "DiD estimate (%)" now clears the title. The policy line and label are present, and the pre/post tint follows `style.py`.
- **F4d.** The y label "CBD pickups vs comparison (%)" clears the three-line title. Direct labels are used and there is no legend. The policy line is present.
- **F4c.** The title count (11 of 17; 4 of 8) matches the panels drawn. Each panel has an axis label with units (%). The CBD accent colour is consistent.
- **Optional, carried from round 2 (not required):** in F3b panel 3 the alarm label runs past the axis; F5's app-share strategy is drawn in teal.

## Decisions check

- Present and consistent:
  - counting rule for primary and secondary readings;
  - Lyft `partial` status;
  - Curb/CMT ratio source and the corrected 2025 range in [D3] (3.98–4.58, mean 4.21, with a dated correction note);
  - F4c counting choice (all drawn subsets; alternative rejected);
  - label shortening;
  - shapefile wording.
  All are in DECISIONS [P7] 2026-11-14 (round-2 entry).
- Observation, not a fix: DECISIONS [D3] still says "Curb cabs carry ~4.3× CMT's volume" in the sentence just before the corrected range. The sourced pre-period mean is 4.38 (2025 weeks: 4.21), so "~4.3×" is approximate and the reports now quote 4.4 from a file. The Builder may align the wording when convenient.

## Fix list

None.

## Escalation reasons

None. CI `startup_failure` remains outside the Builder's control (advisor D2) and is already listed in `reports/deferred_items.md`.

## Amendments made

None.
