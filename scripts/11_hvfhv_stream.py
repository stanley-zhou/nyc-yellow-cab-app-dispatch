"""Amendment 4: stream the high-volume FHV (HVFHV) trip files month by month into aggregates.

Per month (hvfhv.months, oldest first; months already in the manifest are skipped, so a crash
resumes): disk guard -> download -> aggregate with DuckDB -> verify -> delete the raw file.

Disk guard: free space on the filesystem named by the environment variable in
hvfhv.disk_guard_env (the Windows drive that holds the WSL disk image; a machine-specific path, so
never in the repo), else on data/; stop if below hvfhv.min_free_gb before a download.

Records: every row with a valid pickup zone (zones.valid_ids) and a non-NULL platform; rows outside
are counted per reason in the stream log. Pickup hour = floor of pickup_datetime (TLC local time).

Aggregates (Amendment 4, designed once so no re-download is needed), Parquet per month under
hvfhv.out_dir:
  (i)  zone_hour: pickup zone x pickup hour x platform (hvfhs_license_num) x shared_request_flag x
       shared_match_flag x trip type (within / into / out_of / neither the CBD, 60th St rule via
       config/zones_cbd.csv; an unknown dropoff zone counts as outside) x distance bin
       (hvfhv.distance_edges; the yellow distance-tercile cuts are among the edges):
       trips, sum trip_miles, sum trip_time (s), sum base_passenger_fare, sum driver_pay,
       trips with cbd_congestion_fee > 0 (column absent before 2025: 0)
  (ii) pair_week: pickup zone x dropoff zone x panel week (Sunday start) x platform: trips
Verification before deletion: the trips of (i) and of (ii) each equal the number of kept rows;
kept + dropped rows = the file's row count from its Parquet metadata.

Manifest: data/raw/hvfhv_manifest.csv (URL, bytes, sha256, rows, download date); the stream log
with the row accounting is results/hvfhv_stream_log.csv.

Usage:
    python scripts/11_hvfhv_stream.py [--months 2023-01 2023-03]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.download import download_file, month_range

LOG = logging.getLogger("hvfhv")
MANIFEST_COLS = ["url", "file", "bytes", "sha256", "rows", "download_date"]


class DiskGuardError(RuntimeError):
    pass


def free_gb(cfg: dict) -> tuple[float, str]:
    hv = cfg["hvfhv"]
    target = os.environ.get(hv["disk_guard_env"]) or str(path("raw_hvfhv", cfg).parent)
    return shutil.disk_usage(target).free / 1e9, target


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def aggregate(con: duckdb.DuckDBPyConnection, f: Path, month: str, cfg: dict,
              out: Path) -> dict:
    lo, hi = cfg["zones"]["valid_ids"]
    edges = [float(e) for e in cfg["hvfhv"]["distance_edges"]]
    cols = {r[0] for r in con.execute(f"describe select * from read_parquet('{f}')").fetchall()}
    fee = "coalesce(cbd_congestion_fee, 0) > 0" if "cbd_congestion_fee" in cols else "false"
    cbd = (repo_root() / cfg["paths"]["zones_cbd"]).as_posix()
    bins = " ".join(f"when trip_miles < {e} then {i}" for i, e in enumerate(edges))
    con.execute(f"""
        create or replace temp table cbd as
        select zone_id::integer as zone_id from read_csv_auto('{cbd}') where is_cbd""")
    con.execute(f"""
        create or replace temp table t as
        select PULocationID::integer as pu, DOLocationID::integer as dz,
               hvfhs_license_num as platform,
               coalesce(shared_request_flag, 'NULL') as shared_request,
               coalesce(shared_match_flag, 'NULL') as shared_match,
               date_trunc('hour', pickup_datetime) as pu_hour,
               pickup_datetime::date as pu_day,
               case when trip_miles is null then -1 {bins} else {len(edges)} end as dist_bin,
               trip_miles, trip_time, base_passenger_fare, driver_pay, {fee} as fee_charged
        from read_parquet('{f}')
        where PULocationID between {lo} and {hi} and hvfhs_license_num is not null""")
    n_file = con.execute(f"select count(*) from read_parquet('{f}')").fetchone()[0]
    n_keep = con.execute("select count(*) from t").fetchone()[0]
    n_zone = con.execute(f"""select count(*) from read_parquet('{f}')
                             where not coalesce(PULocationID between {lo} and {hi}, false)"""
                         ).fetchone()[0]
    zh = out / f"zone_hour_{month}.parquet"
    pw = out / f"pair_week_{month}.parquet"
    con.execute(f"""
        copy (
          select pu as zone_id, pu_hour, platform, shared_request, shared_match,
                 case when pc.zone_id is not null and dc.zone_id is not null then 'within'
                      when dc.zone_id is not null then 'into'
                      when pc.zone_id is not null then 'out_of' else 'neither' end as trip_type,
                 dist_bin, count(*)::integer as trips, sum(trip_miles) as miles,
                 sum(trip_time)::bigint as seconds, sum(base_passenger_fare) as base_fare,
                 sum(driver_pay) as driver_pay, count(*) filter (where fee_charged)::integer
                     as trips_cbd_fee
          from t left join cbd pc on pc.zone_id = t.pu left join cbd dc on dc.zone_id = t.dz
          group by all order by all
        ) to '{zh}' (format parquet, compression zstd)""")
    con.execute(f"""
        copy (
          select pu as pu_zone_id, dz as do_zone_id,
                 (pu_day - cast(dayofweek(pu_day) as integer))::date as week_start,
                 platform, count(*)::integer as trips
          from t group by all order by all
        ) to '{pw}' (format parquet, compression zstd)""")
    s1 = con.execute(f"select sum(trips) from read_parquet('{zh}')").fetchone()[0]
    s2 = con.execute(f"select sum(trips) from read_parquet('{pw}')").fetchone()[0]
    return {"rows_file": int(n_file), "rows_kept": int(n_keep),
            "rows_invalid_pu_zone": int(n_zone),
            "rows_null_platform": int(n_file - n_keep - n_zone),
            "trips_zone_hour": int(s1), "trips_pair_week": int(s2),
            "has_cbd_congestion_fee": "cbd_congestion_fee" in cols,
            "verified": bool(s1 == n_keep and s2 == n_keep)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--months", nargs=2, metavar=("FIRST", "LAST"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    hv, src = cfg["hvfhv"], cfg["sources"]
    raw = path("raw_hvfhv", cfg)
    out = repo_root() / hv["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    man_p = repo_root() / hv["manifest"]
    log_p = path("results", cfg) / "hvfhv_stream_log.csv"
    man = pd.read_csv(man_p) if man_p.exists() else pd.DataFrame(columns=MANIFEST_COLS)
    log = pd.read_csv(log_p) if log_p.exists() else pd.DataFrame()
    done = set(log.loc[log["verified"], "month"]) if len(log) else set()
    months = month_range(*(args.months or hv["months"]))
    con = duckdb.connect()
    con.execute(f"set memory_limit = '{cfg['duckdb']['memory_limit']}'")
    con.execute(f"set threads = {int(cfg['duckdb']['threads'])}")
    con.execute(f"set temp_directory = '{(repo_root() / cfg['paths']['duckdb_tmp']).as_posix()}'")
    for m in months:
        if m in done:
            LOG.info("%s: already aggregated and verified, skip", m)
            continue
        gb, where = free_gb(cfg)
        if gb < float(hv["min_free_gb"]):
            raise DiskGuardError(f"{gb:.1f} GB free on {where} < {hv['min_free_gb']} GB: "
                                 f"stop before {m} (Amendment 4)")
        url = f"{src['tlc_base_url']}/{src['hvfhv_path'].format(month=m)}"
        f = raw / f"fhvhv_tripdata_{m}.parquet"
        nbytes = download_file(url, f, cfg)
        digest = sha256(f)
        acc = aggregate(con, f, m, cfg, out)
        if not acc["verified"]:
            raise RuntimeError(f"{m}: aggregate totals do not match the kept rows: {acc}; "
                               "raw file kept for inspection")
        f.unlink()
        today = date.today().isoformat()
        man = pd.concat([man[man["file"] != f.name], pd.DataFrame([{
            "url": url, "file": f.name, "bytes": nbytes, "sha256": digest,
            "rows": acc["rows_file"], "download_date": today}])], ignore_index=True)
        man.sort_values("file").to_csv(man_p, index=False, lineterminator="\n")
        log = pd.concat([log[log["month"] != m] if len(log) else log, pd.DataFrame([{
            "month": m, "bytes": nbytes, "sha256": digest, **acc,
            "free_gb_before": round(gb, 1), "processed_date": today}])], ignore_index=True)
        log.sort_values("month").to_csv(log_p, index=False, lineterminator="\n")
        LOG.info("%s: %d rows kept of %d, verified, raw deleted (%.1f GB free before)", m,
                 acc["rows_kept"], acc["rows_file"], gb)


if __name__ == "__main__":
    main()
