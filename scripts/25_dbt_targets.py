"""E3: row counts and dbt test results per target (DuckDB, Snowflake) -> results/dbt_targets.json.

Reads the run results of `dbt build --target snowflake --target-path target/snowflake` and of
`dbt test --target-path target/duckdb` (see `make snowflake`), counts the rows of every model in
both warehouses, compares the marts on the days / weeks both targets cover completely (parity), and
records the credits the Snowflake warehouse used (INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY).

Coverage differs by design: Snowflake holds the cleaned trips of source months
`snowflake.months`, DuckDB every downloaded month, so total row counts differ; the parity check
compares the common window: weekly marts from the second panel week to the last complete week,
daily and hourly marts from the second day (a December-2022 file records some pickups of the first
day as stragglers), features_demand from the second day plus its 28-day look-back.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect as duck
from taxi_shock.snowflake import connect as snow

LOG = logging.getLogger("dbt_targets")

# mart -> keys, compared values (None = every column), time column, window:
#   weeks = complete panel weeks from the second one; days = from the second day;
#   warm  = from the second day + `snowflake.parity.warmup_days` (features_demand's longest
#           look-back, so its lags and rolling means see the same days in both targets).
# Daily and hourly marts are compared month by month (memory).
_CH = ["vendor_id", "channel", "platform", "trip_type", "zone_group", "is_cmt_outer_block"]
PARITY = {
    "fct_weekly_zone_panel": (["zone_id", "week_start"], None, "week_start", "weeks"),
    "fct_weekly_zone_channel": (["zone_id", "week_start", *_CH], ["pickups"], "week_start",
                                "weeks"),
    "fct_weekly_zone_trip_stats": (["zone_id", "week_start"], None, "week_start", "weeks"),
    "fct_weekly_zone_vendor": (["zone_id", "week_start", "vendor_id"], None, "week_start",
                               "weeks"),
    "fct_weekly_pair_speed": (["region", "pu_zone_id", "do_zone_id", "week_start", "hour_band",
                               "dist_tercile"], None, "week_start", "weeks"),
    "fct_daily_zone_panel": (["zone_id", "date"], None, "date", "days"),
    "fct_daily_zone_channel": (["zone_id", "day", *_CH], ["pickups"], "day", "days"),
    "fct_hourly_zone_demand": (["zone_id", "hour_ts"], None, "hour_ts", "days"),
    "features_demand": (["zone_id", "hour_ts"], None, "hour_ts", "warm"),
}
REL_TOL = float(load_config()["snowflake"]["parity"]["relative_tolerance"])


def run_results(target_path: str) -> dict:
    f = repo_root() / "dbt" / target_path / "run_results.json"
    rr = json.loads(f.read_text())
    out = {"models": {}, "tests": {}, "seeds": {}, "generated_at": rr["metadata"]["generated_at"],
           "elapsed_seconds": round(float(rr["elapsed_time"]), 1)}
    for r in rr["results"]:
        kind, name = r["unique_id"].split(".")[0], r["unique_id"].split(".")[-1]
        if kind == "test":
            name = ".".join(r["unique_id"].split(".")[2:])
            out["tests"][name] = {"status": r["status"], "failures": r.get("failures")}
        elif kind in ("model", "seed"):
            out["models" if kind == "model" else "seeds"][name] = {
                "status": r["status"], "seconds": round(r["execution_time"], 1)}
    out["n_tests"] = len(out["tests"])
    out["tests_pass"] = sum(v["status"] == "pass" for v in out["tests"].values())
    out["tests_not_pass"] = {k: v for k, v in out["tests"].items() if v["status"] != "pass"}
    return out


def week_bounds(cfg: dict) -> tuple[str, str]:
    lo = pd.Timestamp(f"{cfg['snowflake']['months'][0]}-01")
    first_week = lo - pd.Timedelta(days=(lo.weekday() + 1) % 7)       # Sunday-start weeks
    hi = pd.Timestamp(f"{cfg['snowflake']['months'][1]}-01") + pd.offsets.MonthEnd(0)
    last_week = hi - pd.Timedelta(days=(hi.weekday() + 1) % 7)
    if last_week + pd.Timedelta(days=6) > hi:
        last_week -= pd.Timedelta(days=7)
    return str((first_week + pd.Timedelta(days=7)).date()), str(last_week.date())


def _kind(x: pd.Series, y: pd.Series) -> str:
    """'time' for dates / timestamps on either side, 'number' for numbers and booleans,
    'text' otherwise."""
    for z in (x, y):
        if pd.api.types.is_datetime64_any_dtype(z):
            return "time"
        v = z.dropna()
        if len(v) and isinstance(v.iloc[0], (pd.Timestamp, date, datetime)):
            return "time"
    for z in (x, y):
        v = z.dropna()
        if len(v) and isinstance(v.iloc[0], str):
            return "text"
    return "number"


def compare(a: pd.DataFrame, b: pd.DataFrame, keys: list[str]) -> dict:
    a, b = (x.rename(columns=str.lower) for x in (a, b))
    for x in (a, b):
        for k in keys:
            if k in ("week_start", "date", "day", "hour_ts"):
                x[k] = pd.to_datetime(x[k]).astype("datetime64[ns]")
    m = a.merge(b, on=keys, how="outer", suffixes=("_duckdb", "_snowflake"), indicator=True)
    vals = [c[:-7] for c in m.columns if c.endswith("_duckdb")]
    worst = {}
    n_bad = 0
    for v in vals:
        x, y = m[f"{v}_duckdb"], m[f"{v}_snowflake"]
        both_nan = x.isna() & y.isna()
        kind = _kind(x, y)
        if kind == "text":                      # exact equality
            bad = ~both_nan & (x.astype("string") != y.astype("string")).fillna(True)
            worst[v] = float(bad.any())
        else:
            if kind == "time":
                x, y = (pd.to_datetime(z).astype("datetime64[ns]").astype("int64").where(z.notna())
                        for z in (x, y))
            x, y = (pd.to_numeric(z, errors="raise").astype(float) for z in (x, y))
            rel = (x - y).abs() / np.maximum(1.0, np.maximum(x.abs(), y.abs()))
            bad = ~both_nan & ~(rel <= REL_TOL)
            worst[v] = float(rel[~both_nan].max()) if (~both_nan).any() else 0.0
        n_bad += int(bad.sum())
    return {"rows_duckdb": int((m["_merge"] != "right_only").sum()),
            "rows_compared_both": int((m["_merge"] == "both").sum()),
            "rows_snowflake": int((m["_merge"] != "left_only").sum()),
            "keys_only_duckdb": int((m["_merge"] == "left_only").sum()),
            "keys_only_snowflake": int((m["_merge"] == "right_only").sum()),
            "cells_differing": n_bad, "max_relative_difference": worst,
            "identical": bool((m["_merge"] == "both").all() and n_bad == 0)}


def merge_results(parts: list[dict]) -> dict:
    out = {k: sum(p[k] for p in parts) for k in ("rows_duckdb", "rows_compared_both",
                                                  "rows_snowflake", "keys_only_duckdb",
                                                  "keys_only_snowflake", "cells_differing")}
    cols = {c for p in parts for c in p["max_relative_difference"]}
    out["max_relative_difference"] = {c: max(p["max_relative_difference"].get(c, 0.0)
                                             for p in parts) for c in sorted(cols)}
    out["identical"] = all(p["identical"] for p in parts)
    return out


def windows(cfg: dict) -> dict[str, tuple[str, str]]:
    lo_w, hi_w = week_bounds(cfg)
    first = pd.Timestamp(f"{cfg['snowflake']['months'][0]}-01")
    last = pd.Timestamp(f"{cfg['snowflake']['months'][1]}-01") + pd.offsets.MonthEnd(0)
    d1 = first + pd.Timedelta(days=1)
    warm = d1 + pd.Timedelta(days=int(cfg["snowflake"]["parity"]["warmup_days"]))
    end = str((last + pd.Timedelta(days=1)).date())                  # exclusive
    return {"weeks": (lo_w, hi_w), "days": (str(d1.date()), end), "warm": (str(warm.date()), end)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", default="dbt_targets.json", help="file name under results/")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("snowflake").setLevel(logging.WARNING)
    cfg = load_config()
    sf_rr, dk_rr = run_results("target/snowflake"), run_results("target/duckdb")
    manifest = json.loads((repo_root() / "dbt" / "target" / "duckdb" / "manifest.json")
                          .read_text())
    dk_models = {n.split(".")[-1] for n, v in manifest["nodes"].items()
                 if n.startswith("model.") and v["config"].get("materialized") != "ephemeral"}
    models = sorted(dk_models | set(sf_rr["models"]))
    schema = os.environ["SNOWFLAKE_SCHEMA"]
    win = windows(cfg)
    rows: dict[str, dict] = {}
    parity: dict[str, dict] = {}
    sc = snow()
    cur = sc.cursor()
    with duck(path("warehouse", cfg), cfg=cfg) as dc:
        dk_tables = {r[0] for r in dc.execute("select table_name from information_schema.tables")
                     .fetchall()}
        cur.execute(f"select table_name from information_schema.tables "
                    f"where table_schema = '{schema.upper()}'")
        sf_tables = {r[0].lower() for r in cur.fetchall()}
        for m in models:
            rows[m] = {
                "duckdb": (int(dc.execute(f"select count(*) from {m}").fetchone()[0])
                           if m in dk_tables else None),
                "snowflake": (int(cur.execute(f"select count(*) from {schema}.{m}")
                                  .fetchone()[0]) if m in sf_tables else None)}
        for m, (keys, vals, tcol, wname) in PARITY.items():
            cols = "*" if vals is None else ", ".join(keys + vals)
            lo, hi = win[wname]
            if wname == "weeks":
                chunks = [(f"{tcol} between '{lo}' and '{hi}'")]
            else:
                edges = [*pd.date_range(lo, hi, freq="MS").strftime("%Y-%m-%d")]
                edges = sorted({lo, *edges, hi})
                chunks = [f"{tcol} >= '{a}' and {tcol} < '{b}'"
                          for a, b in zip(edges[:-1], edges[1:], strict=True)]
            parts = []
            for w in chunks:
                a = dc.execute(f"select {cols} from {m} where {w}").df()
                cur.execute(f"select {cols} from {schema}.{m} where {w}")
                parts.append(compare(a, cur.fetch_pandas_all(), keys))
            parity[m] = merge_results(parts) | {"window": [lo, hi], "chunks": len(chunks)}
            LOG.info("parity %s: %s", m, {k: v for k, v in parity[m].items()
                                          if k != "max_relative_difference"})
    # dialect finding (DECISIONS [E3]): integer seconds divided by the literal 60.0 is fixed
    # point on Snowflake; size of the effect on summed durations per pickup zone x dropoff zone
    # x week, measured on the loaded trips
    cur.execute(f"""select max(abs(a - b) / greatest(1, abs(a), abs(b))), count(*) from (
        select sum(datediff(second, pickup_ts, dropoff_ts) / 60.0) as a,
               sum(cast(datediff(second, pickup_ts, dropoff_ts) as double) / 60.0) as b
        from {schema}.int_trips_valid
        group by pu_zone_id, do_zone_id, date_trunc('week', pu_hour))""")
    dur = cur.fetchone()
    dialect = {"duration_minutes_decimal_vs_double": {
        "grouping": "pickup zone x dropoff zone x week (trips of int_trips_valid)",
        "max_relative_difference": float(dur[0]), "groups": int(dur[1])}}
    start = sf_rr["generated_at"][:10]
    cur.execute("select sum(credits_used), sum(credits_used_compute), "
                "sum(credits_used_cloud_services) from table(information_schema."
                f"warehouse_metering_history(dateadd('day', -7, current_timestamp()), "
                f"current_timestamp(), '{os.environ['SNOWFLAKE_WAREHOUSE']}'))")
    cr = cur.fetchone()
    cur.execute(f"show warehouses like '{os.environ['SNOWFLAKE_WAREHOUSE']}'")
    wh = dict(zip([c[0] for c in cur.description], cur.fetchone(), strict=True))
    sc.close()
    rec = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "targets": {
            "duckdb": {"adapter": "dbt-duckdb", "coverage": "every downloaded month (raw files)",
                       "command": "dbt test (warehouse built by `make dbt`)", "tests": dk_rr},
            "snowflake": {"adapter": "dbt-snowflake", "warehouse_size": wh["size"],
                          "coverage": f"cleaned trips, source months "
                                      f"{cfg['snowflake']['months'][0]} to "
                                      f"{cfg['snowflake']['months'][1]} "
                                      "(results/snowflake_load.json)",
                          "command": "dbt build --target snowflake", "build": sf_rr}},
        "row_counts": rows,
        "parity": {"windows": win, "relative_tolerance": REL_TOL, "marts": parity,
                   "all_identical": all(v["identical"] for v in parity.values())},
        "dialect_checks": dialect,
        "snowflake_credits_last_7_days": {"total": float(cr[0] or 0),
                                          "compute": float(cr[1] or 0),
                                          "cloud_services": float(cr[2] or 0),
                                          "since": start},
    }
    out = path("results", cfg) / args.out
    out.write_text(json.dumps(rec, indent=2, default=str) + "\n")
    LOG.info("wrote %s", out.relative_to(repo_root()))


if __name__ == "__main__":
    main()
