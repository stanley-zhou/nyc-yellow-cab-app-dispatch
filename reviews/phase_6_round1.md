# Phase 6 review (round 1): HVFHV streaming, C6 (FHV congestion pricing), Amendment 4/4a D0–D5b

Reviewer: phase-reviewer subagent (fresh context), 2026-11-13. Commit reviewed: aab0e86 (working tree clean).
Scope = `config/phase_outputs.yaml → 6`: HVFHV streaming, C6, D0, D1, D2, D3, D4, D5, D5b, and figures F6, F6a–F6e. C3 was not in scope (Phase 4 list). Phase 6 has no formal DoD in PLAN. The DoD below is taken from PLAN Phase 6, Amendment 3 C6, and Amendment 4/4a (HVFHV disk decision, D0–D5b).

## Verdict

**FIX.**

The C6 gate was applied exactly as pre-registered. Every FHV series fails the pre-trend test, so no estimate is reported. That is correct, and it is not a reason to escalate here: Checkpoint 6 is the next human stop (Amendment 4 order of work).

The FIX items are:
- untraceable or wrong numbers in DECISIONS;
- monthly totals that compare 5-week months with 4-week months, which distorts the D4 and D1 statements and Amendment 4's motivating numbers;
- an unseeded estimator;
- no tests for any Phase-6 code except the break rule;
- hard-coded dates;
- a missing D5b pre-trend test;
- figure defects.

## DoD table

| Item | Status | Evidence |
|---|---|---|
| HVFHV range (Amendment 4: 2023-01 → 2026-09) | MET | `results/hvfhv_stream_log.csv`: 45 months, all `verified` |
| Stream: download → aggregate → verify → delete; manifest with URL, bytes, sha256, rows, date | MET | `scripts/11_hvfhv_stream.py`; `data/raw/hvfhv_manifest.csv` (45 rows, rows = stream log `rows_file`) |
| Aggregates (i) zone × hour × platform × shared flags × trip type × distance; (ii) pair × week × platform | MET | `data/processed/hvfhv/zone_hour_*`, `pair_week_*` (2.6 GB, git-ignored, DECISIONS l.256) |
| Disk report first; fstrim; stop below 15 GB | MET (fstrim not run: needs sudo, recorded) | `results/hvfhv_disk_report.json`; min free 37.5 GB in the stream log |
| Repeat Phase 4 for FHV, platform split, weighted + equal weight | MET under the C6 stop rule | `results/fhv_did.json`: 4 series × 2 weightings, 38 vs 25 zones |
| Pre-trend test first; stop if it rejects | MET | every `p_F_hotelling` ≤ 8.8e−6; no `estimate` key in any series |
| Lyft January 2025 separately | MET (via the rule) | estimate withheld; the Jan-2025 monthly bin (k=0) is in `fhv_event_study.csv` |
| Shared flags | MET | `fhv_shared` series; `shared_match` kept in the aggregates |
| F6 taxi vs FHV on one axis | PARTIAL | renders; y-label defect (see Figures) |
| No FHV forecasting | MET | none |
| D0–D5b result files and F6a–F6e present | MET | `make verify PHASE=6` outputs PASS |
| Tests for new code / data surprises (CLAUDE.md) | NOT MET | only `tests/test_channel.py` (2 tests, break rule). Nothing covers `11_hvfhv_stream.aggregate`, the C6 gate, the DML SEs or folds, D3, D4 or D5b |
| `make all` reproduces every table (PLAN §0.5) | NOT MET | `all:` omits `hvfhv`, `channel`, `fhv` |

## Test output

- `ruff check .`: All checks passed.
- `pytest -q`: 120 passed, 0 skipped (exit 0).
- `tests/test_leakage.py` run alone: passes (4 test functions, parametrised). It poisons values at and after the origin and asserts unchanged forecasts, as reviewed in Phase 2. Not affected by this phase.
- `dbt test`: PASS=62 WARN=0 ERROR=0.
- `make verify PHASE=6`: ruff PASS, pytest PASS, no_skips PASS, dbt_test PASS, outputs PASS (exit 0).

## Number trace

