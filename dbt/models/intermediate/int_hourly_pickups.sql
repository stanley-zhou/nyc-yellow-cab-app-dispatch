-- Pickups aggregated per (pickup zone, floored local hour) over all valid trips. Hours outside the
-- grid survive here and are dropped by the grid join in fct_hourly_zone_demand (they are counted
-- in int_grid_misses; the two add up, dbt test assert_hourly_pickups_equal_valid_in_grid).
{{ config(materialized='table') }}
select
    pu_zone_id                                     as zone_id,
    pu_hour                                        as hour_ts,
    count(*)                                       as pickups,
    sum(total_amount)                              as revenue,
    avg(trip_distance)                             as mean_distance,
    count(*) filter (where cbd_congestion_fee > 0) as n_cbd_fee_trips,
    count(*) filter (where is_format_exempt)    as n_format_exempt
from {{ ref('int_trips_valid') }}
group by all
