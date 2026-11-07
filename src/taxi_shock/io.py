"""DuckDB connections with the project's memory discipline, and panel readers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from taxi_shock.config import load_config


def connect(db_path: Path | str, read_only: bool = True, cfg: dict[str, Any] | None = None):
    """Open DuckDB with `memory_limit` / `threads` from config."""
    cfg = cfg or load_config()
    con = duckdb.connect(str(db_path), read_only=read_only)
    con.execute(f"SET memory_limit='{cfg['duckdb']['memory_limit']}'")
    con.execute(f"SET threads={int(cfg['duckdb']['threads'])}")
    con.execute(f"SET TimeZone='{cfg['timezone']}'")
    return con


def read_hourly_demand(
    db_path: Path | str,
    start: str | None = None,
    end: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Read `fct_hourly_zone_demand` (zone_id, hour_ts, pickups) for [start, end) local time."""
    where = []
    params: list[str] = []
    if start:
        where.append("hour_ts >= CAST(? AS TIMESTAMP)")
        params.append(start)
    if end:
        where.append("hour_ts < CAST(? AS TIMESTAMP)")
        params.append(end)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with connect(db_path, read_only=True, cfg=cfg) as con:
        df = con.execute(
            f"SELECT zone_id, hour_ts, pickups FROM fct_hourly_zone_demand {clause} "
            "ORDER BY zone_id, hour_ts",
            params,
        ).df()
    df["zone_id"] = df["zone_id"].astype("int32")
    df["pickups"] = df["pickups"].astype("float32")
    return df
