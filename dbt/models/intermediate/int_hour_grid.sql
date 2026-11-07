-- Every local hour in the calendar span of the downloaded months x every valid zone.
-- The hour series is generated in absolute time and converted to local wall-clock time:
-- the repeated fall-back hour collapses under DISTINCT (merged by flooring); the skipped
-- spring-forward hour never appears (left absent by design, see DECISIONS.md).
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
),
hours as (
    select distinct timezone('{{ var("timezone") }}', t.abs_ts) as hour_ts
    from bounds, generate_series(bounds.lo, bounds.hi - interval 1 hour, interval 1 hour) as t(abs_ts)
)
select z.zone_id, h.hour_ts
from {{ ref('stg_zones') }} as z
cross join hours as h
