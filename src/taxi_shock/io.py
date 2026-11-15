"""DuckDB connections with the project's memory discipline, and panel readers.

The readers open the warehouse read-only (`fct_hourly_zone_demand`, `int_hours`, `stg_weather`,
`holidays_ny`) and return DataFrames; `connect` creates the configured DuckDB spill directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from taxi_shock.config import load_config, path


def connect(db_path: Path | str, read_only: bool = True, cfg: dict[str, Any] | None = None):
    """Open DuckDB with `memory_limit` / `threads` from config."""
    cfg = cfg or load_config()
    con = duckdb.connect(str(db_path), read_only=read_only)
    con.execute(f"SET memory_limit='{cfg['duckdb']['memory_limit']}'")
    con.execute(f"SET threads={int(cfg['duckdb']['threads'])}")
    con.execute(f"SET TimeZone='{cfg['timezone']}'")
    tmp = path("duckdb_tmp", cfg)
    tmp.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{tmp.as_posix()}'")
    con.execute(f"SET max_temp_directory_size='{cfg['duckdb']['max_temp_directory_size']}'")
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


def read_exog(db_path: Path | str, start: str | None = None, end: str | None = None,
              cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """City-wide exogenous table indexed by local hour_ts: is_holiday and the observed weather
    columns of `stg_weather` (the same sources as `features_demand`), for [start, end)."""
    from taxi_shock.features import WEATHER_FEATURES

    where, params = [], []
    if start:
        where.append("h.hour_ts >= CAST(? AS TIMESTAMP)")
        params.append(start)
    if end:
        where.append("h.hour_ts < CAST(? AS TIMESTAMP)")
        params.append(end)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    cols = ", ".join(f"w.{c}" for c in WEATHER_FEATURES)
    with connect(db_path, read_only=True, cfg=cfg) as con:
        df = con.execute(f"""
            SELECT h.hour_ts, hol.date IS NOT NULL AS is_holiday, {cols}
            FROM int_hours h
            LEFT JOIN stg_weather w USING (hour_ts)
            LEFT JOIN (SELECT DISTINCT date FROM holidays_ny) hol
                   ON hol.date = CAST(h.hour_ts AS DATE)
            {clause} ORDER BY 1""", params).df()
    return df.set_index("hour_ts")


def read_modeled_panel(db_path: Path | str, zone_ids: list[int], start: str, end: str,
                       cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """`fct_hourly_zone_demand` restricted to `zone_ids` for [start, end)."""
    df = read_hourly_demand(db_path, start, end, cfg=cfg)
    return df[df["zone_id"].isin(zone_ids)].reset_index(drop=True)
