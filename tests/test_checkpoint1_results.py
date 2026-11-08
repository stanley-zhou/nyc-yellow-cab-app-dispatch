"""Checkpoint-1 result files are internally consistent (keys unique, shares in [0, 1], splits add
up). The duplicate-key checks would have caught the GROUP BY ALL + HAVING bug (DECISIONS.md)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from taxi_shock.config import load_config, path

CFG = load_config()
RES = path("results", CFG)


def _need(name: str):
    f = RES / name
    if not f.exists():
        pytest.skip(f"{name} not built (make dbt)")
    return f


def test_cbd_trip_check_tables_have_unique_keys_and_valid_shares():
    s = json.loads(_need("cbd_validation_trips.json").read_text())
    v = pd.DataFrame(s["by_vendor_month"])
    assert not v.duplicated(["month", "vendor_id", "grp"]).any()
    assert v["share_fee_pos"].between(0, 1).all()
    pairs = pd.DataFrame(s["group_i_by_borough_pair"])
    assert not pairs.duplicated(["pu_borough", "do_borough"]).any()
    assert pairs["n_trips"].sum() == s["totals"]["i_both_outside"]["n_trips"]
    zones = pd.DataFrame(s["manhattan_zones"]["rows"])
    assert zones["zone_id"].is_unique
    for m in s["monthly"]:
        parts = [k for k in m if k.startswith("touches_cbd:")]
        assert sum(m[k]["n_trips"] for k in parts) == m["ii_pickup_or_dropoff_inside"]["n_trips"]
    daily = pd.read_csv(_need("cbd_fee_daily_by_vendor.csv"))
    assert not daily.duplicated(["date", "vendor_id"]).any()


def test_vendor_series_unique_and_adds_up_to_weekly_totals():
    vs = pd.read_csv(_need("vendor_series.csv"))
    assert not vs.duplicated(["week_start", "vendor_id", "zone_group"]).any()
    wk = pd.read_csv(_need("citywide_weekly.csv")).set_index("week_start")["pickups"]
    tot = vs.groupby("week_start")["pickups"].sum()
    pd.testing.assert_series_equal(tot, wk.loc[tot.index], check_names=False,
                                   check_dtype=False)


def test_record_format_shares_and_modeled_zones():
    r = pd.read_csv(_need("record_format_shares.csv"))
    assert not r.duplicated(["week_start", "zone_group"]).any()
    shares = r.filter(like="share_")
    assert ((shares >= 0) & (shares <= 1)).all().all()
    m = json.loads(_need("modeled_zones.json").read_text())
    zs = pd.read_csv(_need("zone_summary.csv"))
    assert m["zone_ids"] == sorted(zs.loc[zs["passes_forecast_threshold"], "zone_id"].tolist())
    assert m["share_2024_pickups_modeled"] + m["share_2024_pickups_not_modeled"] == \
        pytest.approx(1.0, abs=1e-5)
