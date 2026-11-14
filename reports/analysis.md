# Where the Growth Came From: App Dispatch and NYC Yellow Cabs, 2023–2026

*Yellow-taxi trip records of the NYC Taxi & Limousine Commission (TLC), 2023-01 → 2026-09, at the TLC-zone level. Every number below links to the file under `results/` it is read from; every judgement call is in [`DECISIONS.md`](../DECISIONS.md).*

## Executive summary

1. **The shift.** From 2023 to 2025, NYC yellow-taxi pickups grew 27.3% (703,268 → 895,177 a week). App-dispatched trips account for all of that growth (+199,068 a week); street hails changed by −7,159 (−1.1%) ([channel_decomposition.csv](../results/channel_decomposition.csv), [presentation_numbers.json](../results/presentation_numbers.json)). In the congestion zone (CBD), app dispatch rose from 2.3% to 29.6% of yellow pickups between January 2023 and January 2026 ([channel_restatement.json](../results/channel_restatement.json)).
2. **The supply fact.** The growth came with more cabs on the road, not more trips per cab. From 2023 to 2025, trips per day rose 25.6% and active cabs per day 24.0% (about 7,040 → 8,720), while trips per cab-day stayed between 14.0 and 15.0 in 2023–2026 (TLC monthly reports; [incrementality_dml.json → supply](../results/incrementality_dml.json), [presentation_numbers.json](../results/presentation_numbers.json)).
3. **What is not identified.** How much of the app growth is additional rather than displaced street hails, and what congestion pricing did to taxi demand, cannot be identified from the trip records: every pre-registered design either failed its pre-trend test or disagreed with the others beyond their intervals, and each is reported as found at its gate.
4. **Forecasting.** From February 2025 to September 2026, refitting the forecaster monthly gave the lowest error (WAPE 0.162 against 0.164 for the frozen model, a small gap the paired bootstrap distinguishes), and adding app-share features made the under-forecast larger, not smaller (−2.9% of pickups against −2.3% frozen; [adaptation_summary.json](../results/adaptation_summary.json), [adaptation_gaps.csv](../results/adaptation_gaps.csv)).

**Recommendation.** Evaluations and forecasts of NYC taxi demand in 2023–2026 must model the dispatch channel. A model or a difference-in-differences that treats yellow pickups as one homogeneous series reads a change in how trips are dispatched as a change in demand.

---

## 1. Question and data

**Questions.**
- When ride-hail apps began dispatching NYC yellow cabs, did the taxi business grow, or did trips move between channels?
- What could the trip records say about Manhattan congestion pricing, which charges taxis $0.75 and high-volume for-hire vehicles (FHV) $1.50 per trip touching the zone from 2025-01-05?
- How should a demand forecaster behave through such a shift?

**Data.**
- 341,589,889 raw yellow-taxi records, 2019-01 → 2026-09. After de-duplication and the validity rules, 331,436,471 remain (2.97% removed; [data_quality.json](../results/data_quality.json)).
- Aggregation is in DuckDB and dbt. The panels and every heterogeneity cut are SQL models, not pandas.
- Forecasting covers 103 zones, which carry 99.04% of 2024 pickups ([modeled_zones.json](../results/modeled_zones.json)).
- **App channel** (Amendment 4a): any e-hail app. The label is Flex Fare (upfront app price) before 2026-06 and the `request_source` field from 2026-06. On June–September 2026 the two labels agree on 99.97–100% of trips ([channel_label_validation.json](../results/channel_label_validation.json)).
  - Uber and Lyft make up 87.8% of app trips there.
  - Codes EH0004 and EH0010 are Curb's and Arro's own apps (TLC e-hail licence list).
  - Codes A and CC are undetermined.
- **High-volume FHV records** (Uber, Lyft): 45 months, 904,683,847 trips, aggregated month by month and the raw files deleted ([hvfhv_summary.json](../results/hvfhv_summary.json), [hvfhv_stream_log.csv](../results/hvfhv_stream_log.csv)).

## 2. The shift: where the growth came from

**Share of CBD pickups.** App dispatch rose from 2.3% (2023-01) to 10.3% (2024-04), 17.8% (2025-01) and 29.6% (2026-01) ([channel_restatement.json](../results/channel_restatement.json)). Per week, CBD yellow pickups rose 15.6% between those Januaries (392,751 → 453,882), and CBD street hails fell 16.7% (383,608 → 319,640).

