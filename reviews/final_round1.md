# Final review: whole repository before publication (Phase 7 scope + E3 + release changes of 2026-11-15)

Reviewed at commit `83be64c` on 2026-11-15. Scope: README.md; reports/analysis.md, appendix.md, dashboard_spec.md; E3 (PLAN Amendment 4); the DECISIONS.md entries of 2026-11-15 (redaction; release checklist) checked against the owner's six release requirements.

## Verdict

**FIX.** Tests, dbt and ruff are green; every number in the README, the report and the appendix that I traced has a source row. All results and verdicts are unchanged. But two release requirements are only partly met, and the report has one number whose stated period does not match its source. Six fixes, none outside the plan.

## DoD table

Phase 7 DoD and Amendment 6 (A/B) items were PASSed in `reviews/phase_7.md`; E3 in `reviews/e3.md`. Here I re-check them at HEAD and add the owner's release requirements.

| Item | Status | Evidence |
|---|---|---|
| `make all` reproduces every figure from `results/` | MET | Phase 7 review showed byte-identical figures. Since then no figure code changed: AST comparison with docstrings stripped, `88c2ede^` → `88c2ede`, shows 63 of 63 changed `.py` files identical (only the 2 new test files differ). |
| README renders; summary, figures, targets, hardware/runtime, licence, limitations | MET | README.md; runtimes trace to `results/runtimes.json`, `snowflake_load.json` (960 s), `dbt_targets.json` (63.3 s; 26 models + 62 tests + 1 seed = 89). |
| CI runs ruff, pytest, `make smoke` | MET | `.github/workflows/ci.yml` (setup, ruff, smoke, pytest). |
| Amendment 6 executive summary, structure, D2 wording | MET | analysis.md Summary (3 findings, untested/unidentified, recommendation); D2 sentence verbatim in §4 and in dashboard_spec View 3. |
| Amendment 5 rule: no causal sentence | MET | No sentence says app dispatch caused growth or that congestion pricing had or had no effect; README/analysis Limitations say so explicitly. |
| E3: Snowflake target with env_var only; stage/PUT/COPY INTO load; dbt build + all tests on Snowflake; portable macros; per-target counts in `dbt_targets.json`; CI on DuckDB | MET | `dbt/profiles.yml` (env_var), `results/snowflake_load.json` (`all_match: true`), `dbt_targets.json` (`tests_pass` 62/62, `parity.all_identical: true`, 9 marts `cells_differing: 0`), `int_speed_trips` 4-row gap explained in `reviews/e3_round1.md`. |
| Release: public tree free of personal notes | PARTIAL | `git grep` finds only technical uses (downloads, Colab chunks). One residue: one word in PLAN.md l.397 (Amendment 4, "Why.") with a personal sense. |
| Release: no machine-specific paths, e-mail addresses, Snowflake identifiers | MET (tree) | No `/home/<user>`, `C:\Users`, e-mail, account locator or user name in tracked text files. Remaining: generic `/mnt/c`, `~/.snowflake/taxi.env` (generic), public Tableau profile URL (intended). See the history note under Escalation reasons. |
| Release: every script and module docstring says what it does, reads and writes; internal labels in words | PARTIAL | All 50 scripts state their reads and writes. In `src/`, 14 modules give no reads/writes statement, not even "no file I/O" (list in Fix 3), although DECISIONS l.291 says "every module docstring says what it does, reads and writes". Labels: the `adapt` row of `make help` / README uses "S1", "S6", "S1e" without words. |
| Release: `make help` matches README table | MET | Visual diff and `tests/test_make_targets.py::test_readme_table_matches_make_help` pass. |
| Release: `results/INDEX.md` covers every results file | MET | `tests/test_results_index.py` passes; 126 tracked files, each listed once; only untracked file is `results/stat_runs.lock` (git-ignored). Quoted-in column checked against the four documents: consistent (the `dashboard_spec.md` entries refer to the Tableau extracts, as the rows say). |
| Release: lock file committed; README states install command | MET | `requirements-dev.lock` (143 pins), `requirements-snowflake.lock` (148); `make setup` runs `uv pip sync` + `--no-deps -e .`; README "Setup" lists the four commands. |
| Release: no result, number, decision or verdict changed | MET | `git diff a32b2d5 HEAD -- results/ reviews/`: INDEX.md added; `presentation_numbers.json` only `generated_utc`, `decisions_entries` 237→239, `tests_collected` 136→139; two review lines reworded (one phrase in the advisor review, scratch path → file name), no verdict touched. DECISIONS: two lines appended in `88c2ede`, one of them amended in `83be64c`; no earlier line edited. Code unchanged per the AST check. |

