-- Zone dimension: TLC lookup + the CBD mapping in config/zones_cbd.csv (written by
-- scripts/03a_cbd_map.py from the geometric rule and the fee-based validation; see DECISIONS.md).
select
    z.zone_id,
    z.zone_name,
    z.borough,
    z.service_zone,
    cast(c.is_cbd as boolean)                     as is_cbd,       -- NULL = unmapped (tested)
    z.is_airport,
    coalesce(cast(c.geometry_available as boolean), false) as geometry_available,
    case
        when c.is_cbd                             then 'cbd'
        when z.borough = 'Manhattan'              then 'manhattan_non_cbd'
        when z.is_airport                         then 'airports'
        else 'other'
    end                                           as zone_group,
    c.is_cbd is not null                          as in_cbd_mapping
from {{ ref('stg_zones') }} as z
left join {{ source('raw', 'zones_cbd') }} as c on cast(c.zone_id as integer) = z.zone_id
