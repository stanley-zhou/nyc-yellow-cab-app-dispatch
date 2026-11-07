-- Unix hours offered by more than one weather file, and whether the files disagree on any value.
-- Informational (the pipeline keeps one file per hour, int_weather_selected); summarised in
-- results/data_quality.json so an Open-Meteo revision between downloads would be visible.
select
    unix_time,
    count(*)                                                        as n_files,
    count(distinct {
        't': temperature_2m, 'at': apparent_temperature, 'p': precipitation, 'r': rain,
        's': snowfall, 'wc': weathercode, 'cc': cloudcover, 'w': windspeed_10m,
        'rh': relativehumidity_2m})                                 as n_distinct_versions
from {{ source('raw', 'weather') }}
group by unix_time
having count(*) > 1
