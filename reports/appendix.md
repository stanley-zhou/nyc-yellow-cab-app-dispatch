# Appendix: Where the Growth Came From

Details behind the [main report](analysis.md). Every number links to its file under `results/`. Labels in brackets, such as (D2), are the cross-references used in [`PLAN.md`](../PLAN.md) and [`DECISIONS.md`](../DECISIONS.md).

## A1. Data

- **Yellow-taxi records.** 341,589,889 raw records, 2019-01 → 2026-09. After de-duplication and the validity rules, 331,436,471 remain (2.97% removed; [data_quality.json](../results/data_quality.json)). Aggregation is in DuckDB and dbt: the panels and every heterogeneity cut are SQL models, not pandas.
- **Modeled zones.** Forecasting covers 103 zones, which carry 99.04% of 2024 pickups ([modeled_zones.json](../results/modeled_zones.json)).
- **App-dispatch label** (Amendment 4a). The Flex Fare flag (an upfront app price) before 2026-06; the `request_source` field from 2026-06. On June–September 2026 the two labels agree on 99.97–100% of trips ([channel_label_validation.json](../results/channel_label_validation.json)).
  - Uber and Lyft make up 87.8% of app trips there.
  - Codes EH0004 and EH0010 are Curb's and Arro's own apps (TLC e-hail licence list).
  - Codes A and CC are on no published TLC list and stay undetermined.
  - Platform-level results (Uber, Lyft) exist only from June 2026.
