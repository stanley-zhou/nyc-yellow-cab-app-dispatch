"""Checkpoint-1 checks requested by Stanley (2026-11-07), from the full warehouse.

Writes:
    results/vendor_series.csv          weekly valid pickups by VendorID x zone group, over
                                       data.event_study_window (CBD vs non-CBD: `area`)
    results/vendor_summary.json        vendor presence over the window, Helix entry week, and the
                                       year-on-year decomposition "did Helix replace or add volume"
    results/cbd_validation_trips.json  trip-level fee check over all zones, monthly over
                                       cbd.trip_check_window: share of trips with
                                       cbd_congestion_fee > 0 when (i) pickup and dropoff are both
                                       outside the CBD, (ii) pickup or dropoff is inside it
    results/record_format_shares.csv   item 2b: weekly share of Flex Fare / Helix / format-exempt
                                       trips by zone group (treatment = cbd, control groups)
    results/cbd_fee_daily_by_vendor.csv  daily fee share of trips touching the CBD by vendor
    results/modeled_zones.json         the forecast-modeled zone set (zone_summary.csv threshold)
                                       and its share of 2024 pickups (PLAN Phase 2)

Usage:
    python scripts/03c_checks.py
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from taxi_shock.causal.panel import control_zone_ids
from taxi_shock.cbd import PLANAR_CRS, area_share_south, sixtieth_street_line
from taxi_shock.config import load_config, path
from taxi_shock.download import OSM_60TH_FILE
from taxi_shock.io import connect
from taxi_shock.viz.maps import load_zones


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    out = path("results", cfg)
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        series = write_vendor_series(con, cfg, out)
        zone_post = _post_policy_zone_vendor(con, cfg)
        write_cbd_trip_check(con, cfg, out)
    write_vendor_summary(series, cfg, out, zone_post)
    write_record_format_shares(series, cfg, out)
    write_modeled_zones(cfg, out)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _d(ts) -> str:
    return pd.Timestamp(ts).date().isoformat()


def _share(num: float, den: float) -> float | None:
    return round(float(num) / float(den), 6) if den else None


# ---------------------------------------------------------------------------------------- vendors
def write_vendor_series(con, cfg: dict, out: Path) -> pd.DataFrame:
    lo, hi = cfg["data"]["event_study_window"]
    df = con.execute("""
        with wk as (   -- days of each panel week inside the download span (edge weeks < 7)
            select week_start, max(n_days) as n_days from fct_weekly_zone_panel group by 1)
        select v.week_start, v.event_week, wk.n_days, v.vendor_id, z.zone_group,
               sum(v.pickups) as pickups, sum(v.pickups_flex) as pickups_flex,
               sum(v.pickups_same_ts) as pickups_same_ts,
               sum(v.pickups_format_exempt) as pickups_format_exempt
        from fct_weekly_zone_vendor v
        join dim_zones z using (zone_id)
        join wk using (week_start)
        where v.week_start >= ?::date and v.week_start <= ?::date
        group by 1, 2, 3, 4, 5 order by 1, 4, 5""", [lo, hi]).df()
    names = {int(k): v for k, v in cfg["vendors"]["names"].items()}
    df["vendor_id"] = df["vendor_id"].astype("Int64")
    df["vendor_name"] = df["vendor_id"].map(lambda v: "unknown (NULL)" if pd.isna(v)
                                            else names.get(int(v), f"undocumented id {v}"))
    df["area"] = df["zone_group"].map(lambda g: "cbd" if g == "cbd" else "non_cbd")
    df["complete_week"] = df["n_days"] == 7
    df["week_start"] = pd.to_datetime(df["week_start"]).dt.date
    cols = ["week_start", "event_week", "n_days", "complete_week", "vendor_id", "vendor_name",
            "area", "zone_group", "pickups", "pickups_flex", "pickups_same_ts",
            "pickups_format_exempt"]
    df = df[cols]
    df.to_csv(out / "vendor_series.csv", index=False, lineterminator="\n")
    logging.info("vendor_series: %d rows, %d vendors", len(df),
                 df["vendor_id"].nunique(dropna=False))
    return df


def write_vendor_summary(series: pd.DataFrame, cfg: dict, out: Path,
                         zone_post: pd.DataFrame) -> None:
    vc = cfg["vendors"]
    new_id = int(vc["new_vendor_id"])
    full = series[series["complete_week"]].copy()
    full["week_start"] = pd.to_datetime(full["week_start"])
    full["vendor_key"] = full["vendor_id"].astype("string").fillna("null")
    weeks = sorted(full["week_start"].unique())

    # presence of each vendor over the complete weeks of the window (citywide)
    pres = full.pivot_table(index="vendor_key", columns="week_start", values="pickups",
                            aggfunc="sum", fill_value=0)
    pres = pres.reindex(columns=weeks, fill_value=0)
    city = pres.sum(axis=0)
    presence = {}
    for key, row in pres.iterrows():
        active = row[row > 0]
        presence[key] = {
            "vendor_name": full.loc[full["vendor_key"] == key, "vendor_name"].iloc[0],
            "n_weeks_with_pickups": int(len(active)),
            "share_of_weeks_with_pickups": round(len(active) / len(weeks), 4),
            "first_week": _d(active.index.min()) if len(active) else None,
            "last_week": _d(active.index.max()) if len(active) else None,
            "share_of_window_pickups": round(float(row.sum() / city.sum()), 6),
            "present_throughout": bool(len(active) / len(weeks) >= vc["present_min_week_share"]),
        }

    # Helix entry: first complete week with >= entry_share_min of citywide pickups
    new_share = pres.loc[str(new_id)] / city if str(new_id) in pres.index else city * 0
    entered = new_share[new_share >= vc["entry_share_min"]]
    entry = entered.index.min() if len(entered) else None

    # year-on-year decomposition by area and quarter of the weeks from entry on: for each
    # complete week w with a complete week w-52 (same weekday alignment), total(w) - total(w-52)
    # = new(w) + [incumbents(w) - incumbents(w-52)] (the new vendor has 0 a year earlier).
    # replacement_ratio = incumbents' YoY loss / new-vendor volume: 1 = pure replacement,
    # 0 = pure addition. Inside the CBD the YoY change also contains the policy effect.
    decomp = []
    if entry is not None:
        full["is_new"] = full["vendor_key"] == str(new_id)
        full["area_all"] = "all"
        for area_col in ("area", "zone_group", "area_all"):
            g = full.pivot_table(index=[area_col, "week_start"], columns="is_new",
                                 values="pickups", aggfunc="sum", fill_value=0)
            g = g.rename(columns={True: "new", False: "incumbent"})
            for c in ("new", "incumbent"):
                if c not in g:
                    g[c] = 0
            for area, ga in g.groupby(level=0):
                ga = ga.droplevel(0)
                prev = ga.reindex([w - pd.Timedelta(days=364) for w in ga.index])
                prev.index = ga.index
                d = ga.join(prev.add_suffix("_prev")).dropna()
                d = d[d.index >= entry]
                if d.empty:
                    continue
                d["quarter"] = pd.PeriodIndex(pd.to_datetime(d.index), freq="Q").astype(str)
                for q, dq in list(d.groupby("quarter")) + [("all_weeks_from_entry", d)]:
                    new_v, inc, inc_p = dq["new"].sum(), dq["incumbent"].sum(), \
                        dq["incumbent_prev"].sum()
                    tot, tot_p = new_v + inc, inc_p + dq["new_prev"].sum()
                    decomp.append({
                        "grouping": area_col.replace("area_all", "all"), "group": area,
                        "period": q, "n_weeks": int(len(dq)),
                        "new_vendor_pickups": int(new_v),
                        "incumbent_pickups": int(inc), "incumbent_pickups_year_before": int(inc_p),
                        "total_pickups": int(tot), "total_pickups_year_before": int(tot_p),
                        "total_yoy_change": _share(tot - tot_p, tot_p),
                        "incumbent_yoy_change": _share(inc - inc_p, inc_p),
                        "new_vendor_share_of_total": _share(new_v, tot),
                        "replacement_ratio": _share(inc_p - inc, new_v),
                    })
    result = {
        "generated_utc": _now(),
        "source": "results/vendor_series.csv (dbt fct_weekly_zone_vendor), complete weeks only",
        "window": cfg["data"]["event_study_window"],
        "n_complete_weeks": len(weeks),
        "vendor_names_source": "TLC Data Dictionary - Yellow Taxi Trip Records, March 18, 2025",
        "presence": presence,
        "vendors_present_throughout": sorted(k for k, v in presence.items()
                                             if v["present_throughout"]),
        "new_vendor": {"vendor_id": new_id, "entry_share_min": vc["entry_share_min"],
                       "entry_week": None if entry is None else _d(entry),
                       "first_week_with_pickups": presence.get(str(new_id), {}).get("first_week"),
                       "weeks_from_entry_to_policy_week": None if entry is None else int(
                           (pd.Timestamp(cfg["data"]["policy_date"]) - pd.Timestamp(entry)).days
                           // 7)},
        "yoy_decomposition": {
            "definition": ("weeks w >= entry with complete weeks w and w-52; total(w) - "
                           "total(w-52) = new(w) + incumbents(w) - incumbents(w-52); "
                           "replacement_ratio = (incumbents(w-52) - incumbents(w)) / new(w): "
                           "1 = new-vendor volume replaced incumbents' volume, 0 = it added to "
                           "it. Inside the CBD the YoY change also contains the policy effect."),
            "rows": decomp,
        },
        "detectability": _detectability(full, new_id, entry, cfg, zone_post),
    }
    (out / "vendor_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    logging.info("vendor_summary: entry week %s, present throughout %s",
                 result["new_vendor"]["entry_week"], result["vendors_present_throughout"])


def _detectability(full: pd.DataFrame, new_id: int, entry, cfg: dict,
                   zone_post: pd.DataFrame) -> dict:
    """Can aggregate counts tell replacement from addition, and what is at stake for the DiD?

    noise: Helix's weekly volume and weekly increments vs the typical absolute week-to-week change
    of the citywide total, over the ramp-up (first Helix week -> 10 weeks after entry).
    worst case: if every Helix trip were additional (not replacing an incumbent's trip), the
    observed log pickups of a group exceed the counterfactual by -log(1 - s), s = the group's
    Helix share; the bias of the CBD-vs-control log DiD over the post-policy weeks is
    -log(1 - s_cbd) + log(1 - s_control). Under pure replacement the bias is 0."""
    city = full.pivot_table(index="week_start", columns="vendor_key", values="pickups",
                            aggfunc="sum", fill_value=0)
    key = str(new_id)
    if key not in city or entry is None:
        return {"note": "new vendor absent from the window"}
    total = city.sum(axis=1)
    first = city.index[city[key] > 0].min()
    ramp = city.loc[first:entry + pd.Timedelta(weeks=10)]
    d_total = total.loc[ramp.index].diff().abs().dropna()
    by_group = full.pivot_table(index=["zone_group", "week_start"], columns="vendor_key",
                                values="pickups", aggfunc="sum", fill_value=0)
    post = by_group[by_group.index.get_level_values("week_start")
                    >= pd.Timestamp(cfg["data"]["policy_date"])]
    sums = post.groupby(level="zone_group").sum()
    share = (sums.get(key, 0) / sums.sum(axis=1)).to_dict()
    # bias per control definition (causal.control_groups), from zone-level post-policy counts
    zp = zone_post
    s_cbd = zp.loc[zp["zone_group"] == "cbd", "new"].sum() / \
        zp.loc[zp["zone_group"] == "cbd", "pickups"].sum()
    bias, ctrl_share = {}, {}
    for name in cfg["causal"]["control_groups"]:
        c = zp[zp["zone_id"].isin(control_zone_ids(zp, cfg, name))]
        ctrl_share[name] = float(c["new"].sum() / c["pickups"].sum())
        bias[name] = round(float(-np.log1p(-s_cbd) + np.log1p(-ctrl_share[name])), 6)
    return {
        "ramp_weeks": [_d(ramp.index.min()), _d(ramp.index.max())],
        "max_weekly_new_vendor_pickups_in_ramp": int(ramp[key].max()),
        "max_weekly_increase_new_vendor_in_ramp": int(ramp[key].diff().max()),
        "median_abs_weekly_change_total_in_ramp": float(d_total.median()),
        "post_policy_new_vendor_share_by_zone_group": {k: round(float(v), 6)
                                                       for k, v in share.items()},
        "post_policy_new_vendor_share_cbd": round(float(s_cbd), 6),
        "post_policy_new_vendor_share_by_control_group": {k: round(v, 6)
                                                          for k, v in ctrl_share.items()},
        "worst_case_did_log_bias_if_purely_additive_by_control": bias,
        "primary_control": cfg["causal"]["control"],
    }


def _post_policy_zone_vendor(con, cfg: dict) -> pd.DataFrame:
    """Per pickup zone: valid pickups and new-vendor pickups over complete post-policy weeks."""
    return con.execute("""
        with wk as (select week_start from fct_weekly_zone_panel group by 1
                    having max(n_days) = 7)
        select z.zone_id, z.borough, z.zone_group, z.is_airport,
               sum(v.pickups) as pickups,
               coalesce(sum(v.pickups) filter (where v.vendor_id = ?), 0) as new
        from fct_weekly_zone_vendor v
        join wk using (week_start)
        join dim_zones z using (zone_id)
        where v.week_start >= ?::date
        group by 1, 2, 3, 4""", [int(cfg["vendors"]["new_vendor_id"]),
                                 cfg["data"]["policy_date"]]).df()


def write_record_format_shares(series: pd.DataFrame, cfg: dict, out: Path) -> None:
    """Item 2b: weekly share of Flex Fare and Helix trips (and of format-exempt and
    identical-timestamp trips) by treatment group (`zone_group`), complete weeks."""
    s = series[series["complete_week"]].copy()
    s["pickups_new_vendor"] = np.where(s["vendor_id"] == int(cfg["vendors"]["new_vendor_id"]),
                                       s["pickups"], 0)
    cols = ["pickups", "pickups_flex", "pickups_new_vendor", "pickups_format_exempt",
            "pickups_same_ts"]
    g = s.groupby(["week_start", "event_week", "zone_group"], as_index=False)[cols].sum()
    for c in cols[1:]:
        g["share_" + c.removeprefix("pickups_")] = (g[c] / g["pickups"]).round(6)
    g.to_csv(out / "record_format_shares.csv", index=False, lineterminator="\n")
    logging.info("record_format_shares: %d rows", len(g))


# ----------------------------------------------------------------------------- CBD trip check
def write_cbd_trip_check(con, cfg: dict, out: Path) -> None:
    lo, hi = cfg["cbd"]["trip_check_window"]
    df = con.execute("""
        with t as (
            select date_trunc('month', t.pickup_ts)::date as month,
                   coalesce(pz.is_cbd, false) as pu_cbd,
                   dz.is_cbd                  as do_cbd,     -- NULL: dropoff id 264/265
                   t.cbd_congestion_fee       as fee
            from int_trips_valid t
            join dim_zones pz on pz.zone_id = t.pu_zone_id
            left join dim_zones dz on dz.zone_id = t.do_zone_id
            where t.pickup_ts >= ?::date and t.pickup_ts < ?::date + interval 1 day)
        select month,
               case when pu_cbd and do_cbd then 'touches_cbd:pickup_and_dropoff'
                    when pu_cbd then 'touches_cbd:pickup_only'
                    when do_cbd then 'touches_cbd:dropoff_only'
                    when do_cbd is null then 'outside:dropoff_zone_unknown'
                    else 'outside:both_outside' end as cls,
               count(*) as n_trips,
               count(*) filter (where fee > 0) as n_fee_pos,
               count(*) filter (where fee is null) as n_fee_null
        from t group by 1, 2 order by 1, 2""", [lo, hi]).df()
    df["month"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m")
    df["group"] = df["cls"].str.split(":").str[0]

    def summarise(d: pd.DataFrame) -> dict:
        n, pos, nul = int(d["n_trips"].sum()), int(d["n_fee_pos"].sum()), \
            int(d["n_fee_null"].sum())
        return {"n_trips": n, "n_fee_pos": pos, "n_fee_null": nul,
                "share_fee_pos": _share(pos, n - nul)}

    groups = {"i_both_outside": df["cls"] == "outside:both_outside",
              "ii_pickup_or_dropoff_inside": df["group"] == "touches_cbd"}
    detail = sorted(df["cls"].unique())
    monthly = []
    for m, dm in df.groupby("month"):
        row = {"month": m}
        for k, mask in groups.items():
            row[k] = summarise(dm[mask.loc[dm.index]])
        for c in detail:
            row[c] = summarise(dm[dm["cls"] == c])
        monthly.append(row)
    shares = {k: [r[k]["share_fee_pos"] for r in monthly] for k in groups}
    diag = _cbd_trip_diagnostics(con, cfg, lo, hi, out)
    result = {
        "generated_utc": _now(),
        "source": "int_trips_valid x dim_zones (is_cbd = config/zones_cbd.csv) in the warehouse",
        "window": [lo, hi],
        "month_definition": "local pickup month",
        "cbd_rule": ("dim_zones.is_cbd: the 60th St geometric rule plus the three harbour-island "
                     "overrides (103-105); fee check of PLAN Phase 1 extended to trips"),
        "share_definition": "trips with cbd_congestion_fee > 0 / trips with a non-NULL fee",
        "groups": {
            "i_both_outside": "pickup and dropoff zone both outside the CBD (dropoff known)",
            "ii_pickup_or_dropoff_inside": "pickup zone or dropoff zone inside the CBD",
            "outside:dropoff_zone_unknown": "pickup outside the CBD, dropoff id 264/265 "
                                            "(reported separately, in neither group)",
        },
        "totals": {**{k: summarise(df[m]) for k, m in groups.items()},
                   **{c: summarise(df[df["cls"] == c]) for c in detail}},
        "monthly_share_range": {k: {"min": min(v), "max": max(v)} for k, v in shares.items()},
        "monthly": monthly,
        **diag,
    }
    (out / "cbd_validation_trips.json").write_text(json.dumps(result, indent=2) + "\n",
                                                   encoding="utf-8")
    logging.info("cbd_validation_trips: %s", result["monthly_share_range"])


def _cbd_trip_diagnostics(con, cfg: dict, lo: str, hi: str, out: Path) -> dict:
    """Where fee-carrying trips with both ends outside the CBD come from, and fee recording by
    vendor. Writes results/cbd_fee_daily_by_vendor.csv; returns JSON blocks."""
    lookup = path("raw_lookup", cfg)
    line = sixtieth_street_line(lookup / OSM_60TH_FILE, cfg["cbd"]["street_names"])
    shapes = load_zones(lookup / "taxi_zones.shp").to_crs(PLANAR_CRS)
    area = area_share_south(shapes, line)
    base = """
        with t as (
            select t.pickup_ts, t.vendor_id, t.pu_zone_id, t.do_zone_id,
                   coalesce(pz.is_cbd, false) as pu_cbd, dz.is_cbd as do_cbd,
                   pz.borough as pu_borough, dz.borough as do_borough,
                   coalesce(t.cbd_congestion_fee > 0, false) as fee_pos
            from int_trips_valid t
            join dim_zones pz on pz.zone_id = t.pu_zone_id
            left join dim_zones dz on dz.zone_id = t.do_zone_id
            where t.pickup_ts >= ?::date and t.pickup_ts < ?::date + interval 1 day)"""
    pairs = con.execute(base + """
        select pu_borough, do_borough, count(*) as n_trips,
               round(avg(fee_pos::int), 6) as share_fee_pos
        from t where not pu_cbd and do_cbd = false
        group by 1, 2 order by n_trips desc""", [lo, hi]).df()
    zones = con.execute(base + """
        select z.zone_id, z.zone_name, z.is_cbd,
               count(*) filter (where not t.pu_cbd and t.do_cbd = false) as n_both_outside,
               avg(t.fee_pos::int) filter (where not t.pu_cbd and t.do_cbd = false)
                                                                    as share_fee_both_outside,
               count(*) filter (where t.do_zone_id = t.pu_zone_id)  as n_intra,
               avg(t.fee_pos::int) filter (where t.do_zone_id = t.pu_zone_id)
                                                                    as share_fee_intra
        from t join dim_zones z on z.zone_id = t.pu_zone_id
        where z.borough = 'Manhattan' group by 1, 2, 3 order by z.zone_id""", [lo, hi]).df()
    zones["area_share_south_of_line"] = zones["zone_id"].map(area).round(4)
    zones = zones.round({"share_fee_both_outside": 6, "share_fee_intra": 6})
    vend = con.execute(base + """
        select date_trunc('month', pickup_ts)::date as month, vendor_id,
               case when pu_cbd or do_cbd then 'ii_pickup_or_dropoff_inside'
                    when do_cbd = false then 'i_both_outside' end as grp,
               count(*) as n_trips, round(avg(fee_pos::int), 6) as share_fee_pos
        from t group by 1, 2, 3 order by 1, 2, 3""", [lo, hi]).df()
    vend = vend[vend["grp"].notna()]
    vend["month"] = pd.to_datetime(vend["month"]).dt.strftime("%Y-%m")
    daily = con.execute(base + """
        select cast(pickup_ts as date) as date, vendor_id, count(*) as n_trips_touching_cbd,
               round(avg(fee_pos::int), 6) as share_fee_pos
        from t where pu_cbd or do_cbd group by 1, 2 order by 1, 2""", [lo, hi]).df()
    daily.to_csv(out / "cbd_fee_daily_by_vendor.csv", index=False, lineterminator="\n")
    straddle = zones[(zones["area_share_south_of_line"] > 0)
                     & (zones["area_share_south_of_line"] < 1)]
    return {
        "group_i_by_borough_pair": pairs.to_dict("records"),
        "manhattan_zones": {
            "note": ("area_share_south_of_line: share of the zone polygon south of the 60th St "
                     "line (cbd.area_share_south); 0 < share < 1 = the zone straddles the line"),
            "straddling_zone_ids": [int(z) for z in straddle["zone_id"]],
            "rows": zones.replace({np.nan: None}).to_dict("records"),
        },
        "by_vendor_month": vend.replace({np.nan: None}).to_dict("records"),
        "daily_by_vendor_file": "results/cbd_fee_daily_by_vendor.csv",
    }


# ---------------------------------------------------------------------------- modeled zones
def write_modeled_zones(cfg: dict, out: Path) -> None:
    zs = pd.read_csv(out / "zone_summary.csv")
    m = zs[zs["passes_forecast_threshold"]]
    total = zs["pickups_2024"].sum()
    result = {
        "generated_utc": _now(),
        "source": "results/zone_summary.csv",
        "threshold_mean_hourly_pickups_2024": cfg["zones"]["min_mean_hourly_pickups_2024"],
        "approved": "Stanley, Checkpoint 1 (2026-11-07)",
        "n_modeled": int(len(m)),
        "n_not_modeled": int(len(zs) - len(m)),
        "share_2024_pickups_modeled": _share(m["pickups_2024"].sum(), total),
        "share_2024_pickups_not_modeled": _share(total - m["pickups_2024"].sum(), total),
        "n_modeled_by_zone_group": {k: int(v) for k, v in m["zone_group"].value_counts().items()},
        "n_zones_by_zone_group": {k: int(v) for k, v in zs["zone_group"].value_counts().items()},
        "zone_ids": sorted(int(z) for z in m["zone_id"]),
    }
    (out / "modeled_zones.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    logging.info("modeled_zones: %d zones, share of 2024 pickups %s", result["n_modeled"],
                 result["share_2024_pickups_modeled"])


if __name__ == "__main__":
    main()
