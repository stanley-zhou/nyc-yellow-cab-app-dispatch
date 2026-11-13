# Phase 6 review (round 2): HVFHV streaming, C6 (FHV congestion pricing), Amendment 4/4a D0–D5b

Reviewer: phase-reviewer subagent (fresh context), 2026-11-13. Commit reviewed: 73af7fa (working tree clean); round-1 fixes in 516eb1d. Round-1 review kept at `reviews/phase_6_round1.md`.
Scope = `config/phase_outputs.yaml → 6`. PLAN gives Phase 6 no formal DoD, so the DoD below comes from PLAN Phase 6, Amendment 3 C6, Amendment 4/4a (HVFHV disk decision, D0–D5b) and the 11 round-1 fix items.

## Verdict

**FIX** (fix round 2 of 2).

All 11 round-1 fixes were applied, and I verified each against code and results (table below). Three new problems remain:
- The F6 y-label fix created a rendering defect: the label is longer than the axis and runs into the title and the caption.
- The D5b DECISIONS entry still says the HVFHV trip-type DiDs have "no pre-trend test". They now have one, and it rejects (p 2.5e−87).
- The D2 panel estimator is now reproducible, but its value depends on the fold draw: CBD 0.555, 0.522 and 0.497 across three draws. That spread straddles the 0.5 bound used to judge the expectation.

None of these is a downgrade of a mandatory item, and none is a repeat of a round-1 failure. If any of them survives this round, it becomes ESCALATE (CLAUDE.md).

## DoD table

| Item | Status | Evidence |
|---|---|---|
| HVFHV 2023-01 → 2026-09 streamed: download → aggregate → verify → delete, manifest | MET | `results/hvfhv_stream_log.csv` (45 verified); `data/raw/hvfhv_manifest.csv` |
| Aggregates (i) zone × hour × … and (ii) pair × week | MET | `scripts/11_hvfhv_stream.py`; `tests/test_phase6.py::test_hvfhv_aggregate_trip_types_bins_and_accounting` |
| Disk report first; 15 GB guard | MET | `results/hvfhv_disk_report.json`; minimum free space 37.5 GB |
| HVFHV totals saved (round-1 fix 5) | MET | `results/hvfhv_summary.json`: requested 25,030,805; requested and matched 11,589,706; matched in total 11,632,513; matched without request 42,807 |
| C6: Phase-4 design, platform split, weighted and equal weight, pre-trend test first, stop if it rejects | MET | `results/fhv_did.json`: 4 series × 2 weightings, all `passes: false`, no `estimate` key; test `test_c6_gate_withholds_the_estimate_when_pretrends_reject` |
| C6: event-study path summaries saved (fix 4) | MET | `fhv_did.json → series.*.*.event_study_path` (pre, post, pre_2023, pre_2024 min/max/mean) |
| Lyft January 2025 separate | MET (by the rule) | `channel_did.lyft_splits` in config; computed only for a passing series |
| F6 taxi vs FHV on one axis | PARTIAL | renders; y-label overflow (Figures) |
| No FHV forecasting | MET | none |
| D0–D5b result files, F6a–F6e | MET | `make verify PHASE=6` outputs PASS |
| D2 seeded (fix 1) | MET | `scripts/12_incrementality.py:189`. I re-ran it: CBD PLPR 0.497258 [0.387327, 0.607189] twice, identical to `results/incrementality_dml.json`; primary DML 0.897780, also identical |
| D5b joint pre-trend tests (fix 6) | MET | `app_share_policy_step.json → yellow.pretrend.*`, `hvfhv.pretrend_uber_lyft_cell_weighted`; p in the F6e title |
| Per-week monthly means (fix 3) | MET | `n_weeks` and `*_per_week` in `channel_monthly.csv`, `channel_restatement.json`, `cross_platform_monthly.csv` |
| Tests for Phase-6 code (fix 8) | MET | `tests/test_phase6.py`, 4 tests covering (a)–(d) as specified |
| Dates moved to config (fix 9) | MET | grep for quoted date literals in `scripts/10*–17*` returns nothing; `channel.cmt_block_diagnosis`, `channel.motivation_months`, `channel_did.step_weeks_each_side`, `channel_did.lyft_splits` |
| `make all` rebuilds Phase-6 tables (fix 10) | MET | `Makefile`: `all: … causal hvfhv channel fhv adapt figures report`. `adapt` and `report` still exit 1, but that is pre-existing (Phases 5 and 7), not this phase |

## Test output

