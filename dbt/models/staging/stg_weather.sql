-- Hourly weather on local wall-clock hours. Open-Meteo returns GMT unix seconds (DECISIONS.md:
-- the API's America/New_York mode applies a fixed EST offset); int_weather_selected keeps one
-- source file per unix hour. The repeated fall-back local hour receives two different physical
-- hours and is merged by flooring: mean of the two readings, max weather code (the same rule as
-- the demand grid). No averaging across files happens here.
with local as (
    select
        date_trunc('hour', {{ local_from_unix('unix_time') }}) as hour_ts,
        *
    from {{ ref('int_weather_selected') }}
)
select
    hour_ts,
    avg(temperature_2m)       as temp_f,
    avg(apparent_temperature) as apparent_temp_f,
    avg(precipitation)        as precip_in,
    avg(rain)                 as rain_in,
    avg(snowfall)             as snowfall_in,
    max(weathercode)          as weather_code,
    {{ avg_double('cloudcover') }}           as cloud_cover_pct,
    avg(windspeed_10m)        as wind_mph,
    {{ avg_double('relativehumidity_2m') }}  as rel_humidity_pct,
    count(*)                  as n_source_hours
from local
group by hour_ts