All comparisons use mean weekly pickups, because calendar months hold four or five panel weeks.

**The app share rose in steps.** Across all zones, the 4-week app share jumped by 5.6 points at the week of 2024-02-25, 5.4 at 2024-09-01, 10.9 at 2025-01-19 and 7.2 at 2025-05-04; it fell by 5.9 points at 2026-03-01 ([channel_label_validation.json → flex_share_steps](../results/channel_label_validation.json)). The largest step comes two weeks after congestion pricing began, so it needs a closer look ([presentation_numbers.json → january_2025_step](../results/presentation_numbers.json)):

| Area, weeks of 2025-01-05 → 2025-01-19 | App pickups | Street hails |
|---|---|---|
| CBD | 45,477 → 110,403 | 353,851 → 381,403 |
| Manhattan outside the CBD | 22,160 → 45,729 | 207,590 → 207,913 |
| Outer boroughs | 9,572 → 26,123 | 4,785 → 4,654 |

- Within two weeks, app pickups about doubled or more in every area, while street hails did not fall. The step adds recorded trips; it does not relabel street hails.
- The step is the same size for trips that never touch the congestion zone (+10.6 points) as for trips that do (+8.1 to +11.3; [app_share_policy_step.json](../results/app_share_policy_step.json); F6e). The fee difference between taxis and ride-hail cars does not explain it.
- What caused the step is not known from public sources.

**Growth accounting, 2023 → 2025, mean weekly pickups** ([channel_decomposition.csv](../results/channel_decomposition.csv)):

| Area | Change in total | From app trips | From street hails |
|---|---|---|---|
| All zones (contracted programme excluded) | +191,909 (703,268 → 895,177) | +199,068 | −7,159 |
| CBD | +99,063 (418,560 → 517,623) | +104,958 | −5,896 |
| Manhattan outside the CBD | +50,537 (215,677 → 266,214) | +51,230 | −692 |
| Outer boroughs (contracted programme excluded) | +43,526 (8,277 → 51,803, about six-fold) | +42,811 | +715 |

Over January–September 2026 against the same weeks of 2023:
- CBD street hails are 12.0% lower (−48,303 a week);
- CBD app trips are 113,506 a week higher.

The **accounting net ratio** is the net change in pickups per app pickup added. It is arithmetic on observed changes, **not** an incrementality estimate. It is 0.944 in the CBD for 2023 → 2025 and 0.574 for Jan–Sep 2023 → 2026.

**A contracted trip programme that ended.** One block of outer-borough "street hails" is in fact a centrally paid trip programme on cabs with CMT meters ([cmt_block_diagnosis.json](../results/cmt_block_diagnosis.json)):
- 93% carry a non-standard rate code (99);
- 99% have a single rider;
- 3% are tipped;
- the median trip is 43 minutes in daytime from central and east Brooklyn.

It ended at the end of May 2026, and no other vendor picked it up. It is reported as its own series. Without it, outer-borough app share went from 13.3% to 89.4% (2023-01 → 2026-01).

**Where app dispatch is common, yellow pickups grew most.**
- Across Manhattan zones, 2023 → 2025 growth correlates with the June–September 2026 Uber/Lyft share at r = 0.92 ([app_dispatch_summary.json](../results/app_dispatch_summary.json)). This is a correlation, not an effect.
- Yellow app trips grew from 0.75% to 10.86% of all app-dispatched CBD trips, yellow plus Uber/Lyft FHV (January 2023 → January 2026; [cross_platform_monthly.csv](../results/cross_platform_monthly.csv)).

**Supply** ([supply_monthly.csv](../results/supply_monthly.csv), [presentation_numbers.json → supply](../results/presentation_numbers.json)). The TLC's monthly reports show the yellow fleet supplying more cab-days at a steady intensity:
- from 2023 to 2025, trips per day rose 25.6% (104,422 → 131,133) and active cabs per day 24.0% (about 7,040 → 8,720);
- trips per cab-day stayed between 14.0 and 15.0 in 2023–2026 (14.85, 14.02, 15.02, and 14.00 for January–July 2026).

The trip records alone cannot say whether app dispatch brought the extra cabs back or the returning cabs took app trips.

