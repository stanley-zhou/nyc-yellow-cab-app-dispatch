-- Fails (returns a row) unless fct_hourly_zone_demand has exactly n_zones x n_hours rows.
with n as (
    select
        (select count(*) from {{ ref('stg_zones') }})                         as n_zones,
        (select count(distinct hour_ts) from {{ ref('int_hour_grid') }})       as n_hours,
        (select count(*) from {{ ref('fct_hourly_zone_demand') }})             as n_rows
)
select * from n where n_rows <> n_zones * n_hours
