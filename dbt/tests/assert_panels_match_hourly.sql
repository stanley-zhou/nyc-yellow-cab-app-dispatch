-- Fails if the daily/weekly panels do not add up to the hourly fact table, or if a panel's splits
-- do not add up to its total (hour bands, distance terciles, dropoff in/out of CBD, weekday/end).
{%- set bands = [] %}
{%- for lo, hi in var('hour_bands') %}{% do bands.append('pickups_h%02d_%02d' % (lo, hi)) %}{% endfor %}
with h as (select sum(pickups) as n from {{ ref('fct_hourly_zone_demand') }}),
d as (select sum(pickups) as n from {{ ref('fct_daily_zone_panel') }}),
w as (select sum(pickups) as n from {{ ref('fct_weekly_zone_panel') }}),
bad_daily as (
    select count(*) as n from {{ ref('fct_daily_zone_panel') }}
    where pickups <> {{ bands | join(' + ') }}
       or pickups <> pickups_dist_t1 + pickups_dist_t2 + pickups_dist_t3
       or pickups <> pickups_do_cbd + pickups_do_non_cbd
),
bad_weekly as (
    select count(*) as n from {{ ref('fct_weekly_zone_panel') }}
    where pickups <> pickups_weekday + pickups_weekend
       or pickups <> {{ bands | join(' + ') }}
)
select h.n as hourly, d.n as daily, w.n as weekly, bad_daily.n as bad_daily, bad_weekly.n as bad_weekly
from h, d, w, bad_daily, bad_weekly
where h.n <> d.n or h.n <> w.n or bad_daily.n > 0 or bad_weekly.n > 0
