"""Grid completeness of fct_hourly_zone_demand (smoke warehouse; full warehouse from Phase 1)."""

import pytest

from taxi_shock.io import connect

pytestmark = pytest.mark.warehouse


def test_grid_is_complete_with_explicit_zeros(smoke_db):
    with connect(smoke_db) as con:
        n_rows, n_zones, n_hours, n_zero, n_dup = con.execute("""
            select count(*), count(distinct zone_id), count(distinct hour_ts),
                   count(*) filter (where pickups = 0),
                   count(*) - count(distinct (zone_id, hour_ts))
            from fct_hourly_zone_demand""").fetchone()
        n_lookup = con.execute("select count(*) from stg_zones").fetchone()[0]
    assert n_rows == n_zones * n_hours
    assert n_zones == n_lookup
    assert n_zero > 0, "explicit zeros must be present"
    assert n_dup == 0


def test_grid_hours_are_contiguous_local_hours(smoke_db):
    with connect(smoke_db) as con:
        gaps = con.execute("""
            select count(*) from (
                select hour_ts - lag(hour_ts) over (order by hour_ts) as d
                from (select distinct hour_ts from fct_hourly_zone_demand))
            where d is not null and d <> interval 1 hour""").fetchone()[0]
    # the smoke month (2024-10) contains no DST transition, so every step is exactly 1 hour
    assert gaps == 0
