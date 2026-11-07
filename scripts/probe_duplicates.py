"""Measure exact-duplicate trip rows in the raw yellow files under three definitions.

Evidence for the duplicate rule in `int_trips_flagged` (DECISIONS.md, Phase 1):

* `full_within_file`  – rows identical in **every raw column** of the same monthly file;
* `projected_within_file` – rows identical in the projected staging columns of the same file;
* `full_cross_file`   – rows identical in every raw column but present in **two different files**.

Counts are computed with a 64-bit row hash and then verified exactly: every hash group with more
than one row is re-grouped on the real column values, so a hash collision cannot create or hide a
duplicate. Writes results/duplicates_probe.json.

Usage:
    python scripts/probe_duplicates.py
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from taxi_shock.config import load_config, path
from taxi_shock.io import connect

PROJECTED = [
    "tpep_pickup_datetime", "tpep_dropoff_datetime", "PULocationID", "DOLocationID",
    "trip_distance", "fare_amount", "total_amount", "passenger_count", "payment_type",
    "cbd_congestion_fee",
]


def main() -> None:
    cfg = load_config()
    t0 = time.perf_counter()
    files = sorted(path("raw_yellow", cfg).glob("yellow_tripdata_*.parquet"))
    glob = (path("raw_yellow", cfg) / "yellow_tripdata_*.parquet").as_posix()
    con = connect(":memory:", read_only=False, cfg=cfg)
    con.execute("SET preserve_insertion_order=false")
    # union_by_name over all files so every file exposes the same column list (NULL where absent)
    con.execute(f"""CREATE VIEW src AS SELECT * FROM read_parquet('{glob}', filename=true,
                    union_by_name=true)""")
    raw_cols = [r[0] for r in con.execute("DESCRIBE src").fetchall() if r[0] != "filename"]
    full = ", ".join(f'"{c}"' for c in raw_cols)
    proj = ", ".join(f'"{c}"' for c in PROJECTED)

    per_file = []
    for f in files:
        month = f.stem.removeprefix("yellow_tripdata_")
        sel = f"FROM src WHERE filename = '{f.as_posix()}'"
        n = con.execute(f"SELECT count(*) {sel}").fetchone()[0]
        out = {"month": month, "rows": int(n)}
        for name, cols in (("full_within_file", full), ("projected_within_file", proj)):
            # hash groups with >1 row are candidates; exact regroup on the column values
            hash_dups, exact_dups = con.execute(f"""
                WITH h AS (SELECT {cols}, hash({cols}) AS hk {sel}),
                cand AS (SELECT * FROM h WHERE hk IN
                         (SELECT hk FROM h GROUP BY hk HAVING count(*) > 1))
                SELECT (SELECT count(*) - count(DISTINCT hk) FROM cand),
                       (SELECT count(*) FROM cand) -
                       (SELECT count(*) FROM (SELECT DISTINCT * EXCLUDE (hk) FROM cand))
            """).fetchone()
            out[name] = int(exact_dups)
            out[name + "_hash_agrees"] = bool(hash_dups == exact_dups)
        per_file.append(out)
        print(month, out, flush=True)

    # Cross-file: identical full raw rows that appear in more than one monthly file.
    cross_rows, cross_groups, n_oom = _cross_file(con, full)

    tot = {k: sum(r[k] for r in per_file) for k in
           ("rows", "full_within_file", "projected_within_file")}
    result = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": len(per_file),
        "raw_columns": raw_cols,
        "projected_columns": PROJECTED,
        "totals": {**tot, "full_cross_file_rows": cross_rows,
                   "full_cross_file_groups": cross_groups,
                   "out_of_month_rows_checked_cross_file": n_oom},
        "hash_agrees_everywhere": all(r["full_within_file_hash_agrees"]
                                      and r["projected_within_file_hash_agrees"]
                                      for r in per_file),
        "months_where_projected_differs_from_full": [
            r["month"] for r in per_file if r["projected_within_file"] != r["full_within_file"]],
        "per_file": per_file,
        "runtime_seconds": round(time.perf_counter() - t0, 1),
    }
    out = path("results", cfg) / "duplicates_probe.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_file"}, indent=2))


def _cross_file(con, full: str) -> tuple[int, int, int]:
    """Rows (and groups) whose full raw content appears in more than one file, verified exactly.

    Two copies of one row in different files share the same pickup timestamp, and calendar months
    are disjoint, so at least one copy is an *out-of-month* row of its file (pickup outside the
    file's calendar month). It therefore suffices to match the out-of-month rows (a small set)
    against all rows with the same pickup timestamp and full-row hash in another file; candidate
    groups are then re-grouped on the real column values.
    """
    month_expr = ("strptime(regexp_extract(filename, 'yellow_tripdata_(\\d{4}-\\d{2})', 1), "
                  "'%Y-%m')")
    con.execute(f"""CREATE TEMP TABLE oom AS
        SELECT tpep_pickup_datetime AS pu, hash({full}) AS hk, filename
        FROM src
        WHERE tpep_pickup_datetime IS NULL
           OR tpep_pickup_datetime < {month_expr}
           OR tpep_pickup_datetime >= {month_expr} + INTERVAL 1 MONTH""")
    con.execute(f"""CREATE TEMP TABLE pairs AS
        SELECT DISTINCT o.hk
        FROM oom o
        JOIN (SELECT tpep_pickup_datetime AS pu, hash({full}) AS hk, filename FROM src
              WHERE tpep_pickup_datetime IN (SELECT DISTINCT pu FROM oom)
                 OR tpep_pickup_datetime IS NULL) a
          ON a.pu IS NOT DISTINCT FROM o.pu AND a.hk = o.hk AND a.filename <> o.filename""")
    n_oom = con.execute("SELECT count(*) FROM oom").fetchone()[0]
    print(f"out-of-month rows: {n_oom}; cross-file hash candidates: "
          f"{con.execute('SELECT count(*) FROM pairs').fetchone()[0]}", flush=True)
    if con.execute("SELECT count(*) FROM pairs").fetchone()[0] == 0:
        return 0, 0, int(n_oom)
    rows, groups = con.execute(f"""
        WITH cand AS (SELECT {full}, filename FROM src
                      WHERE hash({full}) IN (SELECT hk FROM pairs)),
        g AS (SELECT {full}, count(*) AS n_rows, count(DISTINCT filename) AS n_files
              FROM cand GROUP BY {full})
        SELECT coalesce(sum(n_rows) FILTER (WHERE n_files > 1), 0),
               count(*) FILTER (WHERE n_files > 1)
        FROM g""").fetchone()
    return int(rows), int(groups), int(n_oom)


if __name__ == "__main__":
    main()
