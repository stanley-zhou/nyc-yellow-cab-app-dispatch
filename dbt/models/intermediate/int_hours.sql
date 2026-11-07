-- Every local wall-clock hour in the calendar span of the downloaded months (first day of the
-- first month 00:00 -> last hour of the last month). Generated in absolute time and converted to
-- local time: the repeated fall-back hour collapses under DISTINCT (merged by flooring); the
-- skipped spring-forward hour never appears (left absent by design, see DECISIONS.md).
{{ config(materialized='table') }}
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
