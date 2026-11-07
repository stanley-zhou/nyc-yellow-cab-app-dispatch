-- Per source file (month): raw rows, exact duplicates, rows dropped by each validity rule (first
-- failing rule, and each rule tested independently), valid rows, and valid trips that miss the
-- hour grid. scripts/03b_data_results.py turns this table into results/data_quality.json.
with f as (
    select
        source_month,
        sum(n_copies)::bigint                                          as raw_rows,
        sum(n_copies - 1)::bigint                                      as duplicate_rows,
        count(*)::bigint                                               as distinct_rows,
        count(*) filter (where drop_reason = 'pickup_window')          as drop_pickup_window,
        count(*) filter (where drop_reason = 'duration')               as drop_duration,
        count(*) filter (where drop_reason = 'distance')               as drop_distance,
        count(*) filter (where drop_reason = 'fare')                   as drop_fare,
        count(*) filter (where drop_reason = 'pu_zone')                as drop_pu_zone,
        count(*) filter (where fails_pickup_window)                    as flag_pickup_window,
        count(*) filter (where fails_duration)                         as flag_duration,
        count(*) filter (where fails_distance)                         as flag_distance,
        count(*) filter (where fails_fare)                             as flag_fare,
        count(*) filter (where fails_pu_zone)                          as flag_pu_zone,
        count(*) filter (where drop_reason is null)                    as valid_rows,
        count(*) filter (where drop_reason is null and is_format_exempt) as valid_format_exempt,
        count(*) filter (where drop_reason is null and fails_fare_literal)     as exempt_fare_used,
        count(*) filter (where drop_reason is null and fails_distance_literal) as exempt_distance_used,
        count(*) filter (where drop_reason is null and fails_duration_literal) as exempt_duration_used,
        count(*) filter (where fails_duration_literal)                 as flag_duration_literal,
        count(*) filter (where fails_distance_literal)                 as flag_distance_literal,
        count(*) filter (where fails_fare_literal)                     as flag_fare_literal,
        count(*) filter (where drop_reason is null and (
            pickup_ts < source_month or pickup_ts >= source_month + interval 1 month)) as valid_stragglers_kept
    from {{ ref('int_trips_flagged') }}
    group by source_month
),
g as (
    select
        source_month,
        coalesce(sum(n) filter (where kind = 'pickup'  and reason = 'edge_straggler'), 0)
                                                                       as pu_miss_edge_straggler,
        coalesce(sum(n) filter (where kind = 'pickup'  and reason = 'spring_forward_gap'), 0)
                                                                       as pu_miss_spring_forward,
        coalesce(sum(n) filter (where kind = 'dropoff' and reason = 'edge_straggler'), 0)
                                                                       as do_miss_edge_straggler,
        coalesce(sum(n) filter (where kind = 'dropoff' and reason = 'spring_forward_gap'), 0)
                                                                       as do_miss_spring_forward
    from {{ ref('int_grid_misses') }}
    group by source_month
)
select
    f.*,
    coalesce(g.pu_miss_edge_straggler, 0)::bigint                      as pu_miss_edge_straggler,
    coalesce(g.pu_miss_spring_forward, 0)::bigint                      as pu_miss_spring_forward,
    coalesce(g.do_miss_edge_straggler, 0)::bigint                      as do_miss_edge_straggler,
    coalesce(g.do_miss_spring_forward, 0)::bigint                      as do_miss_spring_forward,
    (f.valid_rows - coalesce(g.pu_miss_edge_straggler, 0)
                  - coalesce(g.pu_miss_spring_forward, 0))::bigint     as pickups_in_grid
from f
left join g using (source_month)
order by source_month