- `ruff check .`: All checks passed!
- `make verify PHASE=6` (1 min 41 s), exit 0:

  | Check | Result |
  |---|---|
  | ruff | PASS |
  | pytest | PASS (124 tests, 0 skipped) |
  | no_skips | PASS |
  | dbt_test | PASS (PASS=62 WARN=0 ERROR=0) |
  | outputs | PASS (incl. new `results/hvfhv_summary.json`) |

- `pytest tests/test_leakage.py tests/test_phase6.py`: 27 passed.
  - `test_leakage.py` poisons values at and after the origin and asserts unchanged forecasts. It is not a placeholder, and this phase does not touch it.
- Reproducibility check (scratch script that calls `plpr()` twice with an RNG draw between the calls): identical θ, equal to the committed file.

## Number trace

All traced to `results/`:
- **Fix-commit DECISIONS entries:**
  - panel θ 0.497 [0.387, 0.607] / 0.473 / 0.866 → `incrementality_panel_summary.csv`
  - D3 67 zones → `lyft_entry.json → n_zones`
  - per-week CBD 392,751 → 453,882 (+15.6%), street 383,608 → 319,640 (−16.7%), outer 10,924 → 65,310 and 6,945 → 47,560 → `channel_restatement.json`
  - FHV CBD 1.207 M → 1.102 M per week (−8.7%) → `cross_platform_monthly.csv` (n_weeks 5 / 4)
  - every C6 path range (Uber + Lyft, Uber, Lyft, shared; both weightings; pre and post) → `fhv_did.json → event_study_path`
  - HVFHV shared counts → `hvfhv_summary.json` (requested − requested and matched = 13,441,099 ✓)
  - D5b pre-trend p 3.9e−27 / 6.1e−50 / 1.5e−55 / 2.5e−87 → `app_share_policy_step.json`
  - D5b log points 0.098 [0.022, 0.175] / +10.3%, −0.067 / −6.5%, −0.052, −0.094, −0.003 → same file
- **Figure titles:**
  - F6 p 2e−17 / 2e−18 → `did_by_channel.json`, `fhv_did.json`
  - F6a +105.0k / −5.9k / +42.8k / +0.7k → `channel_decomposition.csv`
  - F6c 0.90 [0.74, 1.06], 1.18 [1.00, 1.35] → `incrementality_dml.json`
  - F6d −1.12, 0.68 [0.09, 1.23] → `lyft_entry.json`
  - F6e +11.3 / +11.1 / +8.1 / +10.6 pp, +3.0 pp, p 4e−27 → `app_share_policy_step.json` (also stored in `figure_stats_phase4c.json`)
- **README:** unchanged; no Phase-6 numbers. `reports/analysis.md` does not exist yet (Phase 7).
- **Commit message 516eb1d:** contains no numbers.

Imprecise (no wrong number, but the wording does not match the saved rows):
1. **D5b entry, pre-weeks.** It says "+1–2 pp in some pre-weeks (−26 to −21, −5 to −3)". In `app_share_step_event_study.csv` the significant pre-weeks are −26 to −22, −18, −17 and −5 to −3; −21 is +0.24 and not significant.
2. **C6 entry, December bins.** It says "Dec 2023 and Dec 2024 are the lowest pre bins" for "Uber and the total". From `fhv_event_study.csv`, the three lowest pre bins are:

   | Series | Weighting | Three lowest pre bins (k) |
   |---|---|---|
   | `fhv_all` | weighted | −1, −5, −13 (Dec 2024, Aug 2024, Dec 2023) |
   | `fhv_all` | equal | −5, −7, −4 |
   | `fhv_uber` | equal | −5, −2, −1 |
   | `fhv_uber` | weighted | −1, −5, −2 |

   The claim holds only loosely, and only for the weighted total. (I wrote this phrasing in round 1 for `fhv_all` weighted; the Builder generalised it.)

## Method sanity

- **C6.** Unchanged from round 1 and correct. The gate logic now sits in `analyse()` and is unit-tested both ways: a planted pre-trend gets no estimate, a parallel panel gets an estimate near 0.
- **HVFHV quality rule.** Now recorded with its rejected alternative (P6 entry, item 9). The reasoning is acceptable.
- **D2.**
  - The `plpr()` seed fix works. `DoubleMLPanelData(static_panel=True)` sets `cluster_cols = id_col`, so the PLPR SEs are zone-clustered, as the F6c caption says.
  - **New concern: fold-draw sensitivity.** Three fold draws gave CBD 0.555 (first run, 1021ffe), 0.522 (the value quoted in round-1 DECISIONS) and 0.497 (seed 20260107).
    - The spread (0.06) is about a quarter of the CI width, but it crosses the 0.5 upper bound of Amendment 4's CBD expectation ("θ between 0 and 0.5"). DECISIONS uses that bound for "only the panel estimator is near (0.50)".
    - One seed must not decide which side of the bound the estimate falls on.
    - DoubleML supports repeated cross-fitting (`n_rep`). Report the median over repetitions and the range. The fit takes seconds.
