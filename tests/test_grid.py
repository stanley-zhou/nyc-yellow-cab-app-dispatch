"""Grid completeness and DST handling of the FULL warehouse (PLAN Phase 1; amendment item 3).

Runs against data/warehouse.duckdb. Inside `make verify PHASE>=1` a missing warehouse fails
(conftest.warehouse_db) and any skipped test fails the verify run.
"""

import pandas as pd
import pytest

from taxi_shock.config import load_config
from taxi_shock.io import connect

pytestmark = pytest.mark.warehouse
TZ = load_config()["timezone"]


def test_grid_is_complete_with_explicit_zeros(warehouse_db):
    with connect(warehouse_db) as con:
        n_rows, n_zones, n_hours, n_zero, n_dup = con.execute("""
            select count(*), count(distinct zone_id), count(distinct hour_ts),
                   count(*) filter (where pickups = 0),
                   count(*) - count(distinct (zone_id, hour_ts))
            from fct_hourly_zone_demand""").fetchone()
        n_lookup = con.execute("select count(*) from stg_zones").fetchone()[0]
    assert n_rows == n_zones * n_hours
    assert n_zones == n_lookup == 263
    assert n_zero > 0, "explicit zeros must be present"
    assert n_dup == 0


def test_grid_hours_equal_an_independent_tz_calendar(warehouse_db):
    """int_hours must be exactly the set of local wall-clock hours that exist in America/New_York
    between the first and last downloaded month, computed here independently with pandas/zoneinfo
    (absolute hours -> local, fall-back repeat merged)."""
    lo, hi = load_config()["data"]["yellow_months"]
    start = pd.Timestamp(f"{lo}-01").tz_localize(TZ)
    end = (pd.Timestamp(f"{hi}-01") + pd.offsets.MonthBegin(1)).tz_localize(TZ)
    expected = pd.date_range(start, end, freq="h", inclusive="left").tz_localize(None).unique()
    with connect(warehouse_db) as con:
        got = con.execute("select hour_ts from int_hours order by hour_ts").df()["hour_ts"]
    assert len(got) == len(expected)
    assert (pd.DatetimeIndex(got) == pd.DatetimeIndex(expected).sort_values()).all()


@pytest.mark.parametrize("day, n_hours, absent_hour", [
    ("2024-03-10", 23, 2),     # spring forward: 02:00 does not exist
    ("2024-11-03", 24, None),  # fall back: 01:00 occurs twice, merged into one row
    ("2019-03-10", 23, 2),
    ("2025-11-02", 24, None),
])
def test_dst_days(warehouse_db, day, n_hours, absent_hour):
    with connect(warehouse_db) as con:
        hours = con.execute("""
            select hour(hour_ts) as h, count(*) as n_zone_rows
            from fct_hourly_zone_demand
            where cast(hour_ts as date) = cast(? as date) group by 1 order by 1""",
                            [day]).df()
    assert len(hours) == n_hours
    assert (hours["n_zone_rows"] == 263).all(), "one row per zone per local hour, no duplicates"
    if absent_hour is not None:
        assert absent_hour not in set(hours["h"])


def test_every_spring_forward_day_in_span_has_23_hours(warehouse_db):
    with connect(warehouse_db) as con:
        short = con.execute("""
            select cast(hour_ts as date) as d, count(*) as n from int_hours
            group by 1 having count(*) <> 24 order by 1""").df()
    lo, hi = load_config()["data"]["yellow_months"]
    years = range(int(lo[:4]), int(hi[:4]) + 1)
    assert len(short) == len(years), "exactly one non-24-hour local day per year"
    assert (short["n"] == 23).all()
    assert all(pd.Timestamp(d).month == 3 and pd.Timestamp(d).dayofweek == 6 for d in short["d"])


def test_fall_back_hour_counts_both_wall_clock_passes(warehouse_db):
    """Pickups in the merged fall-back 01:00 row = every valid in-grid trip stamped 01:xx."""
    with connect(warehouse_db) as con:
        grid, trips = con.execute("""
            select (select sum(pickups) from fct_hourly_zone_demand
                    where hour_ts = timestamp '2024-11-03 01:00'),
                   (select count(*) from int_trips_valid
                    where pu_hour = timestamp '2024-11-03 01:00')""").fetchone()
    assert grid == trips > 0


def test_spring_forward_trips_are_counted_not_lost(warehouse_db):
    with connect(warehouse_db) as con:
        counted, direct = con.execute("""
            select (select sum(pu_miss_spring_forward) from fct_data_quality_monthly),
                   (select count(*) from int_trips_valid
                    where hour(pickup_ts) = 2 and month(pickup_ts) = 3
                      and dayofweek(pickup_ts) = 0 and day(pickup_ts) between 8 and 14)
            """).fetchone()
    assert counted == direct