## Test output

- `ruff check .` → `All checks passed!`
- `pytest -q` → all pass; 139 collected (matches `presentation_numbers.json → repository.tests_collected` and README "139 tests").
- `make verify PHASE=7` (exit 0): `ruff PASS · pytest PASS · no_skips PASS (0 skipped) · dbt_test PASS (PASS=62 WARN=0 ERROR=0) · outputs PASS` (README, analysis, appendix, presentation_numbers, alarm_weather_check, snowflake_load, dbt_targets, e3_duckdb_sql_check, F4b html, ci.yml).
- DECISIONS entry count: `grep -c "^- \[20" DECISIONS.md` = 239 = README "(239 entries)".

## Number trace

Every number below matched its source after rounding. I checked them by reading the source field, not by trusting the link.

- **README / analysis summary / F0 title / dashboard View 0:** 27.3%, 703,268 → 895,177, +199,068, −7,159 (−1.1%): `presentation_numbers.json → citywide_accounting.by_area.all`. 2.3% / 29.6%: `channel_restatement.json` 2023-01 / 2026-01 CBD. 2.1–2.7-fold, −2.7% to +7.8%, the area table: `january_2025_step`. 25.6%, 24.0%, 14.0–15.0, 104,422 → 131,133, ~7,040 → 8,720: `supply` / `incrementality_dml.json → supply`. −34.6% [−47.7, −18.3] p=0.0004: `did_static.json → estimates.main`. −5.2% [−12.8, +3.0]: `pre_volume_weighted_not_preregistered`. +2.0%: `figure_stats_phase4.json → counterfactual.mean_post_monthly_rel`. LOO −36.3 to −32.0: exp of `leave_one_zone_out` min/max. −13.8%: `placebo.json → placebo_in_time`. 9.5%: `pretrend_test_size.json` `reject_5pct_F_hotelling`. 71–83%, 27%, r=0.92/63, 0.90/200: `figure_stats_phase4b.json → c1`, `app_dispatch_summary.json`.
- **Designs table:** every estimate and gate p-value and the 10/8/1/1/2 counts: `presentation_numbers.json → preregistered_checks`. 4.4×: `lyft_curb_cmt_ratio.pre_mean` 4.38. 0.52–2.62, 0.90 [0.74, 1.06]: `incrementality_dml.json` (plpr θ 0.522; first difference 2.620).
- **Forecasting:** 16.5 / 16.7 / 24.1 (2024): `forecast_summary.json`; not distinguishable: `wape_gap_bootstrap.csv` (all, chronos vs lgbm, CI [−0.0053, +0.0007]). Strategy table, 0.23 pts, bias −10.8/−2.0/−7.0/−6.0, 384 s, 411 s, 720 s, 250 s: `adaptation_summary.json`, `adaptation_gaps.csv`. 6.3% / 5.3%, alarm dates: `figure_stats_phase3.json`. 7.5 / 5.5 in, −50.6 / −72.7%: `alarm_weather_check` block. 103 zones, 99.04%: `modeled_zones.json`. 12.5 GB / 11.68 GiB, 12 cores: `machine_resources.json`.
- **Appendix:** 331,436,471 / 2.97%: `data_quality.json`. 87.8%, 99.97%: `channel_label_validation.json`. 15.6% / −16.7%: per-week values in `channel_monthly.csv` / `channel_restatement.json`. CMT block 93/99/3%/43 min: `cmt_block_diagnosis.json`; 13.3% → 89.4%: `channel_restatement.json → other.app_share_excl_cmt_block`. −0.166, −0.381, +4.388: `cross_platform.json`; 0.75% → 10.86%: `cross_platform_monthly.csv`. −1.0% full control: `did_static.json`; 500 / 54 placebos: `power_mde.json`. Synthetic control rank 11 of 16, p 0.69, +4.6%: `synth_control.json`, `preregistered_checks`. −40.5% / −11.3%: exp of `figure_stats_phase4.json → counterfactual.did_*_post_mean`. Switchback 3,756–5,922 zone-blocks, 4.7–7.4 days, 67 zones, sd 33.1, 3,466 days: `experiment_design.json`.
- **Mismatch (Fix 2):** analysis.md §5 "From February 2025 to September 2026 … the CBD app share rose from about 18% to about 30% ([channel_restatement.json])". The source has 17.8% for **January 2025** and 29.6% for **January 2026**. For the stated period, `channel_monthly.csv` gives 22.3% (2025-02) and 31.3% (2026-09, 3 panel weeks), with a dip to 20.8% in 2026-04. The number is sourced but attached to the wrong period.
- **Wording (Fix 5):** README "nine … marts match DuckDB exactly". `dbt_targets.json` records `identical: true` at `relative_tolerance` 1e-9, while `max_relative_difference` goes up to 2.2e-14 on float columns. Integer columns are exact; float columns are equal within tolerance.

