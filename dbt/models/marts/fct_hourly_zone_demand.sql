-- One row per (zone_id, hour_ts): the complete grid with explicit zeros.
-- Pickups/revenue/distance/fee trips are attributed to the pickup zone and floored pickup hour;
-- dropoffs to the dropoff zone and floored dropoff hour. The LEFT JOIN from the grid keeps only
-- grid hours; valid trips in other hours are counted in int_grid_misses.
select
    g.zone_id,
    g.hour_ts,
    coalesce(pu.pickups, 0)::integer                   as pickups,
    coalesce(d.dropoffs, 0)::integer                   as dropoffs,
    coalesce(pu.revenue, 0)::double                    as revenue,
    pu.mean_distance                                   as mean_distance,
    coalesce(pu.n_cbd_fee_trips, 0)::integer           as n_cbd_fee_trips,
    -- pickups kept only by a record-format exemption (int_trips_flagged); PLAN's literal rules
    -- would drop them: pickups - n_format_exempt = PLAN-literal count, for robustness checks
    coalesce(pu.n_format_exempt, 0)::integer        as n_format_exempt
from {{ ref('int_hour_grid') }} as g
left join {{ ref('int_hourly_pickups') }}  as pu on pu.zone_id = g.zone_id and pu.hour_ts = g.hour_ts
left join {{ ref('int_hourly_dropoffs') }} as d  on d.zone_id = g.zone_id and d.hour_ts = g.hour_ts
