-- Fixed fare tercile cut points (Amendment 2, B7 demand heterogeneity): fare_amount of valid
-- in-grid trips with a metered fare, picked up in var('distance_tercile_period') (the 52-week
-- pre-period), like the distance terciles.
{{ config(materialized='table') }}
{%- set p = var('distance_tercile_period') %}
select
    quantile_cont(fare_amount, 1.0 / 3) as c1,
    quantile_cont(fare_amount, 2.0 / 3) as c2,
    count(*)                            as n_trips
from {{ ref('int_trips_valid') }}
where pu_hour in (select hour_ts from {{ ref('int_hours') }})
  and revenue_known
  and pickup_ts >= date '{{ p[0] }}'
  and pickup_ts <  date '{{ p[1] }}' + interval 1 day
