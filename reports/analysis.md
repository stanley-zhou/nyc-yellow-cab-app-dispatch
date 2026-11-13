# Where the Growth Came From: App Dispatch and NYC Yellow Cabs, 2023–2026

*Yellow-taxi trip records of the NYC Taxi & Limousine Commission (TLC), 2023-01 → 2026-09, at the TLC-zone level. Every number below links to the file under `results/` it is read from; every judgement call is in [`DECISIONS.md`](../DECISIONS.md).*

## Executive summary

1. **The shift.** App dispatch, i.e. e-hail apps sending yellow cabs to riders, rose from 2.3% to 29.6% of yellow pickups in Manhattan's congestion-pricing zone (CBD) between January 2023 and January 2026 ([channel_restatement.json](../results/channel_restatement.json)), and from 2023 to 2025 mean weekly CBD pickups grew by 99,063 (+23.7%), with app trips up 104,958 a week and street hails down 5,896 ([channel_decomposition.csv](../results/channel_decomposition.csv)).
2. **The supply fact.** The growth came with more cabs on the road, not more trips per cab: active cabs per day rose from 7,036 (2023) to 8,722.5 (2025) while trips per cab-day stayed at 14.85 → 15.02 (TLC monthly reports; [incrementality_dml.json → supply](../results/incrementality_dml.json)).
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

> **Correction.** Two earlier claims rested on monthly sums: that CBD pickups *declined*, and that street hails fell "by about a third". Both compared a five-week January 2023 with a four-week January 2026 (review, [phase_6_round1](../reviews/phase_6_round1.md)).

**Growth accounting, 2023 → 2025, mean weekly pickups** ([channel_decomposition.csv](../results/channel_decomposition.csv)):

| Area | Change in total | From app trips | From street hails |
|---|---|---|---|
| CBD | +99,063 | +104,958 | −5,896 |
| Manhattan outside the CBD | +50,537 | +51,230 | −692 |
| Outer boroughs (contracted block excluded) | 8,277 → 51,803 | +42,811 | +715 |

Over January–September 2026 against the same weeks of 2023:
- CBD street hails are 12.0% lower (−48,303 a week);
- CBD app trips are 113,506 a week higher.

The **accounting net ratio** is the net change in pickups per app pickup added. It is arithmetic on observed changes, **not** an incrementality estimate. It is 0.944 in the CBD for 2023 → 2025 and 0.574 for Jan–Sep 2023 → 2026.

**A contracted programme that ended.** One block of outer-borough "street hails" is in fact a centrally paid trip programme on CMT-equipped cabs ([cmt_block_diagnosis.json](../results/cmt_block_diagnosis.json)):
- 93% carry a non-standard rate code (99);
- 99% have a single rider;
- 3% are tipped;
- the median trip is 43 minutes in daytime from central and east Brooklyn.

It ended at the end of May 2026, and no other vendor picked it up. It is reported as its own series. Without it, outer-borough app share went from 13.3% to 89.4% (2023-01 → 2026-01).

**Where app dispatch is common, yellow pickups grew most.**
- Across Manhattan zones, 2023 → 2025 growth correlates with the June–September 2026 Uber/Lyft share at r = 0.92 ([app_dispatch_summary.json](../results/app_dispatch_summary.json)). This is a correlation, not an effect.
- Yellow app trips grew from 0.75% to 10.86% of all app-dispatched CBD trips, yellow plus Uber/Lyft FHV (January 2023 → January 2026; [cross_platform_monthly.csv](../results/cross_platform_monthly.csv)).

**Supply** ([supply_monthly.csv](../results/supply_monthly.csv)). The TLC's monthly reports show the yellow fleet supplying more cab-days at a constant intensity:
- 104,422 yellow trips per day in 2023 and 131,133 in 2025;
- active cabs per day 7,036 → 8,722.5;
- trips per cab-day 14.85 → 15.02;
- hours per cab-day 8.28 → 8.61.

The trip records alone cannot say whether app dispatch brought the extra cabs back or the returning cabs took app trips.

## 3. What the trip records cannot identify, and how we know

Every causal design below was pre-registered with an expected direction and a gate before it was run. It was stopped where the gate failed and is reported as found.

**Incrementality of app trips (D2).** Estimates of the share of app trips that are additional range from 0.52 to 2.62 across estimators in the CBD. The primary DML gives 0.90 [0.74, 1.06]. The estimators disagree beyond their intervals, and one lead placebo fails, so incrementality is not identified from these data ([incrementality_dml.json](../results/incrementality_dml.json); F6c).
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

## 4. Methods note: how a textbook DiD produced a 42% effect that was not there, and how it was caught

**The result.** The pre-registered specification was a difference-in-differences of log(1 + weekly pickups) per zone, with zone and week fixed effects, 38 CBD zones against 25 Manhattan donut zones, and zone-clustered errors. It gave −0.425 log points, −34.6% [−47.7%, −18.3%], p = 0.0004 ([did_static.json → main](../results/did_static.json)). Leave-one-zone-out kept every estimate between −36.3% and −32.0%. It looked robust.