## 3. What the trip records cannot identify, and how we know

Every causal design below was pre-registered with an expected direction and a gate before it was run. It was stopped where the gate failed and is reported as found.

**Incrementality of app trips (D2).** Estimates of the share of app trips that are additional range from 0.52 to 2.62 across estimators in the CBD. The primary DML gives 0.90 [0.74, 1.06]. The estimators disagree beyond their intervals, and the lead placebo fails in Manhattan outside the CBD, so incrementality is not identified from these data ([incrementality_dml.json](../results/incrementality_dml.json); F6c).
- The primary estimator is double machine learning with LightGBM nuisances, time-blocked cross-fitting and zone-clustered errors.
- Values above 1 in several estimators mean street hails and app trips rise and fall together within a zone-week: shared local demand shocks, not displacement.
- The DoubleML panel estimator is the median of 25 fold draws (0.52, range 0.49–0.56).

**Lyft's entry on Curb cabs (D3; preliminary, not identified).** Lyft trips appear only on Curb-equipped cabs, from 2026-08-10 ([request_source_daily.csv](../results/request_source_daily.csv)). The pre-registered vendor-level DiD in levels gives an implausible −1.12 Lyft-trip incrementality. Curb cabs carry 4.3 times CMT's volume, so common percentage swings appear as level changes. The log specification gives 0.68 [0.09, 1.23], but fails its pre-trend test ([lyft_entry.json](../results/lyft_entry.json); F6d). `make lyft-refresh` re-estimates once TLC publishes later months.

**Congestion pricing.**
- **Yellow demand (Phase 4).** The volume-weighted DiD of CBD vs Manhattan "donut" zones gives −5.2% [−12.8%, +3.0%] ([did_static.json](../results/did_static.json)).
  - The pre-trend test rejects (Hotelling F* p = 1.6e−17; [placebo.json](../results/placebo.json)).
  - With the full Manhattan non-CBD control the estimate moves to −1.0%.
  - The estimate lies outside all 500 random-zone and all 54 fake-date placebos ([power_mde.json](../results/power_mde.json)), as the diverging app-dispatch trend would produce.
  - The DiD cannot identify the policy's effect on yellow-taxi demand.
- **Synthetic control (C3).** CBD pickups are −1.2% against the synthetic CBD, rank 11 of 16 (p = 0.69). The method produces +4.6% at a fake 2024 date, so it cannot resolve the question ([synth_control.json](../results/synth_control.json)).
- **High-volume FHV (C6).** Every Uber, Lyft and shared-ride series fails the pre-trend test (Uber + Lyft weighted p = 2.3e−18), so no effect is estimated ([fhv_did.json](../results/fhv_did.json); F6).
- **Trip speed (B1, C4).** Within-CBD speed is +1.9% against the donut control and −4.0% against Brooklyn/Queens. Both designs fail their pre-trend tests ([speed_did.json](../results/speed_did.json), [speed_did_outer.json](../results/speed_did_outer.json); F4f).
- **Did the fee move trips into apps? (D5, D5b).** By channel, both the street-hail and the app DiD fail the pre-trend gate ([did_by_channel.json](../results/did_by_channel.json)). The app share jumped about 11 points in the weeks after 2025-01-19, the same for trips touching the CBD (+8.1 to +11.3 points) as for trips touching neither end (+10.6). The size of the jump did not differ with exposure to the fee ([app_share_policy_step.json](../results/app_share_policy_step.json); F6e).

## 4. Methods note: how a textbook DiD produced a −35% effect that was not there, and how it was caught

**The result.** The pre-registered specification was a difference-in-differences of log(1 + weekly pickups) per zone, with zone and week fixed effects, 38 CBD zones against 25 Manhattan donut zones, and zone-clustered errors. It gave −0.425 log points, −34.6% [−47.7%, −18.3%], p = 0.0004 ([did_static.json → main](../results/did_static.json)). Leave-one-zone-out kept every estimate between −36.3% and −32.0%. It looked robust.

**The weighting.** Equal zone weights let small uptown control zones drive the control trend. Their yellow pickups grew several-fold from 2023 to 2025, and they are the zones where app dispatch is highest:
- the fastest-growing donut zones are 71–83% Uber/Lyft-dispatched;
- the CBD median is 27% ([app_dispatch_summary.json](../results/app_dispatch_summary.json); F4g).