## Method sanity (Phase 7)

- Figures come from `results/` only (Phase 7 review), and the release commit changed no code (AST check above). The `make all` order matches the README.
- E3: `features_demand` and the daily/hourly marts are in the parity set; Snowflake's narrower coverage (2023+) explains the lower row counts.
- Fresh-clone evidence: DECISIONS l.291 item (8) gives 63.4 s for smoke; README quotes 47.6 s from `runtimes.json → measured.smoke` (the working-copy run). Both come from records and do not contradict each other.

## Figures

I opened F0 and F5. Units are on the axes, the policy line is drawn, direct labels/legend are used sensibly, and the titles state findings the results support. F5 draws the frozen model in grey (baseline), consistent with `style.py`. No figure changed since the Phase 7 PASS. In the dashboard as built, "Manhattan outside the CBD" is `#9AA5B1` where `style.py` has non-CBD `#8A8F98`. That is Tableau and documented in the spec, so it is not a defect of the repository figures.

## Decisions check

The release changes are recorded (DECISIONS l.290–291), but one claim in them is not accurate: "every module docstring says what it does, reads and writes" (see Fix 3). Lock-file choice, `make setup` change, `19_experiment_design.py` in `make channel`, removed `.gitkeep`, and the kept non-regenerated results files are all recorded with reasons.

## Fix list

1. In `PLAN.md` l.397 (Amendment 4, "Why."), replace the word flagged in the DoD table with neutral wording. This is the same class of edit as the 2026-11-15 redaction. Add it to that DECISIONS entry.
2. In `reports/analysis.md` §5 ("Robustness"), make the app-share numbers match their period. Either write "from 17.8% (January 2025) to 29.6% (January 2026)" citing `channel_restatement.json`, or use `channel_monthly.csv` for February 2025 → September 2026 (22.3% → 31.3%, noting September 2026 has 3 weeks) and cite that file.
3. Add one sentence on file access to the module docstrings of `src/taxi_shock/backtest.py`, `causal/counterfactual.py`, `causal/did.py`, `causal/event_study.py`, `causal/placebo.py`, `conformal.py`, `drift.py`, `evaluation.py`, `features.py`, `metrics.py`, `models/base.py`, `models/lgbm_quantile.py`, `models/seasonal_naive.py`, `models/stat_baselines.py`. For pure-computation modules use "Pure computation on DataFrames; reads and writes no files", as `adapt.py`, `shock.py` and `channel.py` already do. This makes the DECISIONS l.291 claim true. Docstring-only change: re-run the AST check.
4. In the `Makefile` `adapt` description (and so the README table, kept in sync by `tests/test_make_targets.py`), describe the strategies in words with the labels in parentheses, e.g. "monthly-retrain (S1) and app-share-feature (S6) refits and the expanding-window sensitivity (S1e)".
5. In `README.md` "Methods and stack", replace "match DuckDB exactly" with "match DuckDB on every cell (relative tolerance 1e-9; integer columns exact)" or equivalent, per `dbt_targets.json → parity`.
6. In `reports/analysis.md` §5 ("Accuracy"), add the link to `results/wape_gap_bootstrap.csv` for "not distinguishable by a paired bootstrap". Neither cited file holds the bootstrap.

After the fixes, rerun `make figures` only if `23_presentation_numbers.py` is rerun. `repository.review_files` will read 26 once this file is committed. The README does not quote it.

## Escalation reasons

None for the verdict. **One item for the owner's decision, outside what the Builder can fix in the tree:** the git *history* still contains (a) the commit author's personal e-mail address in every commit's metadata, and (b) the text removed by the 2026-11-15 redaction, in earlier commits. The owner's requirement names the public *tree*, which is met. If the repository is made public with its full history, both remain visible. Options: publish a fresh single-commit or squashed history, rewrite author metadata (e.g. `git filter-repo --mailmap`, or a GitHub noreply address), or accept. This review does not repeat the address.

## Amendments made

None.
