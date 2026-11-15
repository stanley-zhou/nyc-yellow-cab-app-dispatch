# Final review, round 3: whole repository before publication (Phase 7 scope + E3 + release changes of 2026-11-15)

Reviewed at commit `df096e2` on 2026-11-15. The scope and the owner's release requirements are the same as in `reviews/final_round1.md` and `reviews/final_round2.md`.

## Verdict

**PASS.** All four round-2 fixes are applied correctly. Every release requirement is now met in the tree. `ruff`, `pytest` (139 tests, 0 skipped), dbt (62/62) and `make verify PHASE=7` pass. Every number I traced has a source row. Between round 2 and HEAD, no result, figure, code path, decision or review verdict changed: the only Python changes are module docstrings on five test files, and they are AST-identical once docstrings are stripped.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| `make all` reproduces every figure from `results/` | MET | No figure, figure code, config or results file other than `presentation_numbers.json` (counts and timestamp) changed since round 2 (`git diff 7c5a2ee HEAD --stat`). The figures are the ones accepted in `reviews/phase_7.md`. |
| README: summary, figures, targets, hardware/runtime, licence, limitations | MET | README.md. I re-traced the numbers in the next section. |
| CI: ruff, pytest, `make smoke` | MET | `.github/workflows/ci.yml` (unchanged). |
| Amendment 6 summary, structure and D2 wording; Amendment 5 rule against causal sentences | MET | `reports/analysis.md`, `appendix.md` and `dashboard_spec.md` are unchanged since round 2, which checked them. The D2 sentence is verbatim in dashboard_spec View 3. |
| E3 (Snowflake target, load, build and tests, parity, CI on DuckDB) | MET | `dbt_targets.json → parity` (9 marts, `cells_differing` 0, `relative_tolerance` 1e-9). `snowflake_load.json` (`all_match` true, `wall_seconds` 960). `dbt/profiles.yml` reads every credential through `env_var`. |
| Release: public tree free of personal, non-technical notes | MET (was NOT MET) | `DECISIONS.md` l.290 now describes the redaction by location only and quotes none of the removed text. `reviews/final_round1.md` l.21, l.63 and l.74 no longer describe the removed text. A `git grep -I -i` for personal, non-technical notes finds only technical uses. PLAN §2 (the old course project) contains technical provenance only. |
| Release: no machine-specific paths, e-mail addresses, Snowflake identifiers | MET | No e-mail address, `/home/<user>`, `C:\Users`, `/Users/` or scratch path is in the tracked files. Snowflake appears only as `SNOWFLAKE_*` `env_var` names. `results/` has no account, user or warehouse fields. The Colab notebook has no outputs and uses only generic `/content/drive/MyDrive/...` paths. The public GitHub and Tableau profile URLs are intended. |
| Release: script/module docstrings state what each does, reads and writes; internal labels in words | MET (was PARTIAL) | All 50 scripts and all `src/` modules state their I/O, or say they hold only package markers or no code. Round 2's non-blocking item is done: the five test modules now have docstrings. Labels: the `dbt` row now reads "the data-quality results (03b) and the vendor, record-format, trip-level CBD-fee and modeled-zone checks (03c)". No `make help` row now uses an internal label without words. Script numbers in parentheses are file prefixes. |
| Release: `make help` matches README table | MET | Compared `make help` with the README table row by row: 25 rows, identical. `tests/test_make_targets.py` passes. |
| Release: `results/INDEX.md` covers every results file | MET | My own check: every tracked file under `results/` is named in INDEX.md, with none missing. `tests/test_results_index.py` passes. |
| Release: lock file committed; README states install command | MET | `requirements-dev.lock` and `requirements-snowflake.lock` are tracked (`dbt/package-lock.yml` as well). README "Setup" gives `uv python install 3.12`, `uv venv`, `uv pip sync … requirements-dev.lock` and `uv pip install --no-deps -e .`. |
| Release: no result, number, decision or verdict changed | MET | `git diff 7c5a2ee HEAD -- results/`: only `generated_utc`, `decisions_entries` 240→241 and `review_files` 26→27. `reviews/`: `final_round2.md` was added. In `final_round1.md`, four lines were reworded; its verdict (FIX), fix numbering 1–6 and the listed options are unchanged. DECISIONS: l.290–291 were reworded as round-2 Fix 1 asked, and l.292 was appended; no decision content changed. Since `a32b2d5` (E3 PASS), the only edits to earlier reviews are one phrase in `checkpoint_7_advisor.md` and a scratch path in `phase_4.md`; no verdict line was touched. |

