# Checkpoint 7 — advisor review of the Phase 7 draft

Reviewed at commit `ad80ee6`: `reports/analysis.md`, `README.md`, `reports/dashboard_spec.md`, all 23 figures in `reports/figures/`, checked against `results/` and `DECISIONS.md`. Code and tests were out of scope.

**Result of the number check.** About 70 numbers in the report and README were traced to their result files. No wrong number was found. Six consistency problems were found (A3, A4, A5, A7, A11, A12).

**Rules for applying this file.**
- Rule 1 of `CLAUDE.md` stays in force. Every number marked *(advisor cross-check)* below was computed by the advisor from the named file only to show the size of the finding. Recompute it, save it to a file under `results/`, and quote your value, not mine.
- No causal wording (Amendment 5 stays in force). Every item below is descriptive or presentational.
- Order: section A, then B, then C if time allows. Commit and push after each lettered item group.
- Then: `make figures`, `make report`, `make verify PHASE=7`, the `phase-reviewer`, and the usual summary to Stanley.
- Do not rename the repository, make it public, or purge git history yet. Do not start E3 before the Snowflake environment variables exist.

---

## A. Must fix

**A1. Lead with the citywide result.** The executive summary, the README summary and the hero figure start with the CBD share (2.3% → 29.6%). The strongest and simplest fact is citywide and is already in `results/channel_decomposition.csv` (rows `2023_to_2025, all`): mean weekly yellow pickups grew by about 27% from 2023 to 2025 (contracted programme excluded), app trips account for all of the growth, and street hails are about 1% lower. Make this the first sentence of the executive summary and of the README, in this form: "From 2023 to 2025, NYC yellow-taxi pickups grew X% (A → B a week). App-dispatched trips account for all of that growth (+C a week); street hails changed by D (E%)." The CBD figures follow as the second sentence.

**A2. Explain the January 2025 step where the reader first sees it.** In F6a the app series doubles exactly at the congestion-pricing line. A reader concludes that the fee caused it; a careful reader asks whether it is a recording change. The report answers this only late and only in part. Add a short paragraph to §2 ("The app share rose in steps") with:
- the step dates and sizes from `channel_label_validation.json → flex_share_steps`;
- from `channel_weekly.csv`, for the weeks of 2025-01-05 and 2025-01-19, app and street-hail pickups by area. *(advisor cross-check: Manhattan outside the CBD, app 22,160 → 45,729, street hails 207,590 → 207,913; outer boroughs, app 9,572 → 26,123, street hails 4,785 → 4,654.)* The point to state: at the largest step app pickups about doubled within two weeks in every area while street hails did not fall, so the step adds recorded trips and does not relabel street hails;
- the step is the same size for trips that never touch the congestion zone (the existing D5b result), so the fee differential is not the cause;
- the cause is not known from public sources. Say so in one plain sentence.
Annotate the step in F6a (see B4).

**A3. The alarm statements in §5 contradict each other.**
- "The single CBD CUSUM alarm (2025-01-19)": `drift_detection.json` lists three CBD alarms in the monitoring period (2025-01-19 up, 2026-01-26 down, 2026-02-23 down). Write "the first alarm" or "the only alarm in the first twelve months", and report the two 2026 alarms.
- Check the two 2026 downward alarms and the 2026-Q1 error rise (WAPE 0.187–0.191 for every strategy) against the weather table: daily snowfall or precipitation and daily actual-versus-forecast for the days around 2026-01-26 and 2026-02-23. Save what you find to a results file. If the data show a weather event on those days, say so with the numbers; that turns an unexplained error rise into "the monitor flagged two storms within a day". If they do not, write "cause not determined". Annotate F5 and F3 accordingly.
- Three-shock table: the column "First CBD alarm" reads as a detection delay. Day 162 (2023-05-30) and day 354 (2025-12-25, Christmas Day) are not detections of the fare increase or of congestion pricing. Rename the column "First CBD alarm after the event" and state the finding directly: COVID-19 was flagged on day 13; the fare increase and congestion pricing produced no alarm for five and eleven months, and the later alarms fall on the dates given. Change the F3b title in the same way.
- The table gives +7.3% for congestion pricing and the paragraph above it gives +6.3% for the same four weeks. Add one sentence: the comparison uses a model trained on the 12 months before each event, the main monitor uses the model trained on 2022–2024.