A log difference against a fast-growing small-zone average reads their growth as a CBD decline. Weighting zones by their pre-period volume, which estimates the effect on the aggregate, shrinks the estimate to −5.2% with a CI that includes zero.

**How it was caught.**
1. The pre-trend test failed (p = 2.7e−10). A size simulation showed the pre-registered F test rejects 56% of the time at 5% in this design, whereas the Hotelling-corrected test has about the right size, 9.5% ([pretrend_test_size.json](../results/pretrend_test_size.json)). The real p-values are far below either, so the failure is real.
2. The frozen forecaster, which knows nothing about control zones, put CBD pickups at +2.0% against its forecast after the policy, while the mean of the monthly event-study coefficients of the pre-registered specification was −40.5% (F4d; [figure_stats_phase4.json](../results/figure_stats_phase4.json)).
3. The control group's growth was traced to the dispatch channel (C1).

**The lesson.** A DiD on counts needs its weighting and its control group's composition examined before its p-value is.

## 5. Forecasting through the shift

**Baseline (Phase 2).**
- On 2024 day-ahead forecasts over the 103 modeled zones, WAPE was 0.1652 for Chronos-2 zero-shot (weather as past covariate) and 0.1675 for a tuned global LightGBM. The two are not distinguishable by a paired block bootstrap ([forecast_summary.json](../results/forecast_summary.json), [wape_gap_bootstrap.csv](../results/wape_gap_bootstrap.csv)).
- Both beat the seasonal naive, at 0.2411.
- Rolling 12-week conformal calibration brings 80%-interval coverage to 0.82 (LightGBM) and 0.79 (Chronos-2).

**The policy date (Phase 3).** A LightGBM frozen at 2024-12-31 showed no CBD-specific break.
- In the first four weeks, actual pickups ran 6.3% above forecast in the CBD and 5.3% above outside it ([figure_stats_phase3.json](../results/figure_stats_phase3.json)).
- CBD rolling WAPE did not rise.
- The first CBD CUSUM alarm (2025-01-19), the only one in the first twelve months, is the kind the 2024 calibration year also produced (one alarm, 2024-09-10, up; the CUSUM threshold allows one a year) ([drift_detection.json](../results/drift_detection.json); F3).
- Two further CBD alarms, both downward, came on 2026-01-26 and 2026-02-23. Both follow snowstorms: 7.5 inches of snow fell on 2026-01-25 and 5.5 inches on 2026-02-23 (3.6 the day before). On those days CBD pickups ran 50.6% and 72.7% below the frozen forecast ([presentation_numbers.json → alarm_weather_check](../results/presentation_numbers.json), [alarm_weather_check.csv](../results/alarm_weather_check.csv)). The monitor flagged two storms within a day.

**Three shocks, one monitor (C5)**, each with a 12-month frozen model ([shock_comparison.json](../results/shock_comparison.json); F3b):

| Shock | CBD vs forecast, first 28 days | First CBD alarm after the event |
|---|---|---|
| COVID-19 | −56.0% | day 13 |
| Metered-fare increase (Dec 2022) | +9.7% | day 162 (2023-05-30) |
| Congestion pricing | +7.3% | day 354 (2025-12-25) |

COVID-19 was flagged on day 13. The fare increase and congestion pricing produced no alarm for five and eleven months; the later alarms fall on the dates given and are not detections of either event. The +7.3% differs from the +6.3% above because this comparison uses a model trained on the 12 months before each event, while the main monitor uses the model trained on 2022–2024.

**Adaptation (Phase 5).**
Four strategies were compared on day-ahead forecasts with origins 2025-02-01 → 2026-09-30, scored with the Phase-2 metrics and a common MASE scale ([adaptation.csv](../results/adaptation.csv), [adaptation_summary.json](../results/adaptation_summary.json), [adaptation_gaps.csv](../results/adaptation_gaps.csv); F5). Two further rows are not strategies: a sensitivity (S1e) and the frozen seasonal naive as the naive reference.

