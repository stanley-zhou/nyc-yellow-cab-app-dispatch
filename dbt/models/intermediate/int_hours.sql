-- Every local wall-clock hour in the calendar span of the downloaded months (first day of the
-- first month 00:00 -> last hour of the last month). Generated in absolute time and converted to
-- local time: the repeated fall-back hour collapses under DISTINCT (merged by flooring); the
-- skipped spring-forward hour never appears (left absent by design, see DECISIONS.md).
{{ config(materialized='table') }}
{%- if target.type == 'snowflake' %}
{#- E3: the loaded months replace the raw-file glob; same rule: every local hour from the first
    month start to the last month end, built on absolute (UTC) hours and converted back #}
with bounds as (
    select
        convert_timezone('{{ var("timezone") }}', 'UTC', min(source_month)::timestamp_ntz)  as lo,
        convert_timezone('{{ var("timezone") }}', 'UTC',
                         {{ plus_months('max(source_month)', 1) }}::timestamp_ntz)       as hi
    from (select distinct source_month from {{ source('raw', 'yellow_trips_valid') }})
),
steps as (
    select row_number() over (order by seq4()) - 1 as i
    from table(generator(rowcount => 200000))                -- 22.8 years of hours
)
select distinct convert_timezone('UTC', '{{ var("timezone") }}', dateadd(hour, s.i, b.lo)) as hour_ts
from bounds as b
join steps as s on dateadd(hour, s.i, b.lo) < b.hi
{%- else %}
with files as (
    select strptime(regexp_extract(file, 'yellow_tripdata_(\d{4}-\d{2})\.parquet', 1), '%Y-%m')
           as month_start
    from glob('{{ var("yellow_glob") }}')
),
bounds as (
    select
        timezone('{{ var("timezone") }}', min(month_start))                      as lo,
        timezone('{{ var("timezone") }}', max(month_start) + interval 1 month)   as hi
    from files
)
select distinct timezone('{{ var("timezone") }}', t.abs_ts) as hour_ts
from bounds, generate_series(bounds.lo, bounds.hi - interval 1 hour, interval 1 hour) as t(abs_ts)
{%- endif %}
