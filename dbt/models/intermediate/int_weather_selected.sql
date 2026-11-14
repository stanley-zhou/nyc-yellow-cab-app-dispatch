-- Exactly ONE source file per absolute (unix) hour. Weather files overlap: yearly chunks are padded
-- by `weather_pad_days` on both sides, and the smoke chunk lies inside its year. Values from two
-- downloads are never averaged (PLAN amendment, Phase 1 item 2). Priority per unix hour:
--   1. a file whose core range (requested range minus the padding) contains the hour's UTC date;
--   2. the longer requested range (a full-year chunk beats the smoke chunk);
--   3. the later file name (deterministic tie-break).
-- `n_files` keeps the number of files offering the hour; results/data_quality.json reports how
-- many overlapping hours exist and how many differ in any value between files.
with raw as (
    select
        *,
        cast({{ regex_group('filename', 'open_meteo_(\d{4}-\d{2}-\d{2})_\d{4}-\d{2}-\d{2}\.csv') }}
             as date) as file_lo,
        cast({{ regex_group('filename', 'open_meteo_\d{4}-\d{2}-\d{2}_(\d{4}-\d{2}-\d{2})\.csv') }}
             as date) as file_hi,
        {{ utc_date_from_unix('unix_time') }} as utc_date
    from {{ source('raw', 'weather') }}
),
ranked as (
    select
        *,
        count(*) over (partition by unix_time) as n_files,
        row_number() over (
            partition by unix_time
            order by
                (utc_date between {{ plus_days('file_lo', var('weather_pad_days')) }}
                              and {{ minus_days('file_hi', var('weather_pad_days')) }}) desc,
                {{ diff_days('file_lo', 'file_hi') }} desc,
                filename desc
        ) as rn
    from raw
)
select * exclude (rn, utc_date, file_lo, file_hi)
from ranked
where rn = 1
