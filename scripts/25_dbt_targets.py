"""E3: row counts and dbt test results per target (DuckDB, Snowflake) -> results/dbt_targets.json.

Reads the run results of `dbt build --target snowflake --target-path target/snowflake` and of
`dbt test --target-path target/duckdb` (see `make snowflake`), counts the rows of every model in
both warehouses, compares the marts on the weeks both targets cover completely (parity), and
records the credits the Snowflake warehouse used (INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY).

Coverage differs by design: Snowflake holds the cleaned trips of source months
`snowflake.months`, DuckDB every downloaded month, so total row counts differ; the parity check
compares the common window, from the second panel week (the first week misses pickups that a
December-2022 file recorded as stragglers) to the last complete week.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect as duck
from taxi_shock.snowflake import connect as snow

LOG = logging.getLogger("dbt_targets")

# mart -> (key columns, value columns compared); weekly marts restricted to the parity weeks
PARITY = {
    "fct_weekly_zone_panel": (["zone_id", "week_start"], None),
    "fct_weekly_zone_channel": (["zone_id", "week_start", "vendor_id", "channel", "platform",
                                 "trip_type", "zone_group", "is_cmt_outer_block"], ["pickups"]),
    "fct_weekly_zone_trip_stats": (["zone_id", "week_start"], None),
    "fct_weekly_zone_vendor": (["zone_id", "week_start", "vendor_id"], None),
    "fct_weekly_pair_speed": (["region", "pu_zone_id", "do_zone_id", "week_start", "hour_band",
                               "dist_tercile"], None),
}
REL_TOL = 1e-9


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


def compare(a: pd.DataFrame, b: pd.DataFrame, keys: list[str]) -> dict:
    a, b = (x.rename(columns=str.lower) for x in (a, b))
    for x in (a, b):
        for k in keys:
            if "week" in k and k != "event_week":
                x[k] = pd.to_datetime(x[k])
    m = a.merge(b, on=keys, how="outer", suffixes=("_duckdb", "_snowflake"), indicator=True)
    vals = [c[:-7] for c in m.columns if c.endswith("_duckdb")]
    worst = {}
    n_bad = 0
    for v in vals:
        x = pd.to_numeric(m[f"{v}_duckdb"], errors="coerce").astype(float)
        y = pd.to_numeric(m[f"{v}_snowflake"], errors="coerce").astype(float)
        both_nan = x.isna() & y.isna()
        rel = (x - y).abs() / np.maximum(1.0, np.maximum(x.abs(), y.abs()))
        bad = ~both_nan & ~(rel <= REL_TOL)
        n_bad += int(bad.sum())
        worst[v] = float(rel[~both_nan].max()) if (~both_nan).any() else 0.0
    return {"rows_duckdb": int((m["_merge"] != "right_only").sum()),
            "rows_snowflake": int((m["_merge"] != "left_only").sum()),
            "keys_only_duckdb": int((m["_merge"] == "left_only").sum()),
            "keys_only_snowflake": int((m["_merge"] == "right_only").sum()),
            "cells_differing": n_bad, "max_relative_difference": worst,
            "identical": bool((m["_merge"] == "both").all() and n_bad == 0)}


def main() -> None:
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
    lo, hi = week_bounds(cfg)
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
        for m, (keys, vals) in PARITY.items():
            cols = "*" if vals is None else ", ".join(keys + vals)
            q = f"select {cols} from {{t}} where week_start between '{lo}' and '{hi}'"
            a = dc.execute(q.format(t=m)).df()
            cur.execute(q.format(t=f"{schema}.{m}"))
            b = cur.fetch_pandas_all()
            parity[m] = compare(a, b, keys)
            LOG.info("parity %s: %s", m, {k: v for k, v in parity[m].items()
                                          if k != "max_relative_difference"})
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
        "parity": {"weeks": [lo, hi], "relative_tolerance": REL_TOL, "marts": parity,
                   "all_identical": all(v["identical"] for v in parity.values())},
        "snowflake_credits_last_7_days": {"total": float(cr[0] or 0),
                                          "compute": float(cr[1] or 0),
                                          "cloud_services": float(cr[2] or 0),
                                          "since": start},
    }
    out = path("results", cfg) / "dbt_targets.json"
    out.write_text(json.dumps(rec, indent=2, default=str) + "\n")
    LOG.info("wrote %s", out.relative_to(repo_root()))


if __name__ == "__main__":
    main()
