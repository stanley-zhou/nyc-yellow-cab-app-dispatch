-- Zone x week panel for the causal work (PLAN Phase 1 / Phase 4), summed from the complete daily
-- panel. Weeks start on var('week_start') (Sunday: the policy date 2025-01-05 is the first day of
-- event week 0). `n_days` < 7 marks the partial edge weeks of the download span; Phase 4 must
-- drop them. Weekday/weekend splits count pickups on Mon-Fri vs Sat-Sun dates.
{%- set split_cols = [] %}
{%- for lo, hi in var('hour_bands') %}{% do split_cols.append('pickups_h%02d_%02d' % (lo, hi)) %}{% endfor %}
{%- do split_cols.extend(['pickups_dist_t1', 'pickups_dist_t2', 'pickups_dist_t3',
                          'pickups_do_cbd', 'pickups_do_non_cbd', 'pickups_format_exempt']) %}
{{ config(materialized='table') }}
select
    zone_id,
    week_start,
    datediff('day', {{ week_start("date '" ~ var('policy_date') ~ "'") }}, week_start) // 7
                                                                  as event_week,
    count(*)                                                      as n_days,
    sum(n_hours)                                                  as n_hours,
    sum(pickups)                                                  as pickups,
    {%- for c in split_cols %}
    sum({{ c }})                                                  as {{ c }},
    {%- endfor %}
    coalesce(sum(pickups) filter (where not is_weekend), 0)       as pickups_weekday,
    coalesce(sum(pickups) filter (where is_weekend), 0)           as pickups_weekend,
    avg(mean_temp_f)                                              as mean_temp_f,  -- mean of daily means
    sum(total_precip_in)                                          as total_precip_in
from {{ ref('fct_daily_zone_panel') }}
group by zone_id, week_start
