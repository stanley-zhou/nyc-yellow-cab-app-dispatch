-- Fails if any local hour of the demand grid has no weather row (would catch timezone shifts
-- and gaps in the Open-Meteo download).
select g.hour_ts
from (select distinct hour_ts from {{ ref('int_hour_grid') }}) as g
left join {{ ref('stg_weather') }} as w using (hour_ts)
where w.hour_ts is null
