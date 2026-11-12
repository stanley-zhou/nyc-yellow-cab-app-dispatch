"""Every low-volume run in the warehouse is either explained (snow, COVID onset) or a configured
source outage; the configured windows are real low-volume runs (DECISIONS.md, Phase 4b)."""

from __future__ import annotations

import pandas as pd

from taxi_shock.config import load_config
from taxi_shock.io import connect
from taxi_shock.outages import in_any, low_volume_runs, outage_days, windows


def test_low_volume_runs_are_explained_or_listed(warehouse_db):
    cfg = load_config()
    so = cfg["source_outages"]
    with connect(warehouse_db, cfg=cfg) as con:
        h = con.execute("select hour_ts, sum(pickups) n from fct_hourly_zone_demand "
                        "group by 1 order by 1").df().set_index("hour_ts")["n"]
        snow = con.execute("select cast(hour_ts as date) d, sum(snowfall_in) s from stg_weather "
                           "group by 1").df().set_index("d")["s"]
    snow.index = pd.to_datetime(snow.index)
    runs = low_volume_runs(h, so["rule"])
    real = [(pd.Timestamp(a), pd.Timestamp(b) + pd.Timedelta(hours=23)) for a, b in
            so["real_events"]]
    win = windows(cfg)
    covered = set()
    for r in runs.itertuples():
        snowy = snow.get(r.start.normalize(), 0.0) >= so["rule"]["snow_day_in"]
        listed = [i for i, (a, b) in enumerate(win) if a <= r.start and r.end <= b]
        assert snowy or in_any(r.start, real) or listed, f"unexplained low run {r.start}"
        covered.update(listed)
    assert covered == set(range(len(win))), "a configured outage window has no low run"


def test_outage_days():
    cfg = load_config()
    days = outage_days(cfg)
    assert pd.Timestamp("2023-09-22") in days and pd.Timestamp("2022-09-17") in days
    assert pd.Timestamp("2024-01-01") not in days
