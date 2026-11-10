-- Per pickup zone x panel week: fares, congestion-fee revenue and fare-tercile counts of the valid
-- in-grid trips (same trip set as fct_weekly_zone_panel). Inputs of the A1 metric framework (mean
-- fare per trip, weekly fee revenue), the A3 trade-off table and the fare-tercile heterogeneity
-- (Amendment 2, B7). Fare terciles: int_fare_terciles; 'unknown' = no metered fare.
{{ config(materialized='table') }}
with t as (
    select
        v.pu_zone_id                                              as zone_id,
        {{ week_start('cast(v.pu_hour as date)') }}               as week_start,
        v.revenue_known,
        v.fare_amount,
        v.total_amount,
        coalesce(v.cbd_congestion_fee, 0)                         as cbd_fee,
        case
            when not v.revenue_known       then 'unknown'
            when v.fare_amount <= c.c1     then 't1'
            when v.fare_amount <= c.c2     then 't2'
            else 't3'
        end                                                       as fare_tercile
    from {{ ref('int_trips_valid') }} as v
    cross join {{ ref('int_fare_terciles') }} as c
    where v.pu_hour in (select hour_ts from {{ ref('int_hours') }})
)
select
    zone_id,
    week_start,
    datediff('day', {{ week_start("date '" ~ var('policy_date') ~ "'") }}, week_start) // 7
                                                                  as event_week,
    count(*)::integer                                             as n_trips,
    count(*) filter (where revenue_known)::integer                as n_revenue_known,
    sum(fare_amount) filter (where revenue_known)                 as sum_fare_amount,
    sum(total_amount) filter (where revenue_known)                as sum_total_amount,
    sum(cbd_fee)                                                  as sum_cbd_fee,
    count(*) filter (where cbd_fee > 0)::integer                  as n_cbd_fee_positive,
    count(*) filter (where fare_tercile = 't1')::integer          as pickups_fare_t1,
    count(*) filter (where fare_tercile = 't2')::integer          as pickups_fare_t2,
    count(*) filter (where fare_tercile = 't3')::integer          as pickups_fare_t3,
    count(*) filter (where fare_tercile = 'unknown')::integer     as pickups_fare_unknown
from t
group by zone_id, week_start
