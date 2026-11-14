-- Leakage-safe feature table at the (zone_id, hour_ts) grain of fct_hourly_zone_demand.
--
-- Every demand feature looks back at least 24 hours: for a target hour on day D the newest input
-- is day D-1, which is complete at the 00:00 forecast origin of day D. Nothing shorter than a
-- 24-hour lag exists in this table by design (PLAN Phase 1 / Phase 2).
--
-- Lags are wall-clock: `lag_k` = the same local hour k/24 calendar days earlier, computed with
-- RANGE window frames over (zone, local hour of day) ordered by date. They therefore stay aligned
-- with the daily pattern across DST transitions. A lag whose source hour does not exist (the
-- spring-forward 02:00 hour) is NULL. Rolling means average the source hours that exist in the
-- window and are NULL while the window reaches back before the first day of the panel.
--
-- Weather is the observed hourly value at the target hour (city-wide point; PLAN limitation:
-- actual weather is used as if it were known in advance).
{{ config(materialized='table') }}
with base as (
    select
        zone_id,
        hour_ts,
        pickups,
        cast(hour_ts as date)                  as date,
        hour(hour_ts)                          as hour
    from {{ ref('fct_hourly_zone_demand') }}
),
first_day as (select min(date) as d0 from base),
daily as (
    select zone_id, date, avg(pickups) as mean_day
    from base
    group by all
),
daily_lag as (
    select
        zone_id,
        date,
        max(mean_day) over (partition by zone_id order by date
            {{ days_back(1, 1) }}) as mean_prev_day
    from daily
),
lags as (
    select
        b.*,
        max(pickups) over (partition by zone_id, hour order by date
            {{ days_back(1, 1) }})   as lag_24,
        max(pickups) over (partition by zone_id, hour order by date
            {{ days_back(2, 2) }})   as lag_48,
        max(pickups) over (partition by zone_id, hour order by date
            {{ days_back(7, 7) }})   as lag_168,
        max(pickups) over (partition by zone_id, hour order by date
            {{ days_back(14, 14) }}) as lag_336,
        avg(pickups) over (partition by zone_id, hour order by date
            {{ days_back(7, 1) }})   as m7,
        avg(pickups) over (partition by zone_id, hour order by date
            {{ days_back(28, 1) }})  as m28
    from base as b
)
select
    l.zone_id,
    l.hour_ts,
    l.pickups,
    -- calendar
    l.hour,
    {{ iso_dow('l.hour_ts') }} - 1                                         as dow,       -- 0 = Monday
    day(l.hour_ts)                                                as dom,
    month(l.hour_ts)                                              as month,
    year(l.hour_ts)                                               as year,
    {{ iso_dow('l.hour_ts') }} >= 6                                        as is_weekend,
    hol.date is not null                                          as is_holiday,
    -- weather (observed, city-wide)
    w.temp_f, w.apparent_temp_f, w.precip_in, w.rain_in, w.snowfall_in, w.weather_code,
    w.cloud_cover_pct, w.wind_mph, w.rel_humidity_pct,
    -- demand history, all >= 24 h old
    l.lag_24,
    l.lag_48,
    l.lag_168,
    l.lag_336,
    case when l.date >= {{ plus_days('fd.d0', 7) }}  then l.m7  end    as mean_same_hour_prev_7d,
    case when l.date >= {{ plus_days('fd.d0', 28) }} then l.m28 end    as mean_same_hour_prev_28d,
    dl.mean_prev_day
from lags as l
cross join first_day as fd
left join daily_lag as dl on dl.zone_id = l.zone_id and dl.date = l.date
left join {{ ref('stg_weather') }} as w on w.hour_ts = l.hour_ts
left join (select distinct date from {{ ref('holidays_ny') }}) as hol on hol.date = l.date
