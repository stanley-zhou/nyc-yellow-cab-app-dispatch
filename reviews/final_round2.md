# Final review, round 2: whole repository before publication (Phase 7 scope + E3 + release changes of 2026-11-15)

Reviewed at commit `7c5a2ee` on 2026-11-15. The scope and the owner's release requirements are the same as in `reviews/final_round1.md`.

## Verdict

**FIX** (fix round 2 of 2; a third failure is ESCALATE under CLAUDE.md). All six round-1 fixes are applied correctly. Tests, dbt and ruff pass. Every number I traced has a source row. No result, figure, code path or verdict changed. But the release requirement on personal, non-technical notes in the public tree is still **not met**, and round 1 missed this. The DECISIONS.md entry that logs the redaction, and the round-1 review itself, quote the removed text back word for word. One `make help` label is also still not described in words. Three fixes plus one follow-up, all inside the plan and of the same kind as the approved 2026-11-15 redaction.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| `make all` reproduces every figure from `results/` | MET | No file under `reports/figures/` or any figure code changed since round 1 (`git diff 83be64c HEAD --stat`). All 14 changed `.py` files are AST-identical once docstrings are stripped. |
| README: summary, figures, targets, hardware/runtime, licence, limitations | MET | README.md. Runtimes trace to `runtimes.json`, `snowflake_load.json` and `dbt_targets.json` (round-1 trace; unchanged). |
| CI: ruff, pytest, `make smoke` | MET | `.github/workflows/ci.yml`. |
| Amendment 6 summary, structure and incrementality (D2) wording; Amendment 5 rule against causal sentences | MET | analysis.md Summary and §4. The D2 sentence appears verbatim in analysis §4 and dashboard_spec View 3. No sentence says app dispatch caused growth or that congestion pricing did or did not have an effect. |
| E3 (Snowflake target, load, build and tests, parity, CI on DuckDB) | MET | `dbt_targets.json → parity`: 9 marts, `cells_differing` 0 for each, `relative_tolerance` 1e-9, `all_identical` true. The new README wording ("identical … within a relative tolerance of 1e-9") is accurate. |
| Release: public tree free of personal, non-technical notes | **NOT MET** | (a) `DECISIONS.md` l.290, the redaction entry, quotes the removed personal, non-technical notes verbatim. (b) `reviews/final_round1.md` l.21, l.63 and l.74 name the same content. The round-1 fix to PLAN l.397 was applied, but these files bring the content back into the tree. |
| Release: no machine-specific paths, e-mail addresses, Snowflake identifiers | MET | `git grep -I` finds no `/home/<user>`, `C:\Users`, `/Users/` or e-mail address (only the noreply attribution). Snowflake appears only as `env_var` names. `results/` has no host, user, account or warehouse fields; the only such field is `"schema": "RAW"`. |
| Release: script/module docstrings state what each does, reads and writes; internal labels in words | PARTIAL | Docstrings: MET. All 116 `.py` files were checked. The 14 modules round 1 flagged now say "Pure computation …; reads and writes no files", and a grep finds no file I/O in any of them, so the claim is true. Labels: the `adapt` row is fixed. The `dbt` row of `make help` and the README still says "Checkpoint-1 checks (03b, 03c)" with no words (Fix 3). |
| Release: `make help` matches README table | MET | Compared visually; `tests/test_make_targets.py` passes. |
| Release: `results/INDEX.md` covers every results file | MET | All 126 tracked files are listed; none missing (my own check plus `tests/test_results_index.py`). |
| Release: lock file committed; README states install command | MET | `requirements-dev.lock`, `requirements-snowflake.lock`. README "Setup" gives the four `uv` commands. |
| Release: no result, number, decision or verdict changed | MET | `git diff 83be64c HEAD -- results/`: only `presentation_numbers.json` changed (`generated_utc`, `decisions_entries` 239→240, `review_files` 25→26). `reviews/`: only `final_round1.md` was added. DECISIONS: l.290–291 were amended as round-1 Fix 1/3 asked, and l.292 was appended. No decision content changed. |

## Test output

- `ruff check .`: `All checks passed!`
- `make verify PHASE=7` (exit 0): `ruff PASS · pytest PASS · no_skips PASS (0 skipped) · dbt_test PASS (PASS=62 WARN=0 ERROR=0 SKIP=0) · outputs PASS`.
- `grep -c "^- \[20" DECISIONS.md` = 240, which matches README "(240 entries)" and `presentation_numbers.json → repository.decisions_entries`.
- `ls reviews | wc -l` = 26 before this file, matching `repository.review_files`. It will be 27 once this file is committed; the README does not quote this count.

## Number trace

The two numbers changed in round 1:
- analysis §5: 22.3% (February 2025) and 31.3% (September 2026) come from `channel_monthly.csv`, zone_group `cbd`, `app_share` 0.223422 / 0.312546. September 2026 has `n_weeks` = 3; the ratio is still valid, and the 3-week note round 1 suggested was left out (not material).
- analysis §5: "not distinguishable by a paired bootstrap" now links `wape_gap_bootstrap.csv`.

