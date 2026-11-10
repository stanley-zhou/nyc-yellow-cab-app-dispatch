-- Trip-level speed sample (Amendment 2, B1-B3; DECISIONS.md Phase 4): valid in-grid trips with
-- pickup AND dropoff in Manhattan, picked up inside var('speed_window'). Treated / control /
-- entering / leaving categories are assigned downstream from the two zones.
-- `exclusion` (NULL = used in the speed analysis), checked in this order:
--   'duration' duration missing or < min_duration_minutes (incl. dropoff = pickup records)
--   'distance' no metered distance (trip_distance <= 0, e.g. Flex Fare records)
--   'speed'    distance / duration > max_speed_mph (record error; fixed before any speed data)
{{ config(materialized='view') }}
with z as (
    select zone_id from {{ ref('dim_zones') }} where borough = 'Manhattan'
),
t as (
    select
        v.pu_zone_id,
        v.do_zone_id,
        v.pu_hour,
        v.trip_distance,
        v.fare_amount,
        v.cbd_congestion_fee,
        v.distance_known,
        date_diff('second', v.pickup_ts, v.dropoff_ts) / 60.0 as duration_min
    from {{ ref('int_trips_valid') }} as v
    where v.pu_zone_id in (select zone_id from z)
      and v.do_zone_id in (select zone_id from z)
      and v.pu_hour in (select hour_ts from {{ ref('int_hours') }})
      and v.pickup_ts >= date '{{ var("speed_window")[0] }}'
      and v.pickup_ts <  date '{{ var("speed_window")[1] }}' + interval 1 day
)
select
    *,
    {{ week_start('cast(pu_hour as date)') }}                      as week_start,
    case when duration_min > 0 then trip_distance / (duration_min / 60.0) end as speed_mph,
    case
        when duration_min is null or duration_min < {{ var('min_duration_minutes') }} then 'duration'
        when not distance_known                                    then 'distance'
        when trip_distance / (duration_min / 60.0) > {{ var('max_speed_mph') }} then 'speed'
    end                                                            as exclusion
from t
