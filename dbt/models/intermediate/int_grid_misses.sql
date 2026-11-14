-- Valid trips whose floored pickup or dropoff hour is not an hour of the grid, by source month,
-- kind and hour (counted in results/data_quality.json; PLAN amendment, Phase 1 item 5):
--   edge_straggler     : the hour lies outside the downloaded calendar span (straggler rows of
--                        the first/last file);
--   spring_forward_gap : the hour is inside the span but is the non-existent local 02:00 hour of
--                        a spring-forward day (TLC stamps are naive local time).
-- Trips are first counted per (source_month, hour), then anti-joined to int_hours, so the
-- 341M-row trip table is never joined row by row.
{{ config(materialized='table') }}
with span as (select min(hour_ts) as lo, max(hour_ts) as hi from {{ ref('int_hours') }}),
by_hour as (
    select source_month, 'pickup' as kind, pu_hour as hour, count(*) as n
    from {{ ref('int_trips_valid') }} group by 1, 2, 3
    union all
    select source_month, 'dropoff' as kind, do_hour as hour, count(*) as n
    from {{ ref('int_trips_valid') }} group by 1, 2, 3
)
select
    b.source_month,
    b.kind,
    b.hour,
    b.n,
    case when b.hour < span.lo or b.hour > span.hi then 'edge_straggler'
         else 'spring_forward_gap' end as reason
from by_hour as b
cross join span
{%- if target.type == 'snowflake' %}
where not exists (select 1 from {{ ref('int_hours') }} as h where h.hour_ts = b.hour)
{%- else %}
anti join {{ ref('int_hours') }} as h on h.hour_ts = b.hour
{%- endif %}