Traced, OK:
- **Commit messages:**
  - 2e−18 → `fhv_did.json fhv_all.pre_volume_weighted.p_F_hotelling` = 2.27e−18
  - 45 months / 904.7M → stream log
  - D4 −0.17 / −0.38 / +4.4, and 0.75% → 10.9% → `cross_platform.json`, `cross_platform_monthly.csv`
  - ~80× → 25,597 / 325 = 78.8
  - D5b ~11 pp and +3.0 pp [+0.9, +5.1] → `app_share_policy_step.json`
  - D3 −1.12 and 0.68 [0.09, 1.23] → `lyft_entry.json`
  - D2 0.90 [0.74, 1.06] and 1.18 → `incrementality_dml.json`
  - D1 +105k / −6k → `channel_decomposition.csv`
  - D0 0.020 → `channel_label_validation.json`
- **Figure titles:**
  - F6: yellow p 1.57e−17, FHV p 2.27e−18
  - F6a, F6b (`figure_stats_phase4c.json`)
  - F6c (0.898 / 1.176)
  - F6d, F6e
- **README:** has no Phase-6 numbers. Its Phase-4 numbers are reproduced by `did_by_channel.json → pickups` (−0.0534 [−0.1367, +0.0299]).
- **HVFHV:** Uber 659,003,496 + Lyft 245,680,351 = kept 904,683,847 ✓; shared requested 25,030,805 ✓ (aggregates).

Not traceable or wrong:
1. **D2 panel estimator.** DECISIONS l.255 reports CBD "0.522 [0.428, 0.616]", Manhattan non-CBD "0.489", and "only the panel estimator is near (0.52)". The committed `incrementality_dml.json` (unchanged since 1021ffe) has `dml_panel_plpr.theta` = 0.555 [0.435, 0.675] and 0.582. F6c plots 0.555. Cause: `plpr()` lets DoubleML draw folds with the unseeded global numpy RNG, so the number changes from run to run.
2. **D3 zone count.** DECISIONS l.254 says "63 zones" and "57 restrictions over 63 clusters". `lyft_entry.json → n_zones` = 67, and the pre-trend df [57, 66] / Hotelling [57, 10] imply G = 67.
3. **D4 FHV volume.** DECISIONS l.258 says "FHV trips picked up in the CBD 6.03 M (2023-01) → 4.41 M (2026-01)". Weeks are assigned to the month of their start, and 2023-01 has **5** weeks while 2026-01 has **4**. Per week this is 1.207 M → 1.102 M (−8.7%), not the −27% the pair implies.
4. **D1 restatement / Amendment 4 motivation (same artefact).** `channel_restatement.json` reproduces "CBD 1,963,754 (2023-01) → 1,815,527 (2026-01)" without saying that these are 5-week vs 4-week sums. Per week (from `results/channel_weekly.csv`):
   - CBD pickups: 392,751 → 453,882 (**+15.6%**), not a decline;
   - CBD street hails: 383,608 → 319,640 (−16.7%), not "fell by about a third";
   - `other` (with the block): 10,924 → 65,311 per week.
   The D1 decomposition itself uses weekly means and is correct.
5. **C6 description.** DECISIONS l.257: "every FHV pre-period month sits +15% to +28% higher". That is only `fhv_all`, pre-volume weighted (14.9% to 28.6%, so the upper end rounds to 29%). From `fhv_event_study.csv`:

   | Series | Pre-period months vs reference |
   |---|---|
   | Lyft | −9.0% to +5.9% (equal) / −8.1% to +11.1% (weighted) — not "higher" |
   | Uber | +18.8% to +38.7% (weighted) |
   | Shared | up to +67% |
   | `fhv_all`, equal weight | +8.6% to +26.9% |

   The "~+25% (2023) → ~+15% (late 2024) → ~+8–15% (2026)" drift has no saved row.
6. **Shared matched.** DECISIONS l.256 "matched 11,589,706" is requested-and-matched. Total matched is 11,632,513, including 42,807 matched-without-request rows. Both numbers come only from the git-ignored aggregates; no `results/` file holds them.
7. **D5b units.** DECISIONS l.260 writes log coefficients as percentages: "−6.7%" for −0.0671 (= −6.5%), and "+9.8%" for 0.0983 (= +10.3%). C6 and F6 use exp(b) − 1. Pick one convention.

## Method sanity