- **D5b.**
  - Every pre-trend test rejects, so the DiDs are correctly downgraded in the P6 entry, and F6e says so in its title.
  - The pre-specified reading rests on the descriptive step comparison (+8.1 to +11.3 pp for the CBD-touching types vs +10.6 pp for trips touching neither end), which needs no parallel-trends assumption. Sound.
  - The log-count event studies now use the cell weights, consistent with the weighted DiDs. The app-share event study and DiD both use per-cell trips as weights, so the title pairs a DiD with a pre-trend test from the same specification.
- **Per-week restatement.** Correct. The CBD monthly "decline" in Amendment 4's motivation is a 5-vs-4-week artefact: +15.6% per week. This goes to Stanley at Checkpoint 6 (storyline is outside reviewer bounds).

## Figures

- **F6_taxi_vs_fhv: DEFECT.**
  - The new y-label "CBD vs control, relative to the week before 2025-01-05 (%)" is one line longer than the 4.2 in axis.
  - It overprints the first characters of both title lines ("Taxi", "(yellow") and the first two caption lines ("Monthly", "treated").
  - Visible in the PNG at 7 in. The legend is still used where direct labels would do (minor, carried over).
- **F6a.** Policy line labelled in the CBD panel, with headroom added. Fixed.
- **F6b.** Unchanged since round 1. Fine.
- **F6c.** Shows panel θ 0.50, consistent with the results. Caption claims are correct (see D2).
- **F6d.** Curb cabs now use `comparison` (purple), CMT uses `non_cbd` (grey). Fixed. A policy line is not applicable (x starts 2025-06).
- **F6e.**
  - Title carries the pre-trend p. Palette is consistent (CBD-touching types in CBD red, "neither" in grey).
  - The right (event-time) panel's policy line is unlabelled, but the left panel carries the label. Acceptable.

## Decisions check

- **Present now:**
  - HVFHV no-filter rule;
  - C6 own-series weights;
  - PLPR seed;
  - all new config keys.
- **Stale:** the D5b entry (DECISIONS l.260) still ends "…these are DiDs on trip types without a pre-trend test and are descriptive". It also reads the HVFHV DiD as "consistent with the fee mattering for FHV". Both are contradicted by the pre-trend test the same fix round added (`hvfhv.pretrend_uber_lyft_cell_weighted.p_F_hotelling` = 2.5e−87). The P6 entry corrects this, but the D5b entry itself must not contradict it.
- **Missing:** the choice of a single fold draw for PLPR vs repeated cross-fitting (see Fix 3).

## Fix list

1. `src/taxi_shock/viz/figures.py` (`f6_taxi_vs_fhv`): make the F6 y-label fit the axis. Either wrap it to two lines (`textwrap.fill(…, 30)`), or use a short label such as "CBD vs control (%)" and move "relative to the week before 2025-01-05" into the caption. Re-render and confirm that nothing overlaps the title or the caption.
2. `DECISIONS.md`, D5b entry (l.260):
   - Replace "without a pre-trend test and are descriptive" with the saved pre-trend result (`hvfhv.pretrend_uber_lyft_cell_weighted`, p 2.5e−87: rejects).
   - Drop or qualify "consistent with the fee mattering for FHV".
   - Correct the significant pre-weeks to −26 to −22, −18 to −17 and −5 to −3 (`results/app_share_step_event_study.csv`).
3. `scripts/12_incrementality.py` (`plpr()`) + `config/project.yaml` (`incr.n_rep`):
   - Fit `DoubleMLPLPR` with repeated cross-fitting (e.g. `n_rep=10`, still seeded).
   - Save the median θ, its CI and the min–max over repetitions in `results/incrementality_dml.json` and `incrementality_panel_summary.csv`.
   - Update the D2 DECISIONS entry and F6c with those values.
   - State whether the CBD panel estimate is within 0–0.5 across repetitions; record the choice in `DECISIONS.md`.
4. `DECISIONS.md`, C6 entry (l.257): restate the "Dec 2023 and Dec 2024 are the lowest pre bins" sentence by series and weighting from `results/fhv_event_study.csv` (weighted total: k = −1, −5, −13 lowest; equal weight: Jun–Sep 2024), or drop it.

## Escalation reasons

None. The C6, D2, D3, D5 and D5b results that contradict their expectations are handled by pre-registered rules and reported as found. They go to Checkpoint 6 together with the per-week restatement of Amendment 4's motivation (CBD yellow pickups +15.6% per week from 2023-01 to 2026-01, not a decline).

## Amendments made

None.
