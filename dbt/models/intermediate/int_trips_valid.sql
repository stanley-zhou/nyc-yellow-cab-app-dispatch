-- Trip-level validity filters (thresholds from config/project.yaml via dbt vars).
-- Per-filter counts are written to results/data_quality.json in Phase 1.
with trips as (
    select distinct * from {{ ref('stg_yellow_trips') }}       -- exact duplicates removed
)
select *
from trips
where pickup_ts >= source_month - interval ({{ var('straggler_days') }}) day
  and pickup_ts <  source_month + interval 1 month + interval ({{ var('straggler_days') }}) day
  and dropoff_ts - pickup_ts >= interval ({{ var('min_duration_minutes') }}) minute
  and dropoff_ts - pickup_ts <= interval ({{ var('max_duration_hours') }}) hour
  and trip_distance > 0
  and trip_distance <= {{ var('max_trip_distance_miles') }}
  and fare_amount > 0
  and pu_zone_id between {{ var('zone_id_min') }} and {{ var('zone_id_max') }}
