"""Phase 7 deferred item (PLAN Phase-1 follow-up 6): rebuild the warehouse into a fresh file.

Staging models are already views over the raw Parquet (dbt_project.yml); the intermediate models
that are tables stay tables (each is read by several marts, so a view would recompute it, e.g.
the de-duplication in int_trips_flagged). The space to reclaim is DuckDB's free blocks: a DuckDB
file never shrinks when tables are rebuilt, so after many dbt runs about half the file is free
blocks. This script

  1. lists the objects in the warehouse that are not a node of the dbt manifest
     (dbt/target/manifest.json) - stale views of removed models - and drops them;
  2. copies every remaining object into a fresh file (ATTACH + COPY FROM DATABASE), which
     writes only live data;
  3. verifies every table's row count and every view's presence in the copy;
  4. with --swap, replaces the warehouse by the copy (the old file is kept as
     <warehouse>.pre_compaction until --delete-old, so nothing is deleted unverified).

A full rebuild from the raw files (`make dbt` into an empty file) was rejected: it needs a second
warehouse-sized file plus up to 15 GB of DuckDB spill on the WSL virtual disk, whose ceiling (free
space on C:) was 36 GB, and recomputes data that the copy reproduces exactly. Writes
results/warehouse_compaction.json.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime

import duckdb

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect

LOG = logging.getLogger("compact")


def inventory(con: duckdb.DuckDBPyConnection, db: str = "main") -> dict[str, str]:
    rows = con.execute("select table_name, table_type from information_schema.tables "
                       "where table_catalog = ? and table_schema = 'main'", [db]).fetchall()
    return dict(rows)


def size(con: duckdb.DuckDBPyConnection, db: str) -> dict:
    r = con.execute("select database_size, total_blocks, used_blocks, free_blocks from "
                    "pragma_database_size() where database_name = ?", [db]).fetchone()
    return dict(zip(("database_size", "total_blocks", "used_blocks", "free_blocks"), r,
                    strict=True))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--swap", action="store_true", help="replace the warehouse by the copy")
    ap.add_argument("--delete-old", action="store_true",
                    help="delete <warehouse>.pre_compaction (after a verified --swap)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    wh = path("warehouse", cfg)
    new = wh.with_name(wh.stem + ".compact.duckdb")
    old = wh.with_name(wh.name + ".pre_compaction")
    out_f = path("results", cfg) / "warehouse_compaction.json"

    if args.delete_old:
        rec = json.loads(out_f.read_text())
        if not (rec.get("verified") and rec.get("swapped") and old.exists()):
            raise SystemExit("refusing: no verified swap recorded, or no old file")
        old.unlink()
        rec["old_file_deleted_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
        out_f.write_text(json.dumps(rec, indent=2) + "\n")
        LOG.info("deleted %s", old.name)
        return

    manifest = json.loads((repo_root() / "dbt" / "target" / "manifest.json").read_text())
    nodes = {n.get("alias") or n["name"] for n in manifest["nodes"].values()
             if n["resource_type"] in ("model", "seed", "snapshot")}
    if new.exists():
        new.unlink()            # a leftover partial copy of this script (regenerable)
    with connect(wh, read_only=False, cfg=cfg) as con:
        before = size(con, wh.stem)
        objs = inventory(con)
        stale = {k: v for k, v in objs.items() if k not in nodes}
        for name, kind in stale.items():
            LOG.info("dropping stale %s %s (not a dbt node)", kind, name)
            con.execute(f'drop {"view" if kind == "VIEW" else "table"} "{name}"')
        con.execute(f"attach '{new}' as fresh")
        con.execute(f'copy from database "{wh.stem}" to fresh')
        con.execute("checkpoint fresh")
        after = size(con, "fresh")
        live = inventory(con)
        copied = inventory(con, "fresh")
        counts = {}
        for name, kind in live.items():
            if kind != "BASE TABLE":
                continue
            a = con.execute(f'select count(*) from "{wh.stem}"."{name}"').fetchone()[0]
            b = con.execute(f'select count(*) from fresh."{name}"').fetchone()[0]
            counts[name] = {"rows": int(a), "rows_copy": int(b)}
        con.execute("detach fresh")
    ok = (set(copied) == set(live)
          and all(v["rows"] == v["rows_copy"] for v in counts.values()))
    rec = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "method": "drop objects that are not dbt nodes, then ATTACH + COPY FROM DATABASE "
                     "into a fresh file",
           "stale_objects_dropped": stale, "before": before, "after": after,
           "tables": counts, "views": sorted(k for k, v in live.items() if v == "VIEW"),
           "verified": bool(ok), "swapped": False}
    if ok and args.swap:
        wh.rename(old)
        new.rename(wh)
        rec["swapped"] = True
        rec["old_file"] = old.name
    out_f.write_text(json.dumps(rec, indent=2) + "\n")
    LOG.info("before %s, after %s, verified %s, swapped %s", before["database_size"],
             after["database_size"], ok, rec["swapped"])
    if not ok:
        raise SystemExit("copy does not match the warehouse; nothing swapped")


if __name__ == "__main__":
    main()
