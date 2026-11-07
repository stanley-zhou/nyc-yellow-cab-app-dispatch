-- Dropoffs aggregated per (dropoff zone, floored local hour) over all valid trips.
{{ config(materialized='table') }}
select do_zone_id as zone_id, do_hour as hour_ts, count(*) as dropoffs
from {{ ref('int_trips_valid') }}
group by all
