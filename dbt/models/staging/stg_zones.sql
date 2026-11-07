-- TLC zone lookup restricted to valid zone ids (264 = Unknown, 265 = Outside NYC are dropped).
-- `is_cbd` is added in dim_zones (Phase 1) from config/zones_cbd.csv.
select
    cast(LocationID as integer)                      as zone_id,
    Zone                                             as zone_name,
    Borough                                          as borough,
    service_zone,
    service_zone in ('Airports', 'EWR')              as is_airport
from {{ source('raw', 'zone_lookup') }}
where cast(LocationID as integer) between {{ var('zone_id_min') }} and {{ var('zone_id_max') }}
