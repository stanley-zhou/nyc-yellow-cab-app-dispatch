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
    pu_zone_id,
    do_zone_id,
    week_start,
    datediff('day', {{ week_start("date '" ~ var('policy_date') ~ "'") }}, week_start) // 7
                                                                  as event_week,
    hour_band,
    dist_tercile,
    count(*)::integer                                             as n_trips,
    count(*) filter (where exclusion = 'duration')::integer       as n_excl_duration,
    count(*) filter (where exclusion = 'distance')::integer       as n_excl_distance,
    count(*) filter (where exclusion = 'speed')::integer          as n_excl_speed,
    count(*) filter (where exclusion is null)::integer            as n_used,
    sum(duration_min) filter (where exclusion is null)            as sum_duration_min,
    sum(trip_distance) filter (where exclusion is null)           as sum_distance_mi,
    sum(speed_mph) filter (where exclusion is null)               as sum_speed_mph,
    count(*) filter (where exclusion is null and fare_amount > 0)::integer as n_fare,
    sum(fare_amount) filter (where exclusion is null and fare_amount > 0)  as sum_fare,
    sum(duration_min) filter (where exclusion is null and fare_amount > 0) as sum_duration_fare_min
from t
group by all