**A4. One headline number for the DiD artefact.** The same result appears as −0.43 (README table header, log points), −35% / −34.6% (report §4, static estimate) and −40.5% (F4d title and §4 item 2, mean of the monthly event-study coefficients). The volume-weighted estimate appears as −5.2% (static) and −11.3% (F4d). Use the static estimates in percent as the headline everywhere: −34.6% ("−35%") and −5.2%. README header: "The −35% artefact". Where the event-study means remain (F4d, §4 item 2), label them "mean of the monthly event-study coefficients".

**A5. Incrementality sentence: say where the lead placebo fails.** In `incrementality_dml.json` the lead placebo passes in the CBD (p = 0.60) and fails in Manhattan outside the CBD (p = 9.8e−5). The sentence "…in the CBD … one lead placebo fails" lets the reader place the failure in the CBD. Replace "and one lead placebo fails" with "and the lead placebo fails in Manhattan outside the CBD" in the report, the F6c caption if it carries it, and View 3 of `dashboard_spec.md`. Amendment 6 authorises this change to Amendment 5's sentence.

**A6. Remove internal labels from everything a reader sees.** `reports/analysis.md` carries 20 lines with labels such as D2, D3, D5b, C3, C4, C6, B1, A1, "Amendment 4a", "Phase 4", "Checkpoint", S0/S1/S4/S6/S1e. Figure titles, legends and README captions carry them too ("(C4)", "(A1)", "Phase 4 primary", "(D1)", "(Phase 5)"). An outside reader cannot decode them.
- Replace with descriptive names: frozen model; monthly retrain; Chronos-2 zero-shot; monthly retrain with app-share features; monthly retrain on an expanding window.
- Labels may stay in the appendix and in the Make-target table as cross-references.
- One name per thing, everywhere, figures included:
  - **app dispatch** — define once: an e-hail app (Uber, Lyft, Curb, Arro) sends a yellow cab to the rider; identified by the Flex Fare flag before June 2026 and by `request_source` from June 2026;
  - **street hail**;
  - **congestion zone (CBD)**;
  - **outer boroughs** (not "other zones", "other", "non-CBD" when the outer boroughs are meant);
  - **contracted trip programme** (not "CMT block" alone).
- WAPE as a percentage with one decimal in text, tables and figures (F2 shows 0.1645, F5 shows 16.2%, the report tables show 0.164).

**A7. F2 title leads with the wrong variant.** The title reports Chronos-2 with weather over the target day (0.1645). The report's headline is the variant with past weather only (0.1652), which is the one that uses information available at forecast time. Lead the title with that variant; mention the other as a sensitivity.

**A8. Third reference.** Replace the HTML-comment placeholder with:
- Pandey, A., Guler, I., & Gayah, V. (2026). *The Effect of the New York City Congestion Toll on Trips Served by Transportation Network Companies.* Findings. https://doi.org/10.32866/001c.155761. High-volume FHV trips, first 14 weeks of 2024 and 2025, difference-in-differences of log(1 + trips), CBD zones against Manhattan zones outside it.
Add a fourth, because it uses the approach of F4d:
- Li, D., Zhuang, D., Li, Y., Shen, C., Cao, N., Zheng, Y., Wang, S., & Zhao, J. (2026). *Public transit gains and spatially uneven travel demand changes after NYC congestion pricing.* arXiv:2606.17530. Counterfactual demand forecasts from time-series foundation models.
Open both links and confirm title and authors before committing. In "What overlaps and what is new", add two neutral sentences: the CBD-versus-Manhattan design is standard in this literature; with 24 pre-policy months the same design fails its pre-trend test here for yellow taxis and for high-volume FHV. Do not say or imply that any cited study is wrong.

