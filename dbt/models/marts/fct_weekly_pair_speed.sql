-- Speed / duration panel (Amendment 2, B1-B3): pickup zone x dropoff zone x panel week x
-- pickup-hour band x distance tercile, for trips within Manhattan (int_speed_trips). Sums over the
-- trips used (exclusion IS NULL) so means can be formed at any coarser grain (mean trip speed =
-- sum_speed_mph / n_used), plus the count of every exclusion reason (B3: excluded share by month
-- and group). Distance terciles: int_speed_terciles; 'unknown' = no metered distance.
{{ config(materialized='table') }}
{%- set bands = var('hour_bands') %}
with t as (
    select
        s.*,
        case
            {%- for lo, hi in bands %}
            when hour(s.pu_hour) >= {{ lo }} and hour(s.pu_hour) < {{ hi }} then '{{ "h%02d_%02d" % (lo, hi) }}'
            {%- endfor %}
        end                                                       as hour_band,
        case
            when not s.distance_known      then 'unknown'
            when s.trip_distance <= c.c1   then 't1'
            when s.trip_distance <= c.c2   then 't2'
            else 't3'
        end                                                       as dist_tercile
    from {{ ref('int_speed_trips') }} as s
    cross join {{ ref('int_speed_terciles') }} as c
)
select
    region,
    pu_zone_id,
    do_zone_id,
    week_start,
    {{ event_week('week_start') }}
                                                                  as event_week,
    hour_band,
    dist_tercile,
    count(*)::integer                                             as n_trips,
    {{ count_if("exclusion = 'duration'") }}::integer       as n_excl_duration,
    {{ count_if("exclusion = 'distance'") }}::integer       as n_excl_distance,
    {{ count_if("exclusion = 'speed'") }}::integer          as n_excl_speed,
    {{ count_if("exclusion is null") }}::integer            as n_used,
    {{ agg_if('sum', 'duration_min', "exclusion is null") }}            as sum_duration_min,
    {{ agg_if('sum', 'trip_distance', "exclusion is null") }}           as sum_distance_mi,
    {{ agg_if('sum', 'speed_mph', "exclusion is null") }}               as sum_speed_mph,
    {{ count_if("exclusion is null and fare_amount > 0") }}::integer as n_fare,
    {{ agg_if('sum', 'fare_amount', "exclusion is null and fare_amount > 0") }}  as sum_fare,
    {{ agg_if('sum', 'duration_min', "exclusion is null and fare_amount > 0") }} as sum_duration_fare_min
from t
group by all
