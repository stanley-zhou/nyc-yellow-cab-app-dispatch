"""Weekly / daily zone panels for the DiD design (Phase 4).

`control_zone_ids` resolves a named control group from `causal.control_groups` in config. The
primary control (`causal.control`) is the "donut": Manhattan non-CBD zones without the six zones
that straddle the 60th St line (Stanley, 2026-11-07; evidence: results/cbd_validation_trips.json).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def control_zone_ids(
    zones: pd.DataFrame, cfg: dict[str, Any], name: str | None = None
) -> list[int]:
    """Zone ids of control group `name` (default: the primary `causal.control`).

    `zones` needs columns zone_id, borough, zone_group, is_airport (dim_zones /
    results/zone_summary.csv). A definition selects by `zone_groups` or by `boroughs`
    (optionally `exclude_airports`), then removes `exclude_zones`. CBD zones are never controls.
    """
    name = name or cfg["causal"]["control"]
    spec = cfg["causal"]["control_groups"][name]
    keep = pd.Series(True, index=zones.index)
    if "zone_groups" in spec:
        keep &= zones["zone_group"].isin(spec["zone_groups"])
    if "boroughs" in spec:
        keep &= zones["borough"].isin(spec["boroughs"])
    if spec.get("exclude_airports"):
        keep &= ~zones["is_airport"].astype(bool)
    keep &= ~zones["zone_id"].isin(spec.get("exclude_zones", []))
    keep &= zones["zone_group"] != "cbd"
    return sorted(int(z) for z in zones.loc[keep, "zone_id"])


def full_weeks(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Rows whose panel week lies inside data.event_study_window and is complete (7 days)."""
    lo, hi = (pd.Timestamp(x) for x in cfg["data"]["event_study_window"])
    keep = (df["week_start"] >= lo) & (df["week_start"] + pd.Timedelta(days=6) <= hi)
    return df[keep].reset_index(drop=True)


def pair_category(pu_cbd: pd.Series, do_cbd: pd.Series, pu_ctl: pd.Series,
                  do_ctl: pd.Series) -> pd.Series:
    """Amendment 2 (B2) trip categories from the two zones of a pair: within_cbd (treated),
    within_control, entering (control -> CBD), leaving (CBD -> control); other pairs
    (donut zones, CBD/control to elsewhere) get 'other'."""
    cat = pd.Series("other", index=pu_cbd.index, dtype="object")
    cat[pu_cbd & do_cbd] = "within_cbd"
    cat[pu_ctl & do_ctl] = "within_control"
    cat[pu_ctl & do_cbd] = "entering"
    cat[pu_cbd & do_ctl] = "leaving"
    return cat


TRIP_STATS = ["n_revenue_known", "sum_fare_amount", "sum_cbd_fee", "pickups_fare_t1",
              "pickups_fare_t2", "pickups_fare_t3"]


def demand_panel(con, cfg: dict[str, Any]) -> pd.DataFrame:
    """Complete zone x week demand panel (every zone, every complete week in the event-study
    window, zero-pickup weeks included) with the trip statistics and the CMT + Curb count.

    `fct_weekly_zone_panel` is complete; `fct_weekly_zone_trip_stats` and
    `fct_weekly_zone_vendor` only have zone-weeks with trips, so they are LEFT-joined and their
    missing counts are zeros (an inner join silently dropped every zero-pickup zone-week;
    DECISIONS.md, Phase 4 review)."""
    s = ", ".join(f"coalesce(s.{c}, 0) as {c}" for c in TRIP_STATS)
    w = con.execute(f"""
        select w.*, {s}, coalesce(v.pickups_cmt_curb, 0) as pickups_cmt_curb
        from fct_weekly_zone_panel w
        left join fct_weekly_zone_trip_stats s using (zone_id, week_start)
        left join (select zone_id, week_start, sum(pickups) as pickups_cmt_curb
                   from fct_weekly_zone_vendor where vendor_id in (1, 2) group by all) v
               using (zone_id, week_start)""").df()
    w["week_start"] = pd.to_datetime(w["week_start"])
    w["pickups_literal"] = w["pickups"] - w["pickups_format_exempt"]
    return full_weeks(w[w["n_days"] == 7], cfg)