**A9. Remove the "Correction" block from §2.** It reports an internal error of the planning stage to the reader. It stays in `DECISIONS.md` and in `reviews/phase_6_round1.md`. Replace it with one sentence of method: "All comparisons use mean weekly pickups, because calendar months hold four or five panel weeks."

**A10. Text that is not written for the public.**
- README line 3: "Status: Phase 7 draft (Checkpoint 7), not yet reviewed." Remove at the end of Phase 7.
- `dashboard_spec.md` line 3 ("Stanley builds this dashboard … The Builder supplies … No mock-ups or screenshots are produced."): rewrite as a neutral description of the dashboard and its data.

**A11. Supply paragraph.**
- "8,722.5" active cabs: a mean of monthly values, printed with a decimal. Round (for example to the nearest ten) in the report, README and summary.
- "Stayed at 14.85 → 15.02" / "constant intensity": the file's yearly values are 14.85 (2023), 14.02 (2024), 15.02 (2025) and 14.00 (January–July 2026). Write that trips per cab-day stayed between 14.0 and 15.0 in 2023–2026, and give the year-on-year comparison that carries the finding: trips per day and active cabs per day both rose by about a quarter from 2023 to 2025 (quote both percentages from the file).

**A12. Growth-accounting table, outer-borough row.** The first column shows a change for the CBD and Manhattan rows and levels ("8,277 → 51,803") for the outer boroughs. Use one format: the change, with the levels in brackets, and say "about six-fold" if the file supports it.

---

## B. Should fix (structure and strength of the findings)

**B1. Split the report into a main text and an appendix.** This answers Checkpoint 7 question 1. Keep all content; the main text should be readable in about ten minutes (aim for 1,800 words or fewer); the rest moves to `reports/appendix.md`, linked from each section.
Main text order:
1. Summary: three findings, what was tested and could not be identified, one recommendation. Sentences of 30 words or fewer (the present first sentence has about 75).
2. Data and definitions (short; include the scale line of B3b).
3. The shift: citywide headline; by area; the steps (A2); the contracted programme that ended; where it happened (map, r); supply; the ride market in the CBD (B3g).
4. A methods case: how a textbook DiD produced a −35% effect that was not there. Move it up: it is the most distinctive part of the project.
5. What the data could not identify: one table (B2).
6. Forecasting through the shift (B3c–e): accuracy and robustness first, one small table, the recommendation.
7. How to measure it properly: the switchback design.
8. Limitations; next steps; references.
To the appendix: the Phase-5 table notes and the expanding-window sensitivity; estimator details of the incrementality analysis; speed, FHV and synthetic-control details; the by-channel DiD; the three-shock details; the pre-trend test-size simulation.

**B2. Replace the bullet list of §3 with one table.** Columns: question; design; estimate; result of the pre-registered check. One row per design. Open the section with two sentences: every design had an expected direction and a pass/fail check fixed before it was run ("gate": define the word once); count from the files how many stopped at the check and say so. This shows the discipline in ten seconds and stops the section reading as a list of failures.