- **C6 design** is the Phase 4 primary (07b loaded directly): zone + week FE, weather × treated, CRV1 by zone, 38 vs 25 zones, reference = week of 2024-12-29, 24 monthly pre-bins, Hotelling F* at 5% (`channel_did.alpha`). Correct.
- **C6 reading for Checkpoint 6 (not a defect).**
  - In `fhv_all`, pre and post coefficients are both offset (+0.14 to +0.25 pre, +0.06 to +0.19 post) from a holiday reference week. Dec 2023 (k=−13) and Dec 2024 (k=−1) are the lowest pre-bins, so the CBD–donut FHV gap is seasonal as well as trending.
  - Lyft, whose pre-bins sit near 0, still rejects (p 2.6e−13 / 3.6e−11).
  - The stop is the correct consequence of the pre-registered rule. Amendment 3's expectation (Uber −3% to −6%) is untestable with this design.
- **HVFHV streaming.**
  - Row accounting closes in every month: kept + invalid zone + null platform = file rows; zone_hour = pair_week = kept.
  - No yellow-style quality filters (duration, distance, fare), no pickup-window filter and no de-duplication are applied. For pickup counts this is defensible, but the choice and its rejected alternative are not in DECISIONS.
  - Out-of-month pickups are kept and assigned by `pu_hour`, so they land in the correct week across files. Fine.
- **D0.** Gate numbers trace.
  - Under the 4a definition, P(Flex | any) = 1.000: `request_source` is only populated on Flex rows, so the 2026 agreement is nearly definitional.
  - It cannot validate Flex = app before 2026-06. This is already accepted by Stanley (4a); state it in the limitations.
- **D2.**
  - Clustered SEs computed from the score elements are correct, and the DoubleML default SE is kept beside them.
  - θ > 1 and the disagreement between estimators are reported honestly.
  - `plpr()` is not reproducible (unseeded folds; item 1).
  - Airports: 2 zones give CIs like [13.497, 13.497]. They are labelled "no conclusion", which is fine.
- **D3.** Q = 57 restrictions on G = 67 clusters gives Hotelling df2 = 10, so the "passing" levels pre-trend test has almost no power. DECISIONS says "weak", which is adequate. The post-hoc variants are labelled.
- **D5.** Reproduces the Phase-4 primary exactly. The gate is applied: both channels fail.
- **D5b.**
  - The event study on cell × week shows several significant pre-weeks (F6e right panel: −25, −23 to −21, −18, −17, −4), but **no joint pre-trend test is saved**. The Phase-4 standard is "each check a saved number".
  - The +3.0 pp DiD headline sits in the F6e title with no pre-trend number beside it.
  - The HVFHV trip-type DiDs (−6.7 log points etc.) also have no pre-trend test. DECISIONS calls them descriptive.

## Figures

- **F6_taxi_vs_fhv.**
  - Palette is correct: CBD = yellow, `comparison` = FHV, tint = pre. Policy line is labelled. The title states only the test result. Readable at 7 in.
  - **Defect:** the y-label "Effect on CBD pickups (%)" sits over a pre-period at +15–29%. These are differences relative to the control and the reference week, not effects. This was already flagged for F4 in `reviews/phase_4_round2.md`.
  - A legend is used where two direct labels would do (minor).
- **F6a.**
  - The policy line is drawn unlabelled in both panels. `style.py` requires the label on every time axis; the caption mentions the line, which is not the same.
  - Otherwise clear; independent y-axes are stated in the caption.
- **F6b.** Fine. The four small maps leave about 40% of the canvas empty (layout detail, optional).
- **F6c.** Fine. Note it plots PLPR 0.555, which contradicts DECISIONS (item 1).
- **F6d.** **Palette misuse:** Curb cabs are drawn in `PALETTE["cbd"]` red. The cabs are not CBD; the panels mix CBD and Manhattan non-CBD. Use `comparison` / `non_cbd`, or another semantic colour. No policy line is needed (x-range starts 2025-06).
- **F6e.** Palette consistent. Title discussed under D5b (no pre-trend number).

## Decisions check

Missing or inconsistent:
- HVFHV: why the yellow quality filters, the pickup-window filter and de-duplication are **not** applied (and what was rejected).
- Hard-coded dates and thresholds in code, without config entries (CLAUDE.md: "no hard-coded dates or thresholds in code"):
  - `scripts/16_fhv_did.py:76-77` (Lyft Jan-2025 split "2025-01-05", "2025-01-31", "2025-02-01");
  - `scripts/10b_cmt_block.py:73,79-80` ("2026-04-26", "2026-06-28", "2026-05-31");
  - `scripts/10c_channel_decomposition.py:39` (`MOTIVATION_MONTHS`);
  - `scripts/17_cross_platform.py:64,66` ("2026-06", "2026-08");
  - `scripts/15_app_share_step.py:128-133` (literal 4 weeks each side).
