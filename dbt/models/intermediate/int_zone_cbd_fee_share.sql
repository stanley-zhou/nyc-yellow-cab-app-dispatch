-- Fee-based CBD validation input (PLAN Phase 1, is_cbd step b): per pickup zone, valid trips
-- picked up in var('cbd_fee_window') and how many carry cbd_congestion_fee > 0. The fee applies to
-- trips that start, end or pass through the zone, so zones just outside the CBD can show a high
-- share from trips INTO the CBD; the intra-zone share (pickup zone = dropoff zone) is the sharper
-- supplementary signal used only to explain ambiguous zones (scripts/03a_cbd_map.py).
{{ config(materialized='table') }}
{%- set w = var('cbd_fee_window') %}
select
    pu_zone_id                                                           as zone_id,
    count(*)                                                             as n_trips,
    count(*) filter (where cbd_congestion_fee > 0)                       as n_fee_pos,
    count(*) filter (where cbd_congestion_fee is null)                   as n_fee_null,
    count(*) filter (where do_zone_id = pu_zone_id)                      as n_intra,
    count(*) filter (where do_zone_id = pu_zone_id and cbd_congestion_fee > 0) as n_intra_fee_pos
from {{ ref('int_trips_valid') }}
where pickup_ts >= date '{{ w[0] }}'
  and pickup_ts <  date '{{ w[1] }}' + interval 1 day
group by 1
