-- Valid in-grid pickups per (pickup zone, panel week, VendorID): sparse long table (a row only where
-- the vendor has >= 1 pickup in that zone-week). Added at Checkpoint 1 (Stanley) for the vendor
-- checks: weekly volume by vendor CBD vs non-CBD, the share of Flex Fare and Helix trips by
-- treatment group, and the Phase 4 DiD restricted to vendors present throughout the window
-- (DECISIONS.md). Same trip set as fct_weekly_zone_panel: summing over vendor_id (NULL included)
-- reproduces its pickups for every zone-week (dbt test assert_vendor_panel_matches_weekly).
{{ config(materialized='table') }}
with t as (
    select
        pu_zone_id                                        as zone_id,
        {{ week_start('cast(pu_hour as date)') }}         as week_start,
        vendor_id,
        payment_type,
        is_format_exempt,
        dropoff_ts = pickup_ts                            as same_ts
    from {{ ref('int_trips_valid') }}
    where pu_hour in (select hour_ts from {{ ref('int_hours') }})
)
select
    zone_id,
    week_start,
    datediff('day', {{ week_start("date '" ~ var('policy_date') ~ "'") }}, week_start) // 7
                                                                          as event_week,
    vendor_id,
    count(*)::integer                                                     as pickups,
    count(*) filter (where payment_type = {{ var('flex_fare_payment_type') }})::integer
                                                                          as pickups_flex,
    count(*) filter (where is_format_exempt)::integer                     as pickups_format_exempt,
    -- identical pickup/dropoff timestamps (the missing-dropoff-time record pattern)
    count(*) filter (where same_ts)::integer                              as pickups_same_ts
from t
group by zone_id, week_start, vendor_id
