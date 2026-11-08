-- Fails for every zone-week where the vendor split does not add up to fct_weekly_zone_panel
-- (pickups and format-exempt pickups), or where a vendor row exists for a zone-week missing from
-- the complete weekly panel.
with v as (
    select zone_id, week_start, sum(pickups) as pickups,
           sum(pickups_format_exempt) as pickups_format_exempt
    from {{ ref('fct_weekly_zone_vendor') }}
    group by all
)
select w.zone_id, w.week_start, w.pickups, v.pickups as vendor_sum,
       w.pickups_format_exempt, v.pickups_format_exempt as vendor_sum_format_exempt
from {{ ref('fct_weekly_zone_panel') }} as w
full outer join v using (zone_id, week_start)
where w.zone_id is null
   or coalesce(v.pickups, 0) <> w.pickups
   or coalesce(v.pickups_format_exempt, 0) <> w.pickups_format_exempt
