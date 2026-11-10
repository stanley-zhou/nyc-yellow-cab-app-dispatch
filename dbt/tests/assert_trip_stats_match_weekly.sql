-- Fails for every zone-week where fct_weekly_zone_trip_stats counts a different number of trips
-- than fct_weekly_zone_panel (both are the valid in-grid trips by pickup zone and week).
select w.zone_id, w.week_start, w.pickups, s.n_trips
from {{ ref('fct_weekly_zone_panel') }} as w
full outer join {{ ref('fct_weekly_zone_trip_stats') }} as s using (zone_id, week_start)
where w.zone_id is null
   or coalesce(s.n_trips, 0) <> w.pickups
