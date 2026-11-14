-- Valid, de-duplicated trips (every rule in int_trips_flagged passed). Each surviving distinct row
-- counts once, whatever its number of exact copies. Per-rule counts: fct_data_quality_monthly.
-- `pu_hour` / `do_hour` = floored local pickup/dropoff hour; a trip enters the hourly grid only if
-- that hour exists in int_hours (misses are counted in int_grid_misses).
select
    vendor_id, pickup_ts, dropoff_ts, pu_zone_id, do_zone_id, trip_distance, fare_amount, total_amount,
    passenger_count, payment_type, cbd_congestion_fee, request_source, source_month, is_format_exempt,
    -- meter-derived fields are only known when the meter produced them (record-format exemptions):
    coalesce(trip_distance > 0, false)  as distance_known,
    coalesce(fare_amount > 0, false)    as revenue_known,
    date_trunc('hour', pickup_ts)  as pu_hour,
    date_trunc('hour', dropoff_ts) as do_hour
{%- if target.type == 'snowflake' %}
from {{ source('raw', 'yellow_trips_valid') }}  {#- E3: loaded output of the DuckDB cleaning #}
{%- else %}
from {{ ref('int_trips_flagged') }}
where drop_reason is null
{%- endif %}
