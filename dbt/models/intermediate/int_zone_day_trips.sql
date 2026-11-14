-- Valid in-grid pickups per (pickup zone, local date) with the splits PLAN Phase 1 asks for:
-- hour band, distance tercile (fixed cut points), dropoff in CBD. Weekday/weekend is a property of
-- the date and is added in the panels.
{{ config(materialized='table') }}
with t as (
    select
        g.pu_zone_id                                       as zone_id,
        cast(g.pu_hour as date)                            as date,
        hour(g.pu_hour)                                    as hr,
        g.trip_distance,
        dz.is_cbd                                          as do_is_cbd,
        g.is_format_exempt
    from {{ ref('int_trips_valid') }} as g
    left join {{ ref('dim_zones') }} as dz on dz.zone_id = g.do_zone_id
    where g.pu_hour in (select hour_ts from {{ ref('int_hours') }})
)
select
    t.zone_id,
    t.date,
    count(*)                                                                as pickups,
    {%- for lo, hi in var('hour_bands') %}
    {{ count_if("t.hr >= " ~ lo ~ " and t.hr < " ~ hi) }}            as pickups_h{{ '%02d' % lo }}_{{ '%02d' % hi }},
    {%- endfor %}
    {{ count_if("t.trip_distance > 0 and t.trip_distance <= c.c1") }} as pickups_dist_t1,
    {{ count_if("t.trip_distance > c.c1 and t.trip_distance <= c.c2") }} as pickups_dist_t2,
    {{ count_if("t.trip_distance > c.c2") }}                          as pickups_dist_t3,
    {{ count_if("not coalesce(t.trip_distance > 0, false)") }}        as pickups_dist_unknown,
    {{ count_if("t.do_is_cbd") }}                                     as pickups_do_cbd,
    -- dropoff outside the CBD, including dropoff ids 264/265 (unknown / outside NYC)
    {{ count_if("not coalesce(t.do_is_cbd, false)") }}                as pickups_do_non_cbd,
    {{ count_if("t.is_format_exempt") }}                           as pickups_format_exempt
from t
cross join {{ ref('int_distance_terciles') }} as c
group by all
