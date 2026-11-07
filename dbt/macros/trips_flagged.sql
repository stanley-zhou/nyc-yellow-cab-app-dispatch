{#- int_trips_flagged is built ONE SOURCE FILE AT A TIME: exact duplicates occur only within a
    file (results/duplicates_probe.json: 0 cross-file duplicates), so per-file grouping gives the
    same result as one global GROUP BY, while each hash table holds a single month instead of all
    raw rows (the global version spilled to disk without bound; DECISIONS.md, Phase 1). The model body selects
    the first file; the post-hook inserts the others in order. -#}

{% macro yellow_files() %}
  {%- set res = run_query("select file from glob('" ~ var('yellow_glob') ~ "') order by file") -%}
  {{ return(res.columns[0].values() | list) }}
{% endmacro %}

{% macro trips_flagged_select(source_file) %}
with dedup as (
    select
        pickup_ts, dropoff_ts, pu_zone_id, do_zone_id, trip_distance, fare_amount, total_amount,
        passenger_count, payment_type, cbd_congestion_fee, source_month, raw_row_hash,
        count(*)::integer                                                 as n_copies
    from {{ ref('stg_yellow_trips') }}
    where source_file = '{{ source_file }}'
    group by all
),
flags as (
    select
        * exclude (raw_row_hash),
        -- PLAN's literal rules
        not coalesce(
            pickup_ts >= source_month - interval ({{ var('straggler_days') }}) day
            and pickup_ts < source_month + interval 1 month
                            + interval ({{ var('straggler_days') }}) day, false)
                                                                          as fails_pickup_window,
        not coalesce(
            dropoff_ts - pickup_ts >= interval ({{ var('min_duration_minutes') }}) minute
            and dropoff_ts - pickup_ts <= interval ({{ var('max_duration_hours') }}) hour, false)
                                                                          as fails_duration_literal,
        not coalesce(
            trip_distance > 0 and trip_distance <= {{ var('max_trip_distance_miles') }}, false)
                                                                          as fails_distance_literal,
        not coalesce(fare_amount > 0, false)                              as fails_fare_literal,
        not coalesce(
            pu_zone_id between {{ var('zone_id_min') }} and {{ var('zone_id_max') }}, false)
                                                                          as fails_pu_zone,
        -- Record-format exemptions (DECISIONS.md, Phase 1; results/record_format_probe.csv): a
        -- meter field that the recording channel structurally does not populate is not tested.
        --   Flex Fare trips (upfront price): fare_amount and the distance lower bound;
        --   identical pickup/dropoff timestamps with a positive distance (missing dropoff
        --   time, vendor 7 from 2024-12): the duration rule.
        coalesce(payment_type = {{ var('flex_fare_payment_type') }}, false) as exempt_fare,
        coalesce(payment_type = {{ var('flex_fare_payment_type') }}
                 and coalesce(trip_distance, 0) <= 0, false)              as exempt_distance,
        coalesce(dropoff_ts = pickup_ts and trip_distance > 0
                 and trip_distance <= {{ var('max_trip_distance_miles') }}, false)
                                                                          as exempt_duration
    from dedup
),
rules as (
    select
        *,
        fails_duration_literal and not exempt_duration                    as fails_duration,
        fails_distance_literal and not exempt_distance                    as fails_distance,
        fails_fare_literal and not exempt_fare                            as fails_fare
    from flags
)
select
    *,
    case
        when fails_pickup_window then 'pickup_window'
        when fails_duration      then 'duration'
        when fails_distance      then 'distance'
        when fails_fare          then 'fare'
        when fails_pu_zone       then 'pu_zone'
    end                                                                   as drop_reason,
    -- valid only thanks to an exemption: PLAN's literal rules would drop it
    not (fails_pickup_window or fails_duration or fails_distance or fails_fare or fails_pu_zone)
    and (fails_duration_literal or fails_distance_literal or fails_fare_literal)
                                                                          as is_format_exempt
from rules
{% endmacro %}

{% macro insert_remaining_files(relation) %}
  {%- if execute -%}
    {%- for f in yellow_files()[1:] -%}
      {%- do run_query("insert into " ~ relation ~ " " ~ trips_flagged_select(f)) -%}
    {%- endfor -%}
  {%- endif -%}
  select 1
{% endmacro %}
