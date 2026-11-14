-- Distance tercile cut points of the speed sample (Amendment 2, B3: "fixed on 2024 quantiles"):
-- used within-Manhattan trips (region 'manhattan') picked up in var('speed_tercile_period') (the 52-week pre-period),
-- so a post-policy shift in trip lengths cannot move the bins.
{{ config(materialized='table') }}
{%- set p = var('speed_tercile_period') %}
select
    {{ quantile_cont('trip_distance', '1.0', 3) }} as c1,
    {{ quantile_cont('trip_distance', '2.0', 3) }} as c2,
    count(*)                              as n_trips
from {{ ref('int_speed_trips') }}
where exclusion is null
  and region = 'manhattan'                 -- within-Manhattan trips only (C4 keeps the cuts)
  and pu_hour >= date '{{ p[0] }}'
  and pu_hour <  {{ plus_days("date '" ~ p[1] ~ "'", 1) }}
