-- Fails unless the hourly fact table counts exactly the valid trips minus the pickups that missed
-- the grid (no trip lost or double-counted by the grid join): an independent path, because
-- fct_hourly_zone_demand gets its counts from the join and int_grid_misses from the anti-join.
select *
from (select sum(pickups) as n from {{ ref('fct_hourly_zone_demand') }}) as a,
     (select count(*) as n from {{ ref('int_trips_valid') }}) as v,
     (select coalesce(sum(n), 0) as n from {{ ref('int_grid_misses') }} where kind = 'pickup') as m
where a.n <> v.n - m.n
