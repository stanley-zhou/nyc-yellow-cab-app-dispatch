-- Every local hour of int_hours x every valid zone (complete panel skeleton).
select z.zone_id, h.hour_ts
from {{ ref('stg_zones') }} as z
cross join {{ ref('int_hours') }} as h