## Test output

- `ruff check .`: `All checks passed!`
- `pytest --collect-only`: `139 tests collected`. This matches README "139 tests" and `presentation_numbers.json → repository.tests_collected`.
- `make verify PHASE=7` (exit 0): `ruff PASS · pytest PASS · no_skips PASS · dbt_test PASS (PASS=62 WARN=0 ERROR=0 SKIP=0) · outputs PASS`. The output files present include `alarm_weather_check.csv`, `snowflake_load.json`, `dbt_targets.json`, `e3_duckdb_sql_check.json`, `F4b_effect_map.html` and `ci.yml`.
- `grep -c "^- \[20" DECISIONS.md` = 241. This matches README "(241 entries)" and `repository.decisions_entries`.
- `ls reviews | wc -l` = 27 before this file, which matches `repository.review_files`. It will be 28 once this file is committed. The README does not quote this count.

## Number trace

The only changed number is README "(241 entries)": `presentation_numbers.json → repository.decisions_entries` = 241, which equals the grep count above.

I also re-traced the README numbers from the source fields myself. All match after rounding:
- 27.3%, 703,268 → 895,177, +199,068, −7,159 (−1.1%): `presentation_numbers.json → citywide_accounting.by_area.all` (`change_pct` 0.272882, `app_change`, `street_change` −7159.37, `street_change_pct` −0.01055).
- 25.6% / 24.0%, trips per cab-day 14.0–15.0: `presentation_numbers.json → supply`. The range is 14.005–15.023 for 2023 onward.
- −34.6%: `did_static.json → estimates.main.terms.treated_post.pct` −0.34645. −5.2%: `pre_volume_weighted_not_preregistered` −0.05202. +2.0%: `figure_stats_phase4.json → counterfactual.mean_post_monthly_rel` 0.019826.
- WAPE 16.4% / 16.2% / 23.7%, February 2025 to September 2026: `adaptation_summary.json → headline` `s0|all` 0.16433, `s1|all` 0.16201, `sn|all` 0.23698. `eval_window` is 2025-02-01 → 2026-09-30.
- 89/89, 1e-9, 63.3 s: `dbt_targets.json`. 16.0 min: `snowflake_load.json → wall_seconds` 960. 47.6 s and 11.68 GiB, 12 cores: `runtimes.json → measured.smoke` and `machine_resources.json`.
- Designs (8 of 10 stopped; −34.6% gate p 2.7e−10, −5.2% gate p 1.6e−17, synthetic control rank 11 of 16): `presentation_numbers.json → preregistered_checks`.
- F4d title (+2.0%, −34.6%, −5.2%) and footer (−40.5%, −11.3%): same sources as above and in round 1.

Rounds 1 and 2 traced analysis.md, appendix.md and dashboard_spec.md, and none of them changed since. No untraceable number found.

## Method sanity (Phase 7)

The round-2 fix commit changed documentation, a Makefile description string, test docstrings and the repository counts. The AST check of `7c5a2ee → HEAD` gives 5 of 5 changed `.py` files identical once docstrings are stripped. No method, model, threshold or figure changed.

## Figures

I opened F4d (README grid; not opened in rounds 1–2). It has a y-axis label with units ("CBD pickups vs comparison (%)"), direct labels and no legend, a policy line with its date, and a source footer. The title states the three estimates the results support. The title runs to three lines, which `reviews/phase_7.md` accepted. No figure changed since the Phase 7 PASS.

## Decisions check

The round-2 fixes are recorded in DECISIONS l.292, and the edits to l.290–291 are the ones round 2 requested. On the one count in l.290: "four phrases in PLAN and CLAUDE.md reworded neutrally" counts distinct phrases. Some of them were reworded in more than one place (seven occurrences across PLAN and CLAUDE.md). That reading is accurate, so this is not a defect. Every release choice (lock files, `make setup`, removed `.gitkeep`, kept non-regenerated results files, orphan-commit publication) has a line with its reason.

## Fix list

None.

## Escalation reasons

None. Notes for the owner, not blockers:
- `repository.review_files` in `presentation_numbers.json` will read 27 while `reviews/` holds 28 once this file is committed. The README does not quote the count. Rerun `scripts/23_presentation_numbers.py` before the release snapshot if the field should be exact.
- The history of the public repository is recorded in the DECISIONS entry "Public history" (l.294).

## Amendments made

None.
