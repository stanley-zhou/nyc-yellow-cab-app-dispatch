-- Column projection only (plus two derived keys). `request_source` exists from the 2026-06 files
-- (Amendment 4, D1; NULL before). VendorID is projected since Checkpoint 1 (vendor
-- checks, DECISIONS.md). `cbd_congestion_fee` exists only in 2025+
-- files; earlier files yield NULL through union_by_name, and if no file on disk has it the column
-- is a typed NULL. `raw_row_hash` hashes every raw column (not just the projected ones) so that
-- int_trips_flagged removes exact duplicates of the full raw row (DECISIONS.md, Phase 1).
{%- set src = source('raw', 'yellow_trips') %}
select
    try_cast(VendorID as integer)                  as vendor_id,
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
    {{ column_or_null(src, 'request_source', 'varchar') }} as request_source,
    cast(strptime(regexp_extract(filename, 'yellow_tripdata_(\d{4}-\d{2})\.parquet', 1), '%Y-%m')
         as date)                                  as source_month,
    hash(*columns(* exclude (filename)))           as raw_row_hash,
    filename                                       as source_file
from {{ src }}