| Strategy | WAPE, all zones | WAPE, CBD | Bias, % of pickups | 80% coverage (rolling conformal) |
|---|---|---|---|---|
| S0 frozen at 2024-12-31 | 0.164 | 0.154 | −2.3% | 0.81 |
| S1 monthly retrain, sliding 24 months | **0.162** | **0.151** | −1.7% | 0.80 |
| S4 Chronos-2 zero-shot | 0.165 | 0.154 | −2.0% | 0.80 |
| S6 S1 + trailing app-share features | 0.168 | 0.157 | −2.9% | 0.80 |
| *Sensitivity:* S1e monthly retrain, expanding window (as S0) | 0.162 | 0.152 | −1.8% | 0.81 |
| *Reference:* seasonal naive, frozen | 0.237 | 0.223 | −0.1% | 0.81 |

Table notes. Quarters are assigned by origin date, so the first quarter, 2025-Q1, covers only 2025-02-01 → 03-31; its rolling-conformal coverage is 0.80–0.82 for the four strategies. The intervals of every row, S0 included, are recalibrated by the rolling 12-week conformal: S0's point forecasts are frozen but its intervals adapt (raw S0 coverage 0.78, calibrated 0.81). Before 2025 the frozen model is in-sample, so S0's calibration residuals there come from the Phase-2 out-of-sample backtest, as in Phase 3. The seasonal naive has no forecast for 206 hours whose lag-168 h hour is the missing spring-forward hour; they are left out of its metrics. MASE over all zones is above 1 for every row (S0 1.40, seasonal naive 1.89) because the scale is the 2022–2024 in-sample seasonal-naive error and outer-borough volume has grown since; it does not mean the strategies lose to the naive forecast, which every strategy beats by about 7 pp of WAPE.

