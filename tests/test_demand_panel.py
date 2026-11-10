"""The Phase-4 demand panel is complete: every zone x every complete week of the event-study
window, zero-pickup weeks included (an inner join once dropped them; DECISIONS.md, Phase 4)."""

from __future__ import annotations

import pandas as pd

from taxi_shock.causal.panel import demand_panel
from taxi_shock.config import load_config
from taxi_shock.io import connect


def test_demand_panel_is_complete(warehouse_db):
    cfg = load_config()
    with connect(warehouse_db, cfg=cfg) as con:
        w = demand_panel(con, cfg)
        n_zones = con.execute("select count(*) from stg_zones").fetchone()[0]
    weeks = w["week_start"].nunique()
    assert len(w) == n_zones * weeks
    assert not w.duplicated(["zone_id", "week_start"]).any()
    assert (w["pickups"] == 0).any()                       # zero-pickup weeks are kept
    lo, hi = (pd.Timestamp(x) for x in cfg["data"]["event_study_window"])
    assert w["week_start"].min() >= lo and w["week_start"].max() + pd.Timedelta(days=6) <= hi
    fare_cols = ["pickups_fare_t1", "pickups_fare_t2", "pickups_fare_t3"]
    assert (w[fare_cols].sum(axis=1) <= w["pickups"]).all()
    assert w[["pickups_cmt_curb", "n_revenue_known"]].notna().all().all()
