-- Fails for every zone-week inside the channel window where the channel split does not add up to
-- fct_weekly_zone_panel, or where a channel row exists for a zone-week missing from the panel.
-- Only weeks whose 7 days lie inside channel_window are compared.
with c as (
    select zone_id, week_start, sum(pickups) as pickups
    from {{ ref('fct_weekly_zone_channel') }}
    group by all
),
w as (
    select zone_id, week_start, pickups
    from {{ ref('fct_weekly_zone_panel') }}
    where week_start >= date '{{ var("channel_window")[0] }}'
      and week_start + 6 <= date '{{ var("channel_window")[1] }}'
)
select w.zone_id, w.week_start, w.pickups, c.pickups as channel_sum
from w
full outer join (select * from c
                 where week_start >= date '{{ var("channel_window")[0] }}'
                   and week_start + 6 <= date '{{ var("channel_window")[1] }}') as c
    using (zone_id, week_start)
where w.zone_id is null or coalesce(c.pickups, 0) <> w.pickups