- **High-volume FHV records** (Uber, Lyft). 45 months, 904,683,847 trips, aggregated month by month, with the raw files deleted after verification ([hvfhv_summary.json](../results/hvfhv_summary.json), [hvfhv_stream_log.csv](../results/hvfhv_stream_log.csv)).
- **Monthly versus weekly.** Months hold four or five panel weeks. Per week, CBD yellow pickups rose 15.6% between January 2023 and January 2026 (392,751 → 453,882), and CBD street hails fell 16.7% (383,608 → 319,640) ([channel_restatement.json](../results/channel_restatement.json)). Monthly sums compare a five-week with a four-week January and must not be used.
- **Supply before 2023.** In 2022, with about 5,930 active cabs a day, trips per cab-day were 18.3. As active cabs rose to about 7,040 a day in 2023, trips per cab-day fell to 14.8, and from then on stayed between 14.0 and 15.0 ([presentation_numbers.json → supply](../results/presentation_numbers.json)).
- **External check of the app share.** At a City Council hearing on 2025-02-10, the TLC said that e-hail trips were "about five to 10% of all taxi trips", depending on the month, without naming a period ([transcript](https://citymeetings.nyc/city-council/2025-02-10-1000-am-committee-on-transportation-and-infrastructure/chapter/update-on-the-e-hail-program-for-yellow-and-green-taxis)). My 2024 monthly app share of all yellow pickups ranges from 4.8% to 13.1% and lies inside 5–10% in only 3 of 12 months (above it in 8, below in 1) ([presentation_numbers.json → external_app_share_2024](../results/presentation_numbers.json)). The two do not agree. Possible reasons, none tested: the statement may cover green taxis too, may refer to other months, or may count a narrower e-hail programme than the Flex Fare flag.
- **Other step dates.** Besides the steps in the main text, the all-zone app share fell by 5.9 points at the week of 2026-03-01 ([channel_label_validation.json → flex_share_steps](../results/channel_label_validation.json)). No public source dates the 2024-09, 2025-05 or 2026-03 changes.

## A2. The contracted trip programme

One block of outer-borough "street hails" is a centrally paid trip programme on cabs with CMT meters ([cmt_block_diagnosis.json](../results/cmt_block_diagnosis.json)):
- 93% carry a non-standard rate code (99);
- 99% have a single rider;
- 3% are tipped;
- the median trip is 43 minutes, in daytime, from central and east Brooklyn.

It ended at the end of May 2026, and no other vendor picked it up. Without it, the outer-borough app share went from 13.3% to 89.4% (2023-01 → 2026-01).

**Other accounting views** ([channel_decomposition.csv](../results/channel_decomposition.csv), [cross_platform_monthly.csv](../results/cross_platform_monthly.csv)):
- Over January–September 2026 against the same weeks of 2023, CBD street hails are 12.0% lower (−48,303 a week) and CBD app trips 113,506 a week higher.
- The accounting net ratio is the net change in pickups per app pickup added. It is arithmetic on observed changes, not an incrementality estimate: 0.944 in the CBD for 2023 → 2025, 0.574 for January–September 2023 → 2026.
- Yellow app trips grew from 0.75% to 10.86% of all app-dispatched CBD trips, yellow plus Uber and Lyft (January 2023 → January 2026).

## A3. Incrementality of app trips

(D2; [incrementality_dml.json](../results/incrementality_dml.json), [incrementality_panel_summary.csv](../results/incrementality_panel_summary.csv); [F6c](figures/F6c_incrementality.png))
- The primary estimator is double machine learning with LightGBM models for the outcome and the treatment, time-blocked cross-fitting and zone-clustered errors.
- Values above 1 in several estimators mean street hails and app trips rise and fall together within a zone-week: shared local demand shocks, not displacement.
- The DoubleML panel estimator is the median of 25 fold draws (0.52, range 0.49–0.56).
- The lead placebo passes in the CBD (p = 0.60) and fails in Manhattan outside the CBD (p = 9.8e−05) ([presentation_numbers.json → preregistered_checks](../results/presentation_numbers.json)).

**Cross-platform view** (D4; [DECISIONS.md](../DECISIONS.md)). Per additional yellow app trip per zone-week, Uber + Lyft trips changed by −0.166 [−0.502, +0.169] in the CBD and −0.381 [−0.733, −0.029] in Manhattan outside it. In the outer boroughs the coefficient is +4.388, which says the regression picks up shared demand shocks there, not displacement ([cross_platform.json](../results/cross_platform.json)).

## A4. Lyft's entry on Curb cabs

(D3, preliminary, not identified; [lyft_entry.json](../results/lyft_entry.json); [F6d](figures/F6d_lyft_entry.png))

Lyft trips appear only on Curb-equipped cabs, from 2026-08-10 ([request_source_daily.csv](../results/request_source_daily.csv)). The pre-registered vendor-level DiD in levels gives an implausible −1.12 Lyft-trip incrementality: Curb cabs carry 4.3 times CMT's volume, so common percentage swings appear as level changes. The log specification gives 0.68 [0.09, 1.23] but fails its pre-trend test. `make lyft-refresh` re-estimates once the TLC publishes later months.

## A5. Congestion pricing: the designs in detail

- **Yellow demand, zones weighted by volume.** CBD vs the 25 Manhattan control zones: −5.2% [−12.8%, +3.0%] ([did_static.json](../results/did_static.json); [F4](figures/F4_event_study.png)).
  - The pre-trend test rejects (Hotelling F* p = 1.6e−17; [placebo.json](../results/placebo.json)).
  - With every Manhattan zone outside the CBD as control, the estimate moves to −1.0%.
  - The estimate lies outside all 500 random-zone and all 54 fake-date placebos ([power_mde.json](../results/power_mde.json); [F4e](figures/F4e_placebo_distribution.png)), as the diverging app-dispatch trend would produce.
  - Leave one zone out: [leave_one_out.csv](../results/leave_one_out.csv); [F4i](figures/F4i_leave_one_out.png). Sub-groups: [heterogeneity.csv](../results/heterogeneity.csv); [F4c](figures/F4c_heterogeneity.png).
- **Synthetic control** (C3). CBD pickups are −1.2% against the synthetic CBD, rank 11 of 16 (p = 0.69). The method produces +4.6% at a fake 2024 date, so it cannot resolve the question ([synth_control.json](../results/synth_control.json); [F4h](figures/F4h_synth_control.png)).
- **High-volume FHV** (C6). Every Uber, Lyft and shared-ride series fails the pre-trend test (Uber + Lyft, volume-weighted, p = 2.3e−18), so no effect is estimated ([fhv_did.json](../results/fhv_did.json); [F6](figures/F6_taxi_vs_fhv.png)).
- **Trip speed** (B1, C4). Within-CBD speed is +1.9% against Manhattan outside the CBD and −4.0% against Brooklyn and Queens. Both designs fail their pre-trend tests ([speed_did.json](../results/speed_did.json), [speed_did_outer.json](../results/speed_did_outer.json); [F4f](figures/F4f_speed_event_study.png)).
- **By channel** (D5). Both the street-hail and the app DiD fail the pre-trend gate ([did_by_channel.json](../results/did_by_channel.json)).
- **Did the fee move trips into apps?** (D5b). The app share jumped about 11 points in the weeks after 2025-01-19, the same for trips touching the CBD (+8.1 to +11.3 points) as for trips touching neither end (+10.6). The size of the jump did not differ with exposure to the fee. This comparison of steps does not need parallel trends; the DiD of the app share (+3.0 points) does, and fails its pre-trend test ([app_share_policy_step.json](../results/app_share_policy_step.json); [F6e](figures/F6e_app_share_step.png)).

## A6. The methods case: test size and the forecast check

- **Pre-trend test size.** With 24 monthly pre-policy coefficients and 63 zone clusters, the pre-registered F test rejects 56% of the time at a 5% level on data without a pre-trend. The Hotelling-corrected test has about the right size, 9.5% ([pretrend_test_size.json](../results/pretrend_test_size.json)). The real p-values are far below either.
- **Event-study means.** The headline numbers are the static DiD estimates (−34.6%, −5.2%). The mean of the monthly event-study coefficients after the policy is −40.5% with equal zone weights and −11.3% with zones weighted by volume; the frozen forecast's mean is +2.0% ([figure_stats_phase4.json](../results/figure_stats_phase4.json); [F4d](figures/F4d_counterfactual_vs_did.png)).
- **Equal-weight leave-one-out.** −36.3% to −32.0% ([did_static.json](../results/did_static.json)).

## A7. Forecasting details

**Baseline year (2024).** Over the 103 modeled zones, WAPE was 16.5% for Chronos-2 zero-shot with weather as a past covariate, 16.7% for LightGBM and 24.1% for the seasonal naive ([wape_gap_bootstrap.csv](../results/wape_gap_bootstrap.csv)). Chronos-2 that also sees the target day's observed weather has 16.5% to one decimal (0.1645 against 0.1652); it uses information not available at forecast time, so it is a sensitivity. Relative to the seasonal naive, error is 31.5% lower for Chronos-2 with past weather and 30.5% lower for LightGBM ([presentation_numbers.json → forecast_vs_seasonal_naive_2024](../results/presentation_numbers.json)). Rolling 12-week conformal calibration brings 80%-interval coverage to 82% (LightGBM) and 79% (Chronos-2) ([forecast_summary.json](../results/forecast_summary.json)).

**Monitoring at the policy date.** A LightGBM frozen at 2024-12-31 showed no CBD-specific break; CBD rolling WAPE did not rise ([drift_detection.json](../results/drift_detection.json); [F3](figures/F3_error_over_time.png)).
- The first CBD CUSUM alarm (2025-01-19), the only one in the first twelve months, is the kind the 2024 calibration year also produced (one alarm, 2024-09-10, up; the threshold allows one a year).
- Two further CBD alarms, both downward, came on 2026-01-26 and 2026-02-23 (outside the CBD: 2026-01-25 and 2026-02-23). Both follow snowstorms: 7.5 inches of snow fell on 2026-01-25, and 3.6 and 5.5 inches on 2026-02-22 and 2026-02-23. CBD pickups ran 50.6% and 72.7% below the frozen forecast on 2026-01-25 and 2026-02-23 ([presentation_numbers.json → alarm_weather_check](../results/presentation_numbers.json), [alarm_weather_check.csv](../results/alarm_weather_check.csv)). The monitor flagged two storms within a day.

**Three shocks, one monitor** (C5), each with a model trained on the 12 months before the event ([shock_comparison.json](../results/shock_comparison.json); [F3b](figures/F3b_three_shocks.png)):

| Shock | CBD vs forecast, first 28 days | First CBD alarm after the event |
|---|---|---|
| COVID-19 | −56.0% | day 13 |
| Metered-fare increase (Dec 2022) | +9.7% | day 162 (2023-05-30) |
| Congestion pricing | +7.3% | day 354 (2025-12-25) |

COVID-19 was flagged on day 13. The fare increase and congestion pricing produced no alarm for five and eleven months; the later alarms fall on the dates given and are not detections of either event. The +7.3% differs from the +6.3% of the main text because this comparison uses a model trained on the 12 months before each event, while the main monitor uses the model trained on 2022–2024.

**Strategies, February 2025 → September 2026** (Phase 5; [adaptation.csv](../results/adaptation.csv), [adaptation_summary.json](../results/adaptation_summary.json), [adaptation_gaps.csv](../results/adaptation_gaps.csv); [F5](figures/F5_adaptation.png)):

| Strategy | WAPE, all zones | WAPE, CBD | Bias, % of pickups | 80% coverage (rolling conformal) |
|---|---|---|---|---|
| Frozen model (S0), trained to 2024-12-31 | 16.4% | 15.4% | −2.3% | 81% |
| Monthly retrain (S1), sliding 24 months | **16.2%** | **15.1%** | −1.7% | 80% |
| Chronos-2 zero-shot (S4) | 16.5% | 15.4% | −2.0% | 80% |
| Monthly retrain + trailing app-share features (S6) | 16.8% | 15.7% | −2.9% | 80% |
| *Sensitivity:* monthly retrain on an expanding window (S1e) | 16.2% | 15.2% | −1.8% | 81% |
| *Reference:* seasonal naive, frozen | 23.7% | 22.3% | −0.1% | 81% |

Table notes.
- Quarters are assigned by origin date, so 2025-Q1 covers only 2025-02-01 → 03-31; its rolling-conformal coverage is 80–82% for the four strategies.
- Every row's intervals are recalibrated by the rolling 12-week conformal. The frozen model's point forecasts are frozen but its intervals adapt (raw coverage 78%, calibrated 81%). Before 2025 the frozen model is in-sample, so its calibration residuals there come from the out-of-sample backtest.
- The seasonal naive has no forecast for 206 hours whose lag-168 h hour is the missing spring-forward hour; they are left out of its metrics.
- MASE over all zones is above 1 for every row (frozen model 1.40, seasonal naive 1.89), because the scale is the 2022–2024 in-sample seasonal-naive error and outer-borough volume has grown since. It does not mean the strategies lose to the naive forecast, which every strategy beats by about 7 points of WAPE.

Findings.
- **Monthly retrain against the frozen model.** It is ahead by 0.23 points of WAPE over all zones and 0.29 in the CBD; both bootstrap intervals exclude zero. In Manhattan outside the CBD the two are not distinguishable. Monthly retraining on the frozen model's expanding window gains 0.24 points (interval excludes zero); moving that retraining to the sliding window changes WAPE by 0.01 points (interval includes zero). The gain is from retraining, not from the window.
- **Chronos-2.** Not distinguishable from the frozen model or the monthly retrain over all zones or in the CBD. It is the best of the four in the outer boroughs (39.5% against 40.3% for the monthly retrain and 41.2% frozen) and at the airports (17.5% against 17.9%, interval excludes zero), and distinguishably behind in Manhattan outside the CBD (14.7% against 14.2%).
- **App-share features are a negative result.** The pre-registered expectation (D6) was that they would remove most of the post-2025 bias. They did not: this strategy has the largest under-forecast and the highest WAPE of the four, distinguishably worse than the frozen model and the monthly retrain. The features are trailing app shares: they describe the channel mix after it has moved and do not anticipate the level of demand. In the outer boroughs they give the smallest under-forecast (−6.0%, against −10.8% frozen, −7.0% monthly retrain, −6.9% Chronos-2; [adaptation_summary.json → bias_pct_of_pickups](../results/adaptation_summary.json)).
- **Every strategy errs at the same time.** All four rise together in 2026-Q1 (WAPE 18.7–19.1%, against 16.2–16.4% in 2025-Q1). Part of the rise is the two snowstorms: the four days with at least 2 inches of snow carry 9–11% of the quarter's absolute error, and without them the quarter's WAPE is 17.0–17.6%. The cause of the remainder is not determined.
- **Intervals.** With rolling 12-week conformal calibration every strategy covers 80–81% of hours with its 80% interval; raw intervals cover 74–78%.
- **Cost.** A LightGBM refit takes a median of 384 s on the 12-core local CPU, and a month of monthly retraining (refit plus that month's daily forecasts) a median of 411 s (23 refits). The expanding-window refit takes a median of 720 s, about twice as long for the same accuracy. Chronos-2 needs no retraining but a GPU at every origin: a median of 250 s per month of daily origins on an L4 ([adaptation_summary.json → retrain_cost](../results/adaptation_summary.json)). The monthly retrain is not ahead in every quarter (the frozen model is ahead in 2025-Q1).

## A8. Experiment design

(A4; [experiment_design.json](../results/experiment_design.json))
- **Why not an A/B test here.** Geography cannot be randomized for a cordon toll; cabs, drivers and riders move between zones, so treated and control areas interfere; and the two channels share the same cabs.
- **Switchback noise.** In March–May 2026 the residual sd is 33.1 trips per zone-block, with 30.3 app trips per block and lag-1 autocorrelation 0.58.
- **Staggered vendor rollout.** Switching cab groups on one at a time is the alternative. Its observational analogue, Lyft's entry on Curb cabs, would need about 3,466 post days for the same precision.

## A9. Questions as first posed

- When ride-hail apps began dispatching NYC yellow cabs, did the taxi business grow, or did trips move between channels?
- What could the trip records say about Manhattan congestion pricing?
- How should a demand forecaster behave through such a shift?
