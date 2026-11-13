# Dashboard specification: *Where the Growth Came From: App Dispatch and NYC Yellow Cabs, 2023–2026*

Stanley builds this dashboard and publishes it on Tableau Public. The Builder supplies the data (`make tableau-extract` → `reports/tableau/`, field definitions in `reports/tableau/README.txt`) and this one-page specification. No mock-ups or screenshots are produced.

## Rules for every view (PLAN Amendment 5)

**Language**
- Titles state measured facts.
- No title or caption may say that app dispatch *caused* growth.
- No title or caption may say that congestion pricing had, or had no, effect.
- The causal estimates are labelled exactly as in the report: "not identified" (D2) and "preliminary, not identified" (D3).

**Numbers**
- Any number in a title is copied from the results file named in its caption.
- Do not compute new headline numbers in Tableau.

**Definitions shown on every view**
- **App** = any e-hail app: Flex Fare before 2026-06, `request_source` from 2026-06.
- **Street hail** excludes the CMT contracted block (outer boroughs, ended 2026-05). The block is a separate series or omitted, never added to street hails.

**Colours**
- App = teal `#1E8C7E`; street hail = sand `#C2A878`; CMT block = grey `#B0B4BA`.
- The red accent `#B23A48` is used only to mark the CBD.
- Maps use a single-hue sequential scale for shares and a diverging scale, centred at 0, for growth.

**Reference lines** (dashed, labelled):
- Uber auto-dispatch of yellow cabs begins, 2023-08 (amNY, 2023-08-29);
- congestion pricing begins, 2025-01-05;
- `request_source` reported, 2026-06;
- first Lyft (HV0005) trip, 2026-08-10.

## View 1: App share over time by area

| | |
|---|---|
| **Source** | `channel_zone_week.csv` |
| **Measure** | SUM(app) / (SUM(app) + SUM(street_hail)) per week |
| **Areas** | Group zones by `zone_group`: CBD, Manhattan non-CBD, other = outer boroughs. Airports appear in a small grey note only: app share below 1%, no app-channel conclusion. |
| **Chart** | One line per area on one axis (0–100%), weekly, Jan 2023 → Sep 2026 |
| **Companion chart** | Stacked weekly pickups by channel for the selected area (app, street hail, CMT block) on its own axis — never a second y-axis |
| **Filter** | Area |
| **Tooltip** | Week, app, street hail, total, share |
| **Caption** | `results/channel_monthly.csv`, `results/channel_decomposition.csv` (D1). Monthly figures compare months of 4 and 5 weeks, so use weekly means. |

## View 2: Zone map of app share and growth

| | |
|---|---|
| **Source** | `zones.geojson` joined on `zone_id` to `zone_summary.csv` |
| **Map A** | `app_share_excl_block_<period>`, with a period parameter: 2023, 2024, 2025, Jan–Sep 2026 |
| **Map B** | `growth_log_2023_2025` as log ratio, labelled in % via exp(x) − 1, diverging and centred at 0 |
| **Low-volume zones** | Zones with fewer than 20 pickups a week, or a blank growth value, are shown in grey and labelled "too few trips" |
| **CBD** | Outlined (`is_cbd`) |
| **Linked chart** | Scatter of growth vs 2025 app share, one dot per zone, CBD in the accent colour |
| **Tooltip** | Zone, borough, mean weekly pickups per period, app share per period |
| **Caption** | `results/channel_zone_share.csv`, F6b. The C1 correlation is in `results/app_dispatch_summary.json`; it is a correlation, not an effect. |

## View 3: Incrementality by area, with intervals

| | |
|---|---|
| **Source** | `incrementality.csv` |
| **Chart** | Dot-and-whisker. Rows: area (CBD, Manhattan non-CBD, outer boroughs). Marks: estimator (primary DML; DML with zone trends; DoubleML panel as the median of 25 fold draws; TWFE; first differences). Whiskers: `ci_lo` to `ci_hi`. |
| **Reference lines** | θ = 0 "every app trip replaces a street hail"; θ = 1 "every app trip is additional" |
| **Title** | The Amendment-5 sentence, verbatim: "Estimates of the share of app trips that are additional range from 0.52 to 2.62 across estimators in the CBD; the primary DML gives 0.90 [0.74, 1.06]; the estimators disagree beyond their intervals and one lead placebo fails, so incrementality is not identified from these data." |
| **Note** | The accounting net ratio (`results/channel_decomposition.csv`, `accounting_net_ratio`) may appear as a separate text tile only, labelled "arithmetic on observed changes, not an incrementality estimate" |
| **Caption** | `results/incrementality_dml.json`, F6c |

## View 4: Lyft entry, before and after (preliminary)

| | |
|---|---|
| **Source** | `lyft_entry_daily.csv` |
| **Data** | CBD and Manhattan non-CBD only |
| **Chart** | Weekly sum per vendor, Curb (gains Lyft) vs CMT (control), each indexed to its mean over the 8 weeks to 2026-07-08 (= 100). Panels for total and app pickups. |
| **Excluded window** | 2026-07-09 → 2026-08-09 shaded and labelled "excluded: code-A surge (hypothesis: Lyft before HV0005)" |
| **Companion chart** | Daily Lyft trips (`lyft`) on Curb cabs from 2026-08-10, on its own axis |
| **Title** | Must contain "preliminary, not identified" |
| **Caption** | `results/lyft_entry.json`, F6d. The pre-registered levels design is not credible on scale; the log design fails its pre-trend test. Refresh with `make lyft-refresh` when TLC publishes later months. |

## Refresh and publication

1. Run `make tableau-extract` after any rerun of `make channel`.
2. Replace the extracts in the Tableau workbook.
3. Republish.

The README links the published dashboard once Stanley supplies the URL.
