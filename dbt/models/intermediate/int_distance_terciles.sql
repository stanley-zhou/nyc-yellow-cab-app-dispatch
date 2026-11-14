-- Fixed trip-distance tercile cut points, estimated once on valid in-grid trips picked up in
-- var('distance_tercile_period') (= the 52-week pre-period) so that a post-policy shift in trip
-- lengths cannot move the bins (DECISIONS.md). Bins: 0 < t1 <= c1 < t2 <= c2 < t3; trips with
-- no metered distance (trip_distance <= 0, Flex Fare exemption) go to `dist_unknown`.
{{ config(materialized='table') }}
{%- set p = var('distance_tercile_period') %}
select
    {{ quantile_cont('trip_distance', '1.0', 3) }} as c1,
    {{ quantile_cont('trip_distance', '2.0', 3) }} as c2,
    count(*)                              as n_trips
from {{ ref('int_trips_valid') }}
where pu_hour in (select hour_ts from {{ ref('int_hours') }})
  and distance_known                       -- unmetered trips have no distance (own bin)
  and pickup_ts >= date '{{ p[0] }}'
  and pickup_ts <  {{ plus_days("date '" ~ p[1] ~ "'", 1) }}