- **S1 vs S0, and why.** S1 is ahead by 0.23 pp of WAPE over all modeled zones and 0.29 pp in the CBD; both bootstrap intervals exclude zero. In Manhattan outside the CBD the two are not distinguishable. S1 changes two things at once, the refit frequency and the training window, so S1e (the same monthly refits on S0's expanding window) separates them. Retraining on S0's window gains 0.24 pp over S0 (interval excludes zero); switching that retraining to the sliding window changes WAPE by 0.01 pp (interval includes zero). The gain is from retraining, not from the window.
- **S4.** Chronos-2 is not distinguishable from S0 or S1 over all zones or in the CBD. It is the best of the four in the outer-borough zones (0.395 against 0.403 for S1 and 0.412 frozen) and at the airports (0.175 against 0.179 for S1, interval excludes zero), and distinguishably behind S0 and S1 in Manhattan outside the CBD (0.147 against 0.142).
- **S6 is a negative result.** The pre-registered expectation (Amendment 4, D6) was that channel-aware features would remove most of the post-2025 bias. They did not: S6 has the largest under-forecast and the highest WAPE of the four, distinguishably worse than S0 and S1. The features are trailing app shares, so they describe the channel mix after it has moved; they do not anticipate the level of demand.
- **Every strategy errs the same way at the same time.** All four rise together in 2026-Q1 (WAPE 18.7–19.1%, against 16.2–16.4% in 2025-Q1; [adaptation.csv](../results/adaptation.csv)); no strategy avoids it, so it is not an adaptation failure of one model. Part of the rise is the two snowstorms: the four days with at least 2 inches of snow carry 9–11% of the quarter's absolute error, and without them the quarter's WAPE is 17.0–17.6% ([presentation_numbers.json → alarm_weather_check](../results/presentation_numbers.json)). The cause of the remainder is not determined.
- **Intervals.** With rolling 12-week conformal calibration, every strategy covers 0.80–0.81 of hours with its 80% interval; raw intervals cover 0.74–0.78.

**Recommendation for the forecasting system.** Retrain monthly (S1). The LightGBM refit takes a median of 384 s on the 12-core local CPU, and a month of S1 (refit plus that month's daily forecasts) a median of 411 s (23 refits, [adaptation_summary.json → retrain_cost](../results/adaptation_summary.json)). The gain over the frozen model is small (0.23 pp of WAPE) but distinguishable over the whole window, though not in every quarter (S0 is ahead in 2025-Q1), and S1 also has the smallest bias of the four strategies. The sliding 24-month window is preferred to the expanding one because the two are equally accurate and the expanding refit takes about twice as long (median 720 s). Chronos-2 needs no retraining but a GPU at every origin (a median of 250 s per month of daily origins on an L4); it is not distinguishable from S1 over all zones and is ahead only in the outer boroughs and at the airports. Channel features should not be added in their current trailing form.

## 6. Why this could not be an A/B test, and how it would be designed

**Why not here.** Neither congestion pricing nor app dispatch was randomized.
- Geography cannot be randomized for a cordon toll.
- Cabs, drivers and riders move between zones, so treated and control areas interfere.
- The two channels share the same cabs.

The incrementality of app dispatch, however, could be measured with a designed experiment by a platform or the TLC ([experiment_design.json](../results/experiment_design.json)).

**Switchback design.**
- Dispatch eligibility is switched on or off at random per pickup zone and 2-hour block across the 67 CBD and Manhattan non-CBD zones.
- θ = (total pickups when on − when off) / app pickups when on.
- With the noise observed in March–May 2026 (residual sd 33.1 trips per zone-block, 30.3 app trips per block, lag-1 autocorrelation 0.58), θ to ±0.1 at 5% size and 80% power needs 3,756–5,922 zone-blocks, about 5–7 days.
- Clusters of neighbouring zones and wash-out periods handle interference and carry-over.

**Staggered vendor rollout** (switch cab groups on one at a time). The observational analogue (D3) would need about 3,466 post days for the same precision.

## 7. Limitations

- **Yellow taxis only for demand.** FHV enters only as aggregates (C6, D4).
- **Weather.** One city-wide point, using observed weather as if it had been known in advance.
- **Channel label.**
  - Before 2026-06, "app" rests on the Flex Fare flag.
  - Platform-specific results exist only from 2026-06.
  - Codes A and CC are undetermined.
  - Fee recording differs by vendor ([cbd_validation_trips.json](../results/cbd_validation_trips.json)).
- **Data gaps.** Two TLC source outages (2022-09-17/18 and 2023-09-21/24) are excluded from the monitors. The CMT contracted block ended in 2026-05.
- **Supply.** No driver or vehicle-level data. The supply view uses TLC monthly aggregates.
- **Causal claims.** All observational designs failed their gates. No sentence here states a causal effect of app dispatch or of congestion pricing.

## 8. What I would do next

- Run the switchback above with a platform partner.
- Re-estimate Lyft's entry with more post-launch months (`make lyft-refresh`).
- Obtain medallion-level supply data to test whether app dispatch brought cabs back.

## References

- Cook, C., et al. (2025, rev. 2026). *The Network-Wide Effects of Congestion Pricing: Evidence from New York City.* NBER Working Paper 33584. https://www.nber.org/papers/w33584. Road speeds from Google Maps data.
- Zhang, Y., Sang, Y., & Wu, M. *Congestion Pricing in New York City: Effects on Ride-Hailing, Transit, and Welfare.* SSRN 5549128; also listed as "Congestion pricing in New York city: Effects on ride-hailing and transit" on ScienceDirect (S0965856426001072). Uber and Lyft trips and subway ridership.
- Pandey, A., Guler, I., & Gayah, V. (2026). *The Effect of the New York City Congestion Toll on Trips Served by Transportation Network Companies.* Findings. https://doi.org/10.32866/001c.155761. High-volume FHV trips, first 14 weeks of 2024 and 2025, difference-in-differences of log(1 + trips), CBD zones against Manhattan zones outside it.
- Li, D., Zhuang, D., Li, Y., Shen, C., Cao, N., Zheng, Y., Wang, S., & Zhao, J. (2026). *Public transit gains and spatially uneven travel demand changes after NYC congestion pricing.* arXiv:2606.17530. https://arxiv.org/abs/2606.17530. Counterfactual demand forecasts from time-series foundation models.

**What overlaps and what is new.**
- **Overlap.** Those studies estimate congestion-pricing effects on road speeds and on ride-hailing and transit over the first months. The CBD-versus-rest-of-Manhattan design is standard in this literature. With 24 pre-policy months, the same design fails its pre-trend test here, for yellow taxis and for high-volume FHV.
- **New here:**
  - yellow taxis over 20 post-policy months;
  - the dispatch-channel decomposition;
  - the finding that standard yellow-taxi designs cannot separate the policy from the channel shift;
  - the forecasting-system view (detection delay, adaptation).