**The weighting.** Equal zone weights let small uptown control zones drive the control trend. Their yellow pickups grew several-fold from 2023 to 2025, and they are the zones where app dispatch is highest:
- the fastest-growing donut zones are 71–83% Uber/Lyft-dispatched;
- the CBD median is 27% ([app_dispatch_summary.json](../results/app_dispatch_summary.json); F4g).

A log difference against a fast-growing small-zone average reads their growth as a CBD decline. Weighting zones by their pre-period volume, which estimates the effect on the aggregate, shrinks the estimate to −5.2% with a CI that includes zero.

**How it was caught.**
1. The pre-trend test failed (p = 2.7e−10). A size simulation showed the pre-registered F test rejects 56% of the time at 5% in this design, whereas the Hotelling-corrected test has about the right size, 9.5% ([pretrend_test_size.json](../results/pretrend_test_size.json)). The real p-values are far below either, so the failure is real.
2. The frozen forecaster, which knows nothing about control zones, put CBD pickups at +2.0% against its forecast after the policy, while the pre-registered event-study path averaged −40.5% (F4d; [figure_stats_phase4.json](../results/figure_stats_phase4.json)).
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
- The single CBD CUSUM alarm (2025-01-19) is the kind the 2024 calibration year also produced ([drift_detection.json](../results/drift_detection.json); F3).

**Three shocks, one monitor (C5)**, each with a 12-month frozen model ([shock_comparison.json](../results/shock_comparison.json); F3b):

| Shock | CBD vs forecast, first 28 days | First CBD alarm |
|---|---|---|
| COVID-19 | −56.0% | day 13 |
| Metered-fare increase (Dec 2022) | +9.7% | day 162 |
| Congestion pricing | +7.3% | day 354 |

**Adaptation (Phase 5).**
Four strategies were compared on day-ahead forecasts with origins 2025-02-01 → 2026-09-30, scored with the Phase-2 metrics and a common MASE scale ([adaptation.csv](../results/adaptation.csv), [adaptation_summary.json](../results/adaptation_summary.json), [adaptation_gaps.csv](../results/adaptation_gaps.csv); F5).

| Strategy | WAPE, all zones | WAPE, CBD | Bias, % of pickups | 80% coverage (rolling conformal) |
|---|---|---|---|---|
| S0 frozen at 2024-12-31 | 0.164 | 0.154 | −2.3% | 0.81 |
| S1 monthly retrain, sliding 24 months | **0.162** | **0.151** | −1.7% | 0.80 |
| S4 Chronos-2 zero-shot | 0.165 | 0.154 | −2.0% | 0.80 |
| S6 S1 + trailing app-share features | 0.168 | 0.157 | −2.9% | 0.80 |

- **S1 vs S0.** S1 is ahead by 0.23 pp of WAPE over all modeled zones and 0.29 pp in the CBD; both bootstrap intervals exclude zero. In Manhattan outside the CBD the two are not distinguishable.
- **S4.** Chronos-2 is not distinguishable from S0 or S1 over all zones. It is the best of the four in the outer-borough zones (0.395 against 0.412 frozen) and distinguishably behind S0 and S1 in Manhattan outside the CBD (0.147 against 0.142).
- **S6 is a negative result.** The pre-registered expectation (Amendment 4, D6) was that channel-aware features would remove most of the post-2025 bias. They did not: S6 has the largest under-forecast and the highest WAPE of the four, distinguishably worse than S0 and S1. The features are trailing app shares, so they describe the channel mix after it has moved; they do not anticipate the level of demand.
- **Every strategy errs the same way at the same time.** All four rise together in 2026-Q1 (WAPE 0.187–0.191, [adaptation.csv](../results/adaptation.csv)); no strategy avoids it, so it is not an adaptation failure of one model.
- **Intervals.** With rolling 12-week conformal calibration, every strategy covers 0.80–0.81 of hours with its 80% interval; raw intervals cover 0.74–0.78.

**Recommendation for the forecasting system.** Retrain monthly (S1). One refit costs a median of 411 s on the 12-core local CPU (23 refits, [adaptation_summary.json → retrain_cost](../results/adaptation_summary.json)), the gain over the frozen model is small (0.23 pp of WAPE) but distinguishable over the whole window, though not in every quarter (S0 is ahead in 2025-Q1), and S1 also has the smallest bias. Chronos-2 needs no retraining but a GPU at every origin (a median of 250 s per month of daily origins on an L4) and buys no accuracy over S1 except in the outer boroughs. Channel features should not be added in their current trailing form.

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
- <!-- THIRD STUDY: to be confirmed with Stanley (PLAN cites three; only two identified) -->

**What overlaps and what is new.**
- **Overlap.** Those studies estimate congestion-pricing effects on road speeds and on ride-hailing and transit over the first months.
- **New here:**
  - yellow taxis over 20 post-policy months;
  - the dispatch-channel decomposition;
  - the finding that standard yellow-taxi designs cannot separate the policy from the channel shift;
  - the forecasting-system view (detection delay, adaptation).