Additional spot checks (not listed in round 1), all matched after rounding:
- analysis §2: 9.7% / 12.0%, 0.96 / 0.94, 0.69 / 0.57 from `presentation_numbers.json → accounting_2026`. Steps 5.6 / 5.4 / 10.9 / 7.2 and the January-2025 area table from `january_2025_step`. CBD ride market 1,234,000 / 1,164,607 / 25.3% / 30.8% / +1.8% from `cbd_ride_market`.
- analysis §4: synthetic control rank 11 of 16 (15 placebos + CBD), gap 0.045 vs pre-RMSPE 0.043, from `synth_control.json`. Lead-placebo p = 9.8e−05 from `incrementality_dml.json`.
- analysis §6 / appendix A8: 67 zones, 3,756–5,922 zone-blocks, 4.7–7.4 days ("about 5–7"), sd 33.1, 30.3 app trips per block, autocorrelation 0.58, 3,466 days, all from `experiment_design.json`.
- appendix A1: 2024 app share 4.8–13.1%, 3 / 8 / 1 of 12 months, from `external_app_share_2024`. 5,930 cabs and 18.3 / 14.8 trips per cab-day from `supply`. Spearman 0.85 from `app_dispatch_summary.json`. A2: 12.5% / 9.3% / 17.8% from `cbd_ride_market`; −48,303 and 0.944 / 0.574 from `accounting_2026`.
- appendix A3: 0.49–0.56 (draws min/max), p = 0.60 (CBD lead), from `incrementality_dml.json`. A5: 23 weighted control zones = 61 units − 38 treated; −1.0% full control; from `did_static.json`. A6: 56% from `pretrend_test_size.json`.
- appendix A7: the three-shocks table (−56.0 / +9.7 / +7.3%; days 13 / 162 / 354) from `shock_comparison.json`. 2026-Q1 WAPE 18.7–19.1%, 2025-Q1 16.2–16.4%, without storm days 17.0–17.6%, storm share 9–11% (s0, s1, s4, s6; s1e excluded as stated) from `presentation_numbers.json → alarm_weather_check.wape_by_strategy_all_zones`. Outer-borough WAPE 41.2 / 40.3 and bias −10.8 / −7.0 / −6.0 / −6.9 from `adaptation_summary.json`.
- F6c title "p = 0.0001" is 9.8e−05 rounded. F4g title r = 0.92 / 0.90, 71–83%, 27% match round 1's sources.

No untraceable number found.

## Method sanity (Phase 7)

The round-1 fix commit changed comments and docs only: the AST check shows 14 of 14 Python files identical, and no figure, results file (other than counts and timestamp) or config changed. Nothing in the method changed. The 2026-Q1 "four strategies" ranges correctly leave out the s1e sensitivity (18.2%).

## Figures

I opened F4g and F6c, which are in the README grid and were not opened in round 1. Both have axis labels with units or meaning, source footers, a CBD accent of `#B23A48` and titles backed by the results. F4g's map uses the teal app-share palette rather than the plan's single-hue blues. This passed in `reviews/phase_7.md` and is not reopened here. No figure changed since then.

## Decisions check

The round-1 fixes are recorded (DECISIONS l.292), and the edits to l.290–291 are the ones round 1 requested. The redaction entry (l.290) is accurate, but it is where the release defect sits (Fix 1).

## Fix list

1. In `DECISIONS.md` l.290 (the 2026-11-15 redaction entry), describe what was removed by location only: former PLAN §8; one row and one note in PLAN §2; the motivation sentence of Amendment 1; one phrase each in Amendment 4's stack heading and rationale; wording in CLAUDE.md, in `reviews/checkpoint_7_advisor.md` and in `reviews/phase_4.md`. Do not quote any removed phrase or section title, do not name the motivation, and replace the quoted grep pattern with "a grep for the removed terms". Keep the date, phase, reason and alternative rejected. In l.292 item (1), say "one word in Amendment 4's rationale" instead of quoting it.
2. In `reviews/final_round1.md`, reword l.21 (DoD row), l.63 (Fix 1) and l.74 (history note) so they do not name the removed content or say how to recover it from git. For example: "one residue of the redacted wording in PLAN l.397"; "replace one word in Amendment 4's rationale"; "the text removed in the 2026-11-15 redaction". Do not change the verdict, the fix numbering or the options listed. This is the same kind of edit as the 2026-11-15 redaction of `reviews/checkpoint_7_advisor.md`. Record it in the l.290 entry.
3. In the `Makefile`, change the `dbt` target's description from "Checkpoint-1 checks (03b, 03c)" to words, e.g. "then the data-quality results (03b) and the vendor, record-format, trip-level CBD-fee and modeled-zone checks (03c)". `tests/test_make_targets.py` keeps the README table in sync; update the README row with it.
4. Follow-up: if a DECISIONS entry is appended for these fixes, update README "(240 entries)" to the new count and rerun `scripts/23_presentation_numbers.py` so `repository.decisions_entries` and `review_files` (27 with this file) match. Then rerun `make verify PHASE=7` and the AST check.

After the fixes, `git grep -I -i` for personal, non-technical notes should return only technical uses.

## Escalation reasons

None. Observations for the owner, not blockers:
- The history question from round 1 is answered in the DECISIONS entry "Public history" (l.294). Fixes 1–2 are still needed, because the public tree is this tree.
- Five test modules (`tests/conftest.py`, `test_backtest.py`, `test_conformal.py`, `test_metrics.py`, `test_seasonal_naive.py`) have no module docstring. The requirement covers scripts and library modules; adding one line each is optional.

## Amendments made

None.
