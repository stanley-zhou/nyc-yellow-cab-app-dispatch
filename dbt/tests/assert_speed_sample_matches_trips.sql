-- Fails if the speed panel loses or gains trips: per week, its trip count must equal the
-- within-Manhattan valid in-grid trips of int_speed_trips.
with a as (select week_start, sum(n_trips) as n from {{ ref('fct_weekly_pair_speed') }} group by 1),
     b as (select week_start, count(*) as n from {{ ref('int_speed_trips') }} group by 1)
select coalesce(a.week_start, b.week_start) as week_start, a.n as panel, b.n as trips
from a full outer join b using (week_start)
where coalesce(a.n, -1) <> coalesce(b.n, -1)