- C6: the weights are each FHV series' own pre-period volume. This is stated in the script and the F6 caption but not in DECISIONS l.257.
- D2: no line about the PLPR fold seed (there is none).

Present: disk guard 15 GB, distance edges, `channel_did.alpha`, `incr.*`, break rule 1,000 / 0.5, D3 windows, CMT block rule, label cut-over by file month.

## Fix list

1. `scripts/12_incrementality.py`: seed DoubleML's sample splitting in `plpr()`, and seed any other unseeded draw (e.g. `np.random.seed(cfg["seed"])` before `DoubleMLPLPR(...)`, or draw the folds explicitly). Re-run D2 and D4, then make DECISIONS l.255 quote the numbers in `results/incrementality_dml.json` (currently 0.555 [0.435, 0.675] and 0.582, not 0.522 / 0.489).
2. `DECISIONS.md` l.254: replace "63 zones / 63 clusters" with the 67 in `results/lyft_entry.json → n_zones`.
3. `scripts/17_cross_platform.py` and `scripts/10c_channel_decomposition.py`: add `n_weeks` and per-week means to `results/cross_platform_monthly.csv` and `results/channel_restatement.json`. In `DECISIONS.md` l.258, restate the CBD FHV change per week. In the D1 entry (l.253), add that the reproduced Amendment-4 monthly totals compare 5-week (2023-01) with 4-week months, and give the per-week CBD (+15.6%) and CBD street-hail (−16.7%) changes.
4. `DECISIONS.md` l.257: replace "every FHV pre-period month sits +15% to +28% higher …" with series- and weighting-specific ranges. Save them first: add a pre/post summary of the event-study coefficients per series to `results/fhv_did.json`, and cite it.
5. `scripts/11_hvfhv_stream.py` (or a small summary step): write platform and shared-flag totals (requested, matched, both, matched-without-request) to a `results/` file, e.g. `results/hvfhv_summary.json`. Correct DECISIONS l.256 to say "requested and matched 11,589,706".
6. `scripts/15_app_share_step.py`: compute and save the joint pre-trend test (pre-registered F and Hotelling F*) for each D5b event study in `results/app_share_policy_step.json`, and report it in DECISIONS l.260 beside the +3.0 pp DiD. Put the p-value in the F6e title or caption.
7. `DECISIONS.md` l.260: use one convention for log coefficients. Either "log points" or exp(b) − 1 in %.
8. `tests/`: add tests for the Phase-6 code:
   - (a) `11_hvfhv_stream.aggregate` on a tiny synthetic Parquet: trip type within/into/out_of/neither, distance bins at the edges, row accounting and `verified`;
   - (b) the C6 gate: a series with a planted pre-trend gets no `estimate`, a parallel one does;
   - (c) `dml_plr` recovers a known β on a synthetic panel, and the clustered SE comes out larger than the iid SE when errors are correlated within a cluster;
   - (d) `time_blocks` returns contiguous, disjoint, exhaustive blocks.
9. `config/project.yaml` + the scripts listed under Decisions check: move every hard-coded date and window into config. Add DECISIONS lines for the HVFHV no-quality-filter rule and for the C6 own-series weights.
10. `Makefile`: add `hvfhv channel fhv` to `all` (with `hvfhv` documented as a long re-stream), so `make all` rebuilds every Phase-6 table.
11. `src/taxi_shock/viz/figures.py`:
    - F6: change the y-label to "CBD vs control, relative to the week before 2025-01-05 (%)" (or equivalent).
    - F6a: label the policy line (`policy_line(ax)` with its label in at least one panel).
    - F6d: replace the `cbd` red for Curb cabs with a non-CBD semantic colour.

## Escalation reasons

None. Results that contradict the expectations will go to Checkpoint 6. Each was handled by a pre-registered rule and is reported as found:
- C6: every series fails pre-trends;
- D2: the CBD expectation is not met, the estimators disagree, and the Manhattan non-CBD lead placebo fails;
- D3: not identified;
- D5: gate closed.

For Checkpoint 6, Stanley should also see Fix 3: Amendment 4's motivating CBD decline is a 5-vs-4-week artefact (per week, CBD yellow pickups rose 15.6% from 2023-01 to 2026-01). Changing the storyline is outside reviewer bounds.

## Amendments made

None.