**B3. Findings that are in `results/` but weak or missing in the text.** Each is descriptive. Save any derived number to a results file first.
- a. The citywide headline (A1).
- b. Scale: 341,589,889 yellow records plus 904,683,847 high-volume FHV trips, processed with DuckDB and dbt on a 12 GB laptop. State the total ("over 1.2 billion trip records") in the data section and the README.
- c. Forecast accuracy as an improvement over the benchmark: `forecast_summary.json → wape_relative_to_seasonal_naive_expanding` gives 0.685 and 0.695 for 2024, that is about 31% lower error than the seasonal naive; the 2025–2026 table gives 16.2–16.4% against 23.7%. "Both beat the seasonal naive" undersells it.
- d. Robustness: the model frozen in December 2024 lost 0.23 percentage points of WAPE to monthly retraining over 20 months, while the app share of CBD pickups rose from about 18% to about 30%. Present the 0.23 pp as "the forecaster stayed accurate through the shift, and monthly retraining recovers a small, measurable gain", not as the headline result.
- e. Where the frozen model fails: `adaptation_summary.json → bias_pct_of_pickups` by area. *(advisor cross-check: frozen model −10.8% in the outer boroughs against −2.0% in the CBD; monthly retrain −7.0% in the outer boroughs; retrain with app-share features −6.0% there.)* The under-forecast sits where app growth is largest. Report it, and add the nuance it brings to the app-share-features result: worst overall, smallest under-forecast in the outer boroughs. Report as found.
- f. The correlation: `app_dispatch_summary.json` gives r = 0.92 for 63 Manhattan zones and r = 0.90 (Spearman 0.85) for all 200 zones. Give both.
- g. The ride market in the CBD, from `cross_platform_monthly.csv`, as yearly means of weekly pickups for 2023 and 2025: yellow pickups, Uber + Lyft FHV pickups, their total, and yellow's share of the total. *(advisor cross-check: yellow 418,560 → 517,623 a week; FHV 1,234,000 → 1,164,607; total +1.8%; yellow share 25.3% → 30.8%.)* Add the platform view already recorded in `DECISIONS.md` (D4): the share of Uber's CBD trips served by yellow cabs (2026-06 and 2026-09) and Lyft's (2026-09). Wording stays descriptive: "the total was about flat and yellow's share rose"; no statement that trips were taken from FHV.
- h. §4, "How it was caught": add the fake-date result from `placebo.json → placebo_in_time`: the same specification gives about −14% at a fake policy date of 2024-01-07, a year before the policy.

**B4. Figures.**
- *Hero figure (new).* Citywide weekly yellow pickups, app and street hail stacked, 2023-01 → 2026-09, contracted programme excluded. Title = the A1 sentence. Annotations: Uber auto-dispatch begins (2023-08); the January 2025 step; the congestion-pricing line with a small label. Full width at the top of the README and of the report.
- *README figure block.* Five thumbnails in one row are about 170 px wide and unreadable. Use the hero figure at full width, then a 2 × 2 grid: where it happened (F4g); the −35% artefact (F4d); incrementality not identified (F6c); forecasting (F5 or F2b). Captions in plain words, no labels.
- *F6a.* Annotate the January 2025 step ("app pickups doubled within two weeks in every area, also for trips that never touch the zone") so the dashed policy line is not read as the cause. Make "own y-axis per panel" visible in the panel titles.
- *F6b.* The title gives the median zone share (91% in 2025); the report's headline is 29.6% for the CBD. State both in the title: outside Manhattan's core the median zone is mostly app-dispatched by 2025; in the CBD the share is the smaller number. Remove the empty space above and below the maps and enlarge them; the hatched Staten Island area dominates the picture.
- *F4g.* The y-axis is in log points (2.5 is about twelve-fold). Label the ticks as multiples (×1, ×2, ×4, ×8, ×12). Put the plain statement first in the title: zones where Uber and Lyft dispatch is common are the zones where yellow pickups grew most.
- *F4d.* Series labels: "Forecast counterfactual (frozen model)"; "DiD, equal zone weights (as pre-registered)"; "DiD, zones weighted by volume". Remove "(primary)". Numbers per A4.
- *F5.* The four lines overlap, so the title's message (a 0.2-point gap) cannot be seen, and the end labels collide. Add a panel with the WAPE gap to the frozen model and its bootstrap interval by area (`adaptation_gaps.csv`), as dots with whiskers. Let the title state what the line panels show (all strategies err together) and the gap panel carry the comparison. Annotate 2026-Q1 per A3.
- *F3.* Draw the two 2026 alarms or change the title to "the first alarm". *F3b:* title per A3.
- *F4b.* The picture shows the reason the control group fails: uptown zones grew strongly while the CBD was flat. The title reports a median of −5.6% instead. Retitle to the visible message, with numbers from `effect_map.csv`.
- *All figures.* "Other zones" → "Outer boroughs" (F2). Raw labels "pre volume weighted" / "equal weight" (F4i) → "zones weighted by volume" / "equal zone weights". WAPE in percent.

