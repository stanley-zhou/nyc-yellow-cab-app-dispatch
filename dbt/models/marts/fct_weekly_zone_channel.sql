-- Weekly version of fct_daily_zone_channel (panel weeks; Amendment 4, D1): pickups per
-- (pickup zone, week, VendorID, channel, platform, trip type, CMT-block flag).
{{ config(materialized='table') }}
select
    zone_id,
    week_start,
    {{ event_week('week_start') }}
                                                                          as event_week,
    vendor_id, channel, platform, trip_type, zone_group, is_cmt_outer_block,
    sum(pickups)::integer                                                 as pickups
from {{ ref('fct_daily_zone_channel') }}
group by all
