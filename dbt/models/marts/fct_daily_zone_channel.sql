-- Valid in-grid pickups per (pickup zone, local day, VendorID, channel, platform, trip type):
-- sparse long table (Amendment 4 D1; channel definition Amendment 4a, D0 ruling option c).
--   channel  : 'app' = any e-hail app, 'street' = street hail. Label: Flex Fare (payment_type =
--              flex_fare_payment_type) in files before request_source_from; request_source not
--              NULL from those files on (cut-over by source file month, so a straggler keeps the
--              label of the file that carries it). D0: the two labels agree at 0.9997-1.000.
--   platform : 'street'; 'app' before the request_source files (platform unknown); from them the
--              e-hail origin (uber, lyft, curb_app, arro, code_a, code_cc; other codes 'other').
--   trip_type: within (both ends in the CBD), into, out_of, neither — by the 60th St rule
--              (dim_zones.is_cbd); an unknown dropoff zone counts as outside the CBD.
--   is_cmt_outer_block: VendorID 1 street hails picked up in the 'other' zone group, the block
--              that vanishes at 2026-05-31 (DECISIONS, D0; Amendment 4a: its own series).
-- Same trip set as fct_weekly_zone_panel inside channel_window (dbt test
-- assert_channel_matches_weekly).
{{ config(materialized='table') }}
with t as (
    select
        v.pu_zone_id                                                      as zone_id,
        cast(v.pu_hour as date)                                           as day,
        v.vendor_id,
        case when v.source_month >= date '{{ var("request_source_from") }}'
             then v.request_source is not null
             else coalesce(v.payment_type = {{ var('flex_fare_payment_type') }}, false)
        end                                                               as is_app,
        v.request_source,
        v.source_month >= date '{{ var("request_source_from") }}'         as has_request_source,
        coalesce(pz.is_cbd, false)                                        as pu_cbd,
        coalesce(dz.is_cbd, false)                                        as do_cbd,
        pz.zone_group
    from {{ ref('int_trips_valid') }} as v
    left join {{ ref('dim_zones') }} as pz on pz.zone_id = v.pu_zone_id
    left join {{ ref('dim_zones') }} as dz on dz.zone_id = v.do_zone_id
    where v.pu_hour in (select hour_ts from {{ ref('int_hours') }})
      and cast(v.pu_hour as date) between date '{{ var("channel_window")[0] }}'
                                      and date '{{ var("channel_window")[1] }}'
)
select
    zone_id,
    day,
    {{ week_start('day') }}                                               as week_start,
    vendor_id,
    case when is_app then 'app' else 'street' end                         as channel,
    case when not is_app then 'street'
         when not has_request_source then 'app'
    {%- for code, name in var('request_source_platforms').items() %}
         when request_source = '{{ code }}' then '{{ name }}'
    {%- endfor %}
         else 'other' end                                                 as platform,
    case when pu_cbd and do_cbd then 'within'
         when do_cbd then 'into'
         when pu_cbd then 'out_of'
         else 'neither' end                                               as trip_type,
    zone_group,
    coalesce(vendor_id = 1 and zone_group = 'other' and not is_app, false) as is_cmt_outer_block,
    count(*)::integer                                                     as pickups
from t
group by all