**B5. README as the front page.** Order:
1. Title and one paragraph with the A1 finding.
2. Hero figure.
3. Key results: five bullets, each with its number and its results file.
4. What was tested and could not be identified: three lines and a link to the report.
5. Methods and stack, one line each: SQL (dbt on DuckDB, window functions), Python 3.12, LightGBM quantile regression, Chronos-2, conformal prediction, difference-in-differences and event studies (pyfixest), synthetic control (pysyncon), double machine learning (DoubleML), CUSUM monitoring, pytest, ruff, GitHub Actions, Tableau. Add Snowflake only after E3 has run.
6. How the work was controlled: expected directions and pass/fail checks written before each analysis; an independent review of every phase (`reviews/`); every judgement call logged (`DECISIONS.md`); tests. Quote the counts from the repository.
7. Dashboard link (when Stanley supplies it).
8. Reproduce: setup, Make targets, hardware and runtimes, the Chronos-2 steps.
9. Limitations; data and licences. Keep the sentence on 2024 volume at 48% of 2019 and the 2022 model start (Checkpoint 1 item 5), under data.
Also: GitHub does not render `F4b_effect_map.html`; remove that sentence or point to the dashboard once it is published.
- **"How this project was built" section: do not write it.** Leave a clearly marked placeholder. Stanley supplies the wording (it states how AI tools were used and what he decided).

**B6. Language.**
- First person singular throughout ("how we know" → "how I know").
- Define on first use, in a few words: WAPE, difference-in-differences, pre-trend test, placebo, double machine learning, conformal calibration, CUSUM, switchback, FHV, CBD, "gate".
- Summary sentences of 30 words or fewer.

---

## C. Optional

- App-share maps in a teal sequential scale, so one colour family means "app" in every figure.
- F1c: larger fonts, or move to the appendix only.
- §2 supply: mention the 2022 value of trips per cab-day from the same file, if it helps to show that intensity fell as cabs returned and then stayed flat.
- External check for the 2024 app share: the TLC Commissioner told the City Council on 2025-02-10 that e-hail trips were 5–10% of taxi trips depending on the month (https://citymeetings.nyc/city-council/2025-02-10-1000-am-committee-on-transportation-and-infrastructure/chapter/update-on-the-e-hail-program-for-yellow-and-green-taxis). Compare with the citywide 2024 monthly app share in `channel_monthly.csv`; cite it only if the two agree, and say plainly if they do not.
- `dashboard_spec.md`: a first view with three number tiles carrying the A1 headline, each copied from its results file.

---

## D. Answers to the five Checkpoint 7 questions

1. **Report length.** Keep the content; main text plus appendix as in B1.
2. **CI `startup_failure`.** Every run fails in 0 s before any step starts, on a private repository. That is an account-level condition (Actions disabled or no included minutes), not a workflow error. Leave `ci.yml` as it is. Stanley checks the account settings; otherwise the workflow is confirmed after the repository becomes public. Add the status badge to the README only after the first green run.
3. **Third reference.** See A8.
4. **Stanley's own items** (dashboard URL, Snowflake account, `notebooks/colab_chronos.ipynb`, optional Colab profiling, repository name, licence, visibility, "How this project was built" wording): leave placeholders; do not block on them.
5. **Space on C:.** Nothing to do now. The WSL disk compaction stays optional and is done by Stanley after the final review, because it needs a WSL shutdown.
