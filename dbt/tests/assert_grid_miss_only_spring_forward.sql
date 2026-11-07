-- Fails if a valid trip inside the download span misses the hour grid for any reason other than
-- the non-existent local 02:00 hour of a US spring-forward day (second Sunday of March).
select kind, hour, n
from {{ ref('int_grid_misses') }}
where reason = 'spring_forward_gap'
  and not (hour(hour) = 2 and month(hour) = 3 and dayofweek(hour) = 0
           and day(hour) between 8 and 14)
