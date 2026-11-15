# Dashboard specification: *Where the Growth Came From: App Dispatch and NYC Yellow Cabs, 2023–2026*

Published on Tableau Public: [Where the Growth Came From – NYC Yellow Cabs and App Dispatch](https://public.tableau.com/app/profile/stanley.zhou7746/viz/WheretheGrowthCameFrom-NYCYellowCabsandAppDispatch/Overview).

The specification has five views: the headline in three number tiles, the app share over time by area, a zone map of app share and growth, incrementality estimates with their intervals, and Lyft's entry on Curb cabs. Its data are the extracts made by `make tableau-extract` (`reports/tableau/`; field definitions in `reports/tableau/README.txt`), and every number shown comes from the results file named in the view's caption.

## Version 1 as built

One dashboard page, **"Overview"**, 1400 × 1700, holding:

| Part | As built |
|---|---|
| **View 0** | The three headline tiles, as specified below. |
| **Citywide weekly chart** | Stacked weekly pickups citywide by channel, app and street hail, from `channel_zone_week.csv` (columns `app`, `street_hail`; the contracted trip programme is not added to street hails). |
| **View 1** | App share over time by area, airports filtered out. Colours: CBD `#B23A48`, Manhattan outside the CBD `#9AA5B1`, outer boroughs `#4F7CAC`. Reference lines at 2023-08-29 "Uber dispatch begins" and 2025-01-05 "Congestion pricing begins". |
| **View 2, Map A** | App share by zone with the period parameter. Zones under 20 pickups a week (`config/project.yaml → channel.map_min_weekly`) are left blank. |

Not built in version 1: View 2 Map B, the View 2 scatter, View 3 and View 4. Their specifications below are kept for a later version.

## Rules for every view

**Language**
- Titles state measured facts.
- No title or caption may say that app dispatch *caused* growth.
- No title or caption may say that congestion pricing had, or had no, effect.
- The causal estimates are labelled exactly as in the report: "not identified" (incrementality of app trips) and "preliminary, not identified" (Lyft's entry).

**Numbers**
- Any number in a title is copied from the results file named in its caption.
- Do not compute new headline numbers in Tableau.

**Definitions shown on every view**
- **App** = any e-hail app: Flex Fare before 2026-06, `request_source` from 2026-06.
- **Street hail** excludes the contracted trip programme on CMT-metered cabs (outer boroughs, ended 2026-05). The programme is a separate series or omitted, never added to street hails.

**Colours**
- App = teal `#1E8C7E`; street hail = sand `#C2A878`; contracted trip programme = grey `#B0B4BA`.
- The red accent `#B23A48` is used only to mark the CBD (in version 1, the CBD line of View 1).
- Areas in version 1 (View 1): CBD `#B23A48`, Manhattan outside the CBD `#9AA5B1`, outer boroughs `#4F7CAC`.
- Maps use a single-hue sequential scale for shares and a diverging scale, centred at 0, for growth.

**Reference lines** (dashed, labelled; version 1 draws the first two on View 1, labelled "Uber dispatch begins" (2023-08-29) and "Congestion pricing begins" (2025-01-05)):
- Uber auto-dispatch of yellow cabs begins, 2023-08 (amNY, 2023-08-29);
- congestion pricing begins, 2025-01-05;
- `request_source` reported, 2026-06;
- first Lyft (HV0005) trip, 2026-08-10.

## View 0: The headline in three tiles

| | |
|---|---|
| **Source** | `results/presentation_numbers.json → citywide_accounting.by_area.all` (copied, not recomputed in Tableau) |
| **Tile 1** | "+27.3%": yellow-taxi pickups, mean per week, 2025 vs 2023 (703,268 → 895,177) |
| **Tile 2** | "+199,068 a week": app-dispatched trips, 2025 vs 2023 |
| **Tile 3** | "−7,159 a week (−1.1%)": street hails, 2025 vs 2023 |
| **Caption** | The contracted trip programme is left out. Source: `results/channel_decomposition.csv` (rows `2023_to_2025`, `all`, without the programme). |

## View 1: App share over time by area

Built in version 1 with airports filtered out (see *Version 1 as built*).

| | |
|---|---|
| **Source** | `channel_zone_week.csv` |
| **Measure** | SUM(app) / (SUM(app) + SUM(street_hail)) per week |
| **Areas** | Group zones by `zone_group`: CBD, Manhattan outside the CBD, other = outer boroughs. Airports appear in a small grey note only: app share below 1%, no app-channel conclusion. |
| **Chart** | One line per area on one axis (0–100%), weekly, Jan 2023 → Sep 2026 |
| **Companion chart** | Stacked weekly pickups by channel for the selected area (app, street hail, contracted trip programme) on its own axis — never a second y-axis |
| **Filter** | Area |
| **Tooltip** | Week, app, street hail, total, share |
| **Caption** | `results/channel_monthly.csv`, `results/channel_decomposition.csv`. Monthly figures compare months of 4 and 5 weeks, so use weekly means. |

## View 2: Zone map of app share and growth

Version 1 builds Map A only, with zones under 20 pickups a week left blank. Map B and the linked scatter are **not built in version 1**.

| | |
|---|---|
| **Source** | `zones.geojson` joined on `zone_id` to `zone_summary.csv` |
| **Map A** | `app_share_excl_block_<period>`, with a period parameter: 2023, 2024, 2025, Jan–Sep 2026 |
| **Map B** (not built in version 1) | `growth_log_2023_2025` as log ratio, labelled in % via exp(x) − 1, diverging and centred at 0 |
| **Low-volume zones** | Map A (version 1): zones with fewer than 20 pickups a week in the period are left blank. Map B (later version): zones with a blank growth value are shown in grey and labelled "too few trips" |
| **CBD** | Outlined (`is_cbd`) |
| **Linked chart** (not built in version 1) | Scatter of growth vs 2025 app share, one dot per zone, CBD in the accent colour |
| **Tooltip** | Zone, borough, mean weekly pickups per period, app share per period |
| **Caption** | `results/channel_zone_share.csv`, F6b. The correlation of growth with app share is in `results/app_dispatch_summary.json`; it is a correlation, not an effect. |

## View 3: Incrementality by area, with intervals

**Not built in version 1.**

| | |
|---|---|
| **Source** | `incrementality.csv` |
| **Chart** | Dot-and-whisker. Rows: area (CBD, Manhattan outside the CBD, outer boroughs). Marks: estimator (primary DML; DML with zone trends; DoubleML panel as the median of 25 fold draws; TWFE; first differences). Whiskers: `ci_lo` to `ci_hi`. |
| **Reference lines** | θ = 0 "every app trip replaces a street hail"; θ = 1 "every app trip is additional" |
| **Title** | This sentence, verbatim: "Estimates of the share of app trips that are additional range from 0.52 to 2.62 across estimators in the CBD; the primary DML gives 0.90 [0.74, 1.06]; the estimators disagree beyond their intervals and the lead placebo fails in Manhattan outside the CBD, so incrementality is not identified from these data." |
| **Note** | The accounting net ratio (`results/channel_decomposition.csv`, `accounting_net_ratio`) may appear as a separate text tile only, labelled "arithmetic on observed changes, not an incrementality estimate" |
| **Caption** | `results/incrementality_dml.json`, F6c |

## View 4: Lyft entry, before and after (preliminary)

**Not built in version 1.**

| | |
|---|---|
| **Source** | `lyft_entry_daily.csv` |
| **Data** | CBD and Manhattan outside the CBD only |
| **Chart** | Weekly sum per vendor, Curb (gains Lyft) vs CMT (control), each indexed to its mean over the 8 weeks to 2026-07-08 (= 100). Panels for total and app pickups. |
| **Excluded window** | 2026-07-09 → 2026-08-09 shaded and labelled "excluded: code-A surge (hypothesis: Lyft before HV0005)" |
| **Companion chart** | Daily Lyft trips (`lyft`) on Curb cabs from 2026-08-10, on its own axis |
| **Title** | Must contain "preliminary, not identified" |
| **Caption** | `results/lyft_entry.json`, F6d. The pre-registered levels design is not credible on scale; the log design fails its pre-trend test. Refresh with `make lyft-refresh` when TLC publishes later months. |

## Refresh and publication

1. Run `make tableau-extract` after any rerun of `make channel`.
2. Replace the extracts in the Tableau workbook.
3. Republish.

Published (version 1): [Tableau Public, "Overview"](https://public.tableau.com/app/profile/stanley.zhou7746/viz/WheretheGrowthCameFrom-NYCYellowCabsandAppDispatch/Overview). The README links it.
