-- Zone x local-date panel (complete: every valid zone x every date of the grid, zeros explicit),
-- the zone_day variant of fct_weekly_zone_panel. Daily weather controls are city-wide.
{%- set split_cols = [] %}
{%- for lo, hi in var('hour_bands') %}{% do split_cols.append('pickups_h%02d_%02d' % (lo, hi)) %}{% endfor %}
{%- do split_cols.extend(['pickups_dist_t1', 'pickups_dist_t2', 'pickups_dist_t3', 'pickups_dist_unknown',
                          'pickups_do_cbd', 'pickups_do_non_cbd', 'pickups_format_exempt']) %}
with dates as (
    select cast(hour_ts as date) as date, count(*) as n_hours
    from {{ ref('int_hours') }}
    group by 1
),
wx as (
    select cast(hour_ts as date) as date, avg(temp_f) as mean_temp_f, sum(precip_in) as total_precip_in
    from {{ ref('stg_weather') }}
    group by 1
)
select
    z.zone_id,
    d.date,
    {{ week_start('d.date') }}                                    as week_start,
    {{ iso_dow('d.date') }} >= 6                                           as is_weekend,
    d.n_hours,
    coalesce(t.pickups, 0)::integer                               as pickups,
    {%- for c in split_cols %}
    coalesce(t.{{ c }}, 0)::integer                               as {{ c }},
    {%- endfor %}
    wx.mean_temp_f,
    wx.total_precip_in
from {{ ref('stg_zones') }} as z
cross join dates as d
left join {{ ref('int_zone_day_trips') }} as t on t.zone_id = z.zone_id and t.date = d.date
left join wx on wx.date = d.date
