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


def test_design_panels_are_balanced(warehouse_db):
    """Both DiD designs (donut and Brooklyn + Queens controls) carry every zone of the design in
    every week, with explicit zeros (reviewer fix, Phase 4)."""
    from taxi_shock.causal.panel import control_zone_ids
    from taxi_shock.config import path

    cfg = load_config()
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    cbd = zs.loc[zs["is_cbd"], "zone_id"].tolist()
    with connect(warehouse_db, cfg=cfg) as con:
        w = demand_panel(con, cfg)
    weeks = w["week_start"].nunique()
    for name in ("manhattan_non_cbd_donut", "outer_boroughs"):
        zones = set(cbd) | set(control_zone_ids(zs, cfg, name))
        d = w[w["zone_id"].isin(zones)]
        assert len(d) == len(zones) * weeks, name
        assert d.groupby("zone_id").size().eq(weeks).all(), name
