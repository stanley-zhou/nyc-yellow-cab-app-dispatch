"""E3 (PLAN Amendment 4): load the cleaned yellow trips and the HVFHV aggregates into Snowflake.

Needs the Snowflake environment (`source ~/.snowflake/taxi.env`; see taxi_shock/snowflake.py).

1. Export the cleaned yellow trips, source months `snowflake.months` (one Parquet file per month),
   from the DuckDB warehouse: the valid, de-duplicated rows of int_trips_flagged (drop_reason
   NULL) with the columns int_trips_valid reads. The cleaning itself (de-duplication and the
   validity rules over the raw files) stays in DuckDB; Snowflake receives its output.
2. Upload them, the HVFHV aggregate files, the raw weather CSVs, the zone lookup and
   config/zones_cbd.csv to an internal stage (PUT), then `COPY INTO` tables in schema RAW
   (`CREATE OR REPLACE`, so a rerun reloads from the stage; PUT skips unchanged files).
3. Verify every table's row count against its local source and write
   results/snowflake_load.json. Exits non-zero if any count differs.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect as duck
from taxi_shock.snowflake import connect as snow

LOG = logging.getLogger("sf_load")

YELLOW_COLS = {   # column -> Snowflake type (int_trips_valid's input columns)
    "vendor_id": "integer", "pickup_ts": "timestamp_ntz", "dropoff_ts": "timestamp_ntz",
    "pu_zone_id": "integer", "do_zone_id": "integer", "trip_distance": "double",
    "fare_amount": "double", "total_amount": "double", "passenger_count": "double",
    "payment_type": "integer", "cbd_congestion_fee": "double", "request_source": "varchar",
    "source_month": "date", "is_format_exempt": "boolean"}
HV_ZONE_HOUR = {"zone_id": "integer", "pu_hour": "timestamp_ntz", "platform": "varchar",
                "shared_request": "varchar", "shared_match": "varchar", "trip_type": "varchar",
                "dist_bin": "integer", "trips": "integer", "miles": "double",
                "seconds": "bigint", "base_fare": "double", "driver_pay": "double",
                "trips_cbd_fee": "integer"}
HV_PAIR_WEEK = {"pu_zone_id": "integer", "do_zone_id": "integer", "week_start": "date",
                "platform": "varchar", "trips": "integer"}
WEATHER = ["unix_time bigint", "temperature_2m double", "apparent_temperature double",
           "precipitation double", "rain double", "snowfall double", "weathercode integer",
           "cloudcover integer", "windspeed_10m double", "relativehumidity_2m integer"]
ZONE_LOOKUP = ["LocationID integer", "Borough varchar", "Zone varchar", "service_zone varchar"]
ZONES_CBD = ["zone_id integer", "zone_name varchar", "borough varchar", "is_cbd boolean",
             "source varchar", "geometric_is_cbd boolean", "fee_label varchar",
             "fee_share double", "intra_fee_label varchar", "intra_fee_share double",
             "n_trips integer", "n_intra integer", "centroid_lon double",
             "centroid_lat double", "geometry_available boolean"]


def months(lo: str, hi: str) -> list[str]:
    out, y, m = [], int(lo[:4]), int(lo[5:7])
    while f"{y:04d}-{m:02d}" <= hi:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def export_yellow(cfg: dict, out_dir: Path, ms: list[str]) -> dict[str, int]:
    """One Parquet file per source month; skipped if present with the recorded row count."""
    out_dir.mkdir(parents=True, exist_ok=True)
    log_f = out_dir / "export_counts.json"
    done = json.loads(log_f.read_text()) if log_f.exists() else {}
    cols = ", ".join(YELLOW_COLS)
    with duck(path("warehouse", cfg), cfg=cfg) as con:
        for m in ms:
            f = out_dir / f"yellow_valid_{m}.parquet"
            if f.exists() and m in done:
                continue
            q = (f"select {cols} from int_trips_flagged where drop_reason is null "
                 f"and source_month = date '{m}-01'")
            con.execute(f"copy ({q}) to '{f.as_posix()}' (format parquet, compression zstd)")
            done[m] = int(con.execute(f"select count(*) from read_parquet('{f.as_posix()}')")
                          .fetchone()[0])
            log_f.write_text(json.dumps(done, indent=1) + "\n")
            LOG.info("exported %s: %d rows", m, done[m])
    return {m: done[m] for m in ms}


def local_rows(glob: str) -> int:
    return int(duckdb.connect().execute(f"select count(*) from read_parquet('{glob}')")
               .fetchone()[0])


def csv_rows(f: Path) -> int:
    """Data rows of a CSV with one header line and no embedded newlines."""
    return sum(1 for line in f.read_text().splitlines() if line.strip()) - 1


def ddl(cols: dict[str, str] | list[str]) -> str:
    items = [f"{k} {v}" for k, v in cols.items()] if isinstance(cols, dict) else cols
    return ", ".join(items)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--skip-put", action="store_true", help="files already on the stage")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("snowflake").setLevel(logging.WARNING)
    cfg = load_config()
    sc = cfg["snowflake"]
    ms = months(*sc["months"])
    load_dir = path("snowflake_load", cfg)
    t0 = time.time()
    yellow_counts = export_yellow(cfg, load_dir / "yellow_valid", ms)
    hv_dir = path("hvfhv_processed", cfg)
    hv_files = {k: sorted(hv_dir.glob(f"{k}_*.parquet")) for k in ("zone_hour", "pair_week")}
    hv_files = {k: [f for f in v if ms[0] <= f.stem[-7:] <= ms[-1]] for k, v in hv_files.items()}
    weather = sorted(path("raw_weather", cfg).glob("open_meteo_*.csv"))
    lookup = path("raw_lookup", cfg) / "taxi_zone_lookup.csv"
    zones_cbd = path("zones_cbd", cfg)
    raw, stage = sc["raw_schema"], f"{sc['raw_schema']}.{sc['stage']}"

    con = snow(schema=raw)
    cur = con.cursor()
    run = cur.execute
    run(f"create schema if not exists {raw}")
    run(f"use schema {raw}")
    run(f"create stage if not exists {sc['stage']}")
    run("create or replace file format pq type = parquet use_logical_type = true")
    run("create or replace file format csv_h type = csv skip_header = 1 "
        "field_optionally_enclosed_by = '\"' null_if = ('')")

    uploads = {"yellow_valid": sorted((load_dir / "yellow_valid").glob("yellow_valid_*.parquet")),
               "hvfhv_zone_hour": hv_files["zone_hour"], "hvfhv_pair_week": hv_files["pair_week"],
               "weather": weather, "zone_lookup": [lookup], "zones_cbd": [zones_cbd]}
    put = {}
    if not args.skip_put:
        for prefix, files in uploads.items():
            n_up = n_skip = 0
            for f in files:
                cur.execute(f"put 'file://{f.resolve().as_posix()}' @{stage}/{prefix}/ "
                            "auto_compress = false parallel = 8 overwrite = false")
                for r in cur.fetchall():
                    if r[6] == "UPLOADED":
                        n_up += 1
                    else:
                        n_skip += 1
            put[prefix] = {"files": len(files), "uploaded": n_up, "skipped_unchanged": n_skip,
                           "bytes": sum(f.stat().st_size for f in files)}
            LOG.info("put %s: %s", prefix, put[prefix])

    def copy_parquet(table: str, cols: dict[str, str], prefix: str) -> None:
        run(f"create or replace table {table} ({ddl(cols)})")
        run(f"copy into {table} from @{stage}/{prefix}/ file_format = (format_name = pq) "
            "match_by_column_name = case_insensitive on_error = abort_statement")

    copy_parquet("yellow_trips_valid", YELLOW_COLS, "yellow_valid")
    copy_parquet("hvfhv_zone_hour", HV_ZONE_HOUR, "hvfhv_zone_hour")
    copy_parquet("hvfhv_pair_week", HV_PAIR_WEEK, "hvfhv_pair_week")
    run(f"create or replace table weather ({', '.join(WEATHER)}, filename varchar)")
    run(f"copy into weather from (select $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, "
        f"metadata$filename from @{stage}/weather/) file_format = (format_name = csv_h) "
        "on_error = abort_statement")
    for table, cols, prefix in (("zone_lookup", ZONE_LOOKUP, "zone_lookup"),
                                ("zones_cbd", ZONES_CBD, "zones_cbd")):
        run(f"create or replace table {table} ({', '.join(cols)})")
        run(f"copy into {table} from @{stage}/{prefix}/ file_format = (format_name = csv_h) "
            "on_error = abort_statement")

    expected = {
        "yellow_trips_valid": sum(yellow_counts.values()),
        "hvfhv_zone_hour": sum(local_rows(f.as_posix()) for f in hv_files["zone_hour"]),
        "hvfhv_pair_week": sum(local_rows(f.as_posix()) for f in hv_files["pair_week"]),
        "weather": sum(csv_rows(f) for f in weather),
        "zone_lookup": csv_rows(lookup),
        "zones_cbd": csv_rows(zones_cbd),
    }
    tables = {}
    for t, n in expected.items():
        got = int(cur.execute(f"select count(*) from {t}").fetchone()[0])
        tables[t] = {"rows_local": n, "rows_snowflake": got, "match": got == n}
        LOG.info("%s: local %d, snowflake %d", t, n, got)
    con.close()
    rec = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "months": [ms[0], ms[-1]], "schema": raw, "method": "internal stage, PUT, COPY INTO",
           "yellow_source": "int_trips_flagged where drop_reason is null (DuckDB), per month",
           "yellow_rows_by_month": yellow_counts, "put": put, "tables": tables,
           "all_match": all(v["match"] for v in tables.values()),
           "wall_seconds": round(time.time() - t0, 1)}
    out = path("results", cfg) / "snowflake_load.json"
    out.write_text(json.dumps(rec, indent=2) + "\n")
    LOG.info("wrote %s", out.relative_to(repo_root()))
    if not rec["all_match"]:
        raise SystemExit("row counts differ between local sources and Snowflake")


if __name__ == "__main__":
    main()
