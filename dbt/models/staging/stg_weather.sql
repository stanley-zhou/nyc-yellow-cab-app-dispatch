-- Open-Meteo returns unix seconds; convert to local wall-clock time. The repeated fall-back
-- hour is merged by flooring (mean of the two readings; max weather code). Overlapping files
-- (e.g. a smoke chunk plus a full-year chunk) contain identical rows and are de-duplicated.
with raw as (
    select distinct * from {{ source('raw', 'weather') }}
),
local as (
    select
        date_trunc('hour', timezone('{{ var("timezone") }}', to_timestamp(unix_time))) as hour_ts,
        *
    from raw
)
select
    hour_ts,
    avg(temperature_2m)       as temp_f,
    avg(apparent_temperature) as apparent_temp_f,
    avg(precipitation)        as precip_in,
    avg(rain)                 as rain_in,
    avg(snowfall)             as snowfall_in,
    max(weathercode)          as weather_code,
    avg(cloudcover)           as cloud_cover_pct,
    avg(windspeed_10m)        as wind_mph,
    avg(relativehumidity_2m)  as rel_humidity_pct
from local
group by hour_ts
