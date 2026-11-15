"""Rebuild the DuckDB warehouse into a fresh file to reclaim space (Phase 7 deferred item).

Listed in reports/deferred_items.md (PLAN Phase-1 follow-up 6).

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
space on C:) was 36 GB, and recomputes data that the copy reproduces exactly.

Reads: the warehouse (config `paths.warehouse`) and dbt/target/manifest.json.
Writes: the copy <warehouse>.compact.duckdb (renamed to the warehouse with --swap) and
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


def inventory(con: duckdb.DuckDBPyConnection, db: str) -> dict[str, str]:
    """Objects of schema main in catalog `db` (a file-backed database's catalog is named after
    the file stem, not "main")."""
    rows = con.execute("select table_name, table_type from information_schema.tables "
                       "where table_catalog = ? and table_schema = 'main'", [db]).fetchall()
    return dict(rows)


def size(con: duckdb.DuckDBPyConnection, db: str) -> dict:
    r = con.execute("select database_size, total_blocks, used_blocks, free_blocks from "
                    "pragma_database_size() where database_name = ?", [db]).fetchone()
    return dict(zip(("database_size", "total_blocks", "used_blocks", "free_blocks"), r,
                    strict=True))


def compact_into(con: duckdb.DuckDBPyConnection, db: str, nodes: set[str], new
                 ) -> tuple[dict, dict, dict, dict, dict, bool]:
    """Drop the objects of `db` that are not in `nodes`, copy the rest into the file `new` and
    verify the copy: same object set, same row count in every table."""
    before = size(con, db)
    objs = inventory(con, db)
    if not objs:
        raise SystemExit(f"no objects found in catalog {db!r}; refusing")
    stale = {k: v for k, v in objs.items() if k not in nodes}
    for name, kind in stale.items():
        LOG.info("dropping stale %s %s (not a dbt node)", kind, name)
        con.execute(f'drop {"view" if kind == "VIEW" else "table"} "{db}"."{name}"')
    con.execute(f"attach '{new}' as fresh")
    con.execute(f'copy from database "{db}" to fresh')
    con.execute("checkpoint fresh")
    after = size(con, "fresh")
    live = inventory(con, db)
    copied = inventory(con, "fresh")
    counts = {}
    for name, kind in live.items():
        if kind != "BASE TABLE":
            continue
        a = con.execute(f'select count(*) from "{db}"."{name}"').fetchone()[0]
        b = con.execute(f'select count(*) from fresh."{name}"').fetchone()[0]
        counts[name] = {"rows": int(a), "rows_copy": int(b)}
    con.execute("detach fresh")
    ok = (copied == live and bool(counts)
          and all(v["rows"] == v["rows_copy"] for v in counts.values()))
    return stale, before, after, counts, live, ok


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
        stale, before, after, counts, live, ok = compact_into(con, wh.stem, nodes, new)
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
