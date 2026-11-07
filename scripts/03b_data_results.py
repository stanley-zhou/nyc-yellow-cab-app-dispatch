"""Phase-1 result files from the full warehouse (every number later quoted comes from these).

Writes:
    results/data_quality.json          filter counts (first failing rule + independent flags),
                                       duplicates, grid-join drops, weather overlap, span, zeros
    results/data_quality_monthly.csv   the same counts per source month, with shares filtered
    results/zone_summary.csv           one row per zone: names, CBD/airport flags, zone group,
                                       2024 pickups, mean hourly pickups 2024, forecast threshold
    results/citywide_weekly.csv        citywide pickups per panel week (input of F1b)
    results/citywide_yearly.csv        citywide pickups per calendar year vs 2019 (model_start)

Usage:
    python scripts/03b_data_results.py [--smoke]
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from taxi_shock.config import load_config, path
from taxi_shock.io import connect

RULES = ["pickup_window", "duration", "distance", "fare", "pu_zone"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--smoke", action="store_true", help="smoke warehouse -> results/smoke/")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    db = path("smoke_warehouse" if args.smoke else "warehouse", cfg)
    out = path("smoke.results_dir" if args.smoke else "results", cfg)
    out.mkdir(parents=True, exist_ok=True)
    with connect(db, cfg=cfg) as con:
        write_data_quality(con, cfg, out)
        write_zone_summary(con, cfg, out)
        write_citywide(con, out)


def _share(num: float, den: float) -> float | None:
    return round(float(num) / float(den), 6) if den else None


def write_data_quality(con, cfg: dict, out: Path) -> None:
    m = con.execute("select * from fct_data_quality_monthly order by source_month").df()
    m["source_month"] = pd.to_datetime(m["source_month"]).dt.strftime("%Y-%m")
    m["rows_removed"] = m["raw_rows"] - m["valid_rows"]
    m["share_removed"] = (m["rows_removed"] / m["raw_rows"]).round(6)
    m["share_removed_excl_duplicates"] = (
        (m["raw_rows"] - m["duplicate_rows"] - m["valid_rows"]) / m["raw_rows"]).round(6)
    m.to_csv(out / "data_quality_monthly.csv", index=False, lineterminator="\n")

    tot = m.drop(columns=["source_month", "share_removed", "share_removed_excl_duplicates"]).sum()
    raw = int(tot["raw_rows"])
    span = con.execute("""
        select min(hour_ts), max(hour_ts), count(*) from int_hours""").fetchone()
    n_zones = con.execute("select count(*) from stg_zones").fetchone()[0]
    n_rows, n_zero = con.execute("""
        select count(*), count(*) filter (where pickups = 0) from fct_hourly_zone_demand
    """).fetchone()
    wx_unix, wx_overlap, wx_diff = con.execute("""
        select (select count(*) from int_weather_selected),
               (select count(*) from int_weather_overlap),
               (select count(*) filter (where n_distinct_versions > 1) from int_weather_overlap)
    """).fetchone()
    wx_local, wx_merged = con.execute("""
        select count(*), count(*) filter (where n_source_hours > 1) from stg_weather
        where hour_ts between (select min(hour_ts) from int_hours)
                          and (select max(hour_ts) from int_hours)""").fetchone()
    c1, c2, n_terc = con.execute("select c1, c2, n_trips from int_distance_terciles").fetchone()
    worst = m.loc[m["share_removed"].idxmax()]
    q = cfg["quality"]
    result = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "fct_data_quality_monthly (dbt), per month in results/data_quality_monthly.csv",
        "span": {"first_hour": str(span[0]), "last_hour": str(span[1]), "n_hours": int(span[2]),
                 "n_zones": int(n_zones), "n_grid_rows": int(n_rows),
                 "n_months": int(len(m))},
        "rules": {
            "order": ["duplicates"] + RULES,
            "pickup_window": (f"source_month - {q['straggler_days']} day <= pickup_ts < "
                              f"source_month + 1 month + {q['straggler_days']} day (half-open)"),
            "duration": (f"{q['min_duration_minutes']} min <= dropoff - pickup <= "
                         f"{q['max_duration_hours']} h; not tested when dropoff = pickup "
                         "timestamp and trip_distance > 0 (missing dropoff time)"),
            "distance": (f"0 < trip_distance <= {q['max_trip_distance_miles']} miles; lower bound "
                         f"not tested for Flex Fare trips (payment_type "
                         f"{q['flex_fare_payment_type']})"),
            "fare": (f"fare_amount > 0, or payment_type = {q['flex_fare_payment_type']} "
                     "(Flex Fare trip, TLC data dictionary 2025-03-18)"),
            "pu_zone": "PULocationID in [{}, {}]".format(*cfg["zones"]["valid_ids"]),
            "duplicates": "rows of the same file identical in every raw column; one copy kept",
            "null_handling": "a NULL in a tested column fails that rule",
        },
        "totals": {
            "raw_rows": raw,
            "duplicate_rows": int(tot["duplicate_rows"]),
            "dropped_first_failing_rule": {r: int(tot[f"drop_{r}"]) for r in RULES},
            "failing_each_rule_independently": {r: int(tot[f"flag_{r}"]) for r in RULES},
            "valid_rows": int(tot["valid_rows"]),
            "rows_removed": int(tot["rows_removed"]),
            "share_removed": _share(tot["rows_removed"], raw),
            "share_removed_by_rule": {r: _share(tot[f"drop_{r}"], raw) for r in RULES},
            "share_duplicates": _share(tot["duplicate_rows"], raw),
            "valid_stragglers_kept": int(tot["valid_stragglers_kept"]),
            "valid_only_by_format_exemption": int(tot["valid_format_exempt"]),
            "exemptions_used": {"fare_flex": int(tot["exempt_fare_used"]),
                                "distance_flex_zero": int(tot["exempt_distance_used"]),
                                "duration_missing_dropoff_time":
                                    int(tot["exempt_duration_used"])},
            "failing_each_plan_literal_rule": {"duration": int(tot["flag_duration_literal"]),
                                               "distance": int(tot["flag_distance_literal"]),
                                               "fare": int(tot["flag_fare_literal"])},
            "share_valid_only_by_format_exemption": _share(tot["valid_format_exempt"], raw),
            "note_format_exemptions": (
                "PLAN's literal rules would additionally drop valid_only_by_format_exemption "
                "rows (per month in data_quality_monthly.csv; per zone-hour in "
                "fct_hourly_zone_demand.n_format_exempt; per zone-day/week in the panels' "
                "pickups_format_exempt)"),
        },
        "per_month_share_removed": {
            "min": float(m["share_removed"].min()),
            "median": float(m["share_removed"].median()),
            "max": float(m["share_removed"].max()),
            "month_of_max": worst["source_month"],
            "month_of_min": m.loc[m["share_removed"].idxmin(), "source_month"],
        },
        "grid_join": {
            "pickups_in_grid": int(tot["pickups_in_grid"]),
            "pickup_dropped_edge_straggler": int(tot["pu_miss_edge_straggler"]),
            "pickup_dropped_spring_forward_gap": int(tot["pu_miss_spring_forward"]),
            "dropoff_dropped_edge_straggler": int(tot["do_miss_edge_straggler"]),
            "dropoff_dropped_spring_forward_gap": int(tot["do_miss_spring_forward"]),
            "note": ("edge stragglers fall outside the downloaded calendar span; spring-forward "
                     "trips are stamped in the non-existent local 02:00 hour"),
        },
        "hourly_panel": {"n_rows": int(n_rows), "n_zero_pickup_rows": int(n_zero),
                         "share_zero_pickup_rows": _share(n_zero, n_rows)},
        "weather": {"n_unix_hours_selected": int(wx_unix),
                    "n_unix_hours_in_several_files": int(wx_overlap),
                    "n_overlapping_hours_with_differing_values": int(wx_diff),
                    "n_local_hours_in_span": int(wx_local),
                    "n_local_hours_merging_two_readings": int(wx_merged)},
        "distance_terciles": {"c1_miles": float(c1), "c2_miles": float(c2),
                              "n_trips": int(n_terc),
                              "period": cfg["panel"]["distance_tercile_period"]},
    }
    (out / "data_quality.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    logging.info("data_quality: %d raw rows, share removed %s", raw,
                 result["totals"]["share_removed"])


def write_zone_summary(con, cfg: dict, out: Path) -> None:
    thr = float(cfg["zones"]["min_mean_hourly_pickups_2024"])
    df = con.execute("""
        with h as (
            select zone_id,
                   sum(pickups) filter (where year(hour_ts) = 2024)            as pickups_2024,
                   count(*) filter (where year(hour_ts) = 2024)                as hours_2024,
                   sum(pickups)                                                as pickups_all
            from fct_hourly_zone_demand group by zone_id)
        select z.zone_id, z.zone_name, z.borough, z.service_zone, z.is_cbd, z.is_airport,
               z.zone_group, z.geometry_available, h.pickups_2024, h.hours_2024,
               h.pickups_2024 / nullif(h.hours_2024, 0)                        as mean_hourly_2024,
               h.pickups_all
        from dim_zones z join h using (zone_id) order by zone_id""").df()
    total = df["pickups_2024"].sum()
    df["share_of_2024_pickups"] = (df["pickups_2024"] / total).round(6) if total else None
    df["mean_hourly_2024"] = df["mean_hourly_2024"].round(4)
    df["passes_forecast_threshold"] = df["mean_hourly_2024"] >= thr
    df.to_csv(out / "zone_summary.csv", index=False, lineterminator="\n")
    logging.info("zone_summary: %d zones, %d pass the %.1f threshold", len(df),
                 int(df["passes_forecast_threshold"].sum()), thr)


def write_citywide(con, out: Path) -> None:
    wk = con.execute("""
        select week_start, max(n_days) as n_days, sum(pickups) as pickups
        from fct_weekly_zone_panel group by week_start order by week_start""").df()
    wk["complete_week"] = wk["n_days"] == 7
    wk.to_csv(out / "citywide_weekly.csv", index=False, lineterminator="\n")
    yr = con.execute("""
        select year(date) as year, count(distinct date) as n_days, sum(pickups) as pickups
        from fct_daily_zone_panel group by 1 order by 1""").df()
    yr["mean_daily_pickups"] = (yr["pickups"] / yr["n_days"]).round(1)
    base = yr.loc[yr["year"] == yr["year"].min(), "mean_daily_pickups"].iloc[0]
    yr[f"ratio_to_{int(yr['year'].min())}"] = (yr["mean_daily_pickups"] / base).round(4)
    yr.to_csv(out / "citywide_yearly.csv", index=False, lineterminator="\n")


if __name__ == "__main__":
    main()
