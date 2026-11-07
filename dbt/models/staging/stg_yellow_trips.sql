-- Column projection only. `cbd_congestion_fee` exists only in 2025+ files; earlier files
-- yield NULL through union_by_name, and if no file on disk has it the column is a typed NULL.
{%- set src = source('raw', 'yellow_trips') %}
select
    tpep_pickup_datetime                           as pickup_ts,
    tpep_dropoff_datetime                          as dropoff_ts,
    try_cast(PULocationID as integer)              as pu_zone_id,
    try_cast(DOLocationID as integer)              as do_zone_id,
    try_cast(trip_distance as double)              as trip_distance,
    try_cast(fare_amount as double)                as fare_amount,
    try_cast(total_amount as double)               as total_amount,
    try_cast(passenger_count as double)            as passenger_count,
    try_cast(payment_type as integer)              as payment_type,
    {{ column_or_null(src, 'cbd_congestion_fee', 'double') }} as cbd_congestion_fee,
    cast(strptime(regexp_extract(filename, 'yellow_tripdata_(\d{4}-\d{2})\.parquet', 1), '%Y-%m')
         as date)                                  as source_month
from {{ src }}
