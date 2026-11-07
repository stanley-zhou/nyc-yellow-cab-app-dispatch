-- One row per (zone_id, hour_ts): the complete grid with explicit zeros.
with pu as (
    select
        pu_zone_id                                   as zone_id,
        date_trunc('hour', pickup_ts)                as hour_ts,
        count(*)                                     as pickups,
        sum(total_amount)                            as revenue,
        avg(trip_distance)                           as mean_distance,
        count(*) filter (where cbd_congestion_fee > 0) as n_cbd_fee_trips
    from {{ ref('int_trips_valid') }}
    group by all
),
dropoffs as (
    select
        do_zone_id                                   as zone_id,
        date_trunc('hour', dropoff_ts)               as hour_ts,
        count(*)                                     as dropoffs
    from {{ ref('int_trips_valid') }}
    group by all
)
select
    g.zone_id,
    g.hour_ts,
    coalesce(pu.pickups, 0)::integer                 as pickups,
    coalesce(d.dropoffs, 0)::integer                 as dropoffs,
    coalesce(pu.revenue, 0)::double                  as revenue,
    pu.mean_distance                                 as mean_distance,
    coalesce(pu.n_cbd_fee_trips, 0)::integer         as n_cbd_fee_trips
from {{ ref('int_hour_grid') }} as g
left join pu       on pu.zone_id = g.zone_id and pu.hour_ts = g.hour_ts
left join dropoffs as d on d.zone_id = g.zone_id and d.hour_ts = g.hour_ts
