"""results/data_quality.json is internally consistent and matches the full warehouse."""

import json

import pytest

from taxi_shock.config import load_config, path
from taxi_shock.io import connect

CFG = load_config()


def _dq():
    return json.loads((path("results", CFG) / "data_quality.json").read_text())


def test_totals_balance():
    t = _dq()["totals"]
    assert t["raw_rows"] == (t["duplicate_rows"] + sum(t["dropped_first_failing_rule"].values())
                             + t["valid_rows"])
    assert t["rows_removed"] == t["raw_rows"] - t["valid_rows"]
    for rule, n in t["dropped_first_failing_rule"].items():
        assert n <= t["failing_each_rule_independently"][rule]
    g = _dq()["grid_join"]
    assert t["valid_rows"] == (g["pickups_in_grid"] + g["pickup_dropped_edge_straggler"]
                               + g["pickup_dropped_spring_forward_gap"])


def test_weather_covers_every_grid_hour_and_overlap_is_reported():
    w = _dq()["weather"]
    assert w["n_local_hours_in_span"] == _dq()["span"]["n_hours"]
    # informational: revisions between overlapping files are reported, never averaged
    assert 0 <= w["n_overlapping_hours_with_differing_values"] <= w["n_unix_hours_in_several_files"]


@pytest.mark.warehouse
def test_results_match_warehouse(warehouse_db):
    d = _dq()
    with connect(warehouse_db) as con:
        raw, pickups = con.execute("""
            select (select sum(raw_rows) from fct_data_quality_monthly),
                   (select sum(pickups) from fct_hourly_zone_demand)""").fetchone()
        n_parquet = con.execute(
            f"select count(*) from read_parquet('{path('raw_yellow', CFG).as_posix()}"
            "/yellow_tripdata_*.parquet')").fetchone()[0]
    assert raw == d["totals"]["raw_rows"] == n_parquet
    assert pickups == d["grid_join"]["pickups_in_grid"]
