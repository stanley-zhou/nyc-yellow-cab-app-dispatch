"""Run dbt with every var and DuckDB setting taken from config/project.yaml.

dbt_project.yml carries identical defaults so that `dbt test` also works by hand from dbt/;
tests/test_config_sync.py fails if the two drift apart.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from taxi_shock.config import load_config, path, repo_root


def dbt_vars(cfg: dict[str, Any], yellow_glob: str | None = None) -> dict[str, Any]:
    """dbt vars derived from config.

    Paths are absolute at run time so that views over raw files resolve from any working
    directory. They exist only in the git-ignored warehouse, never in the repository.
    """

    def rel(p: Path) -> str:
        return p.resolve().as_posix()

    q = cfg["quality"]
    return {
        "yellow_glob": yellow_glob or rel(path("raw_yellow", cfg)) + "/yellow_tripdata_*.parquet",
        "weather_glob": rel(path("raw_weather", cfg)) + "/open_meteo_*.csv",
        "zone_lookup_csv": rel(path("raw_lookup", cfg)) + "/taxi_zone_lookup.csv",
        "timezone": cfg["timezone"],
        "zone_id_min": int(cfg["zones"]["valid_ids"][0]),
        "zone_id_max": int(cfg["zones"]["valid_ids"][1]),
        "straggler_days": int(q["straggler_days"]),
        "min_duration_minutes": int(q["min_duration_minutes"]),
        "max_duration_hours": int(q["max_duration_hours"]),
        "max_trip_distance_miles": int(q["max_trip_distance_miles"]),
    }


def dbt_env(cfg: dict[str, Any], warehouse: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        TAXI_SHOCK_WAREHOUSE=str(warehouse),
        TAXI_SHOCK_DUCKDB_MEMORY=str(cfg["duckdb"]["memory_limit"]),
        TAXI_SHOCK_DUCKDB_THREADS=str(cfg["duckdb"]["threads"]),
        TAXI_SHOCK_TZ=str(cfg["timezone"]),
        DBT_PROFILES_DIR=str(repo_root() / "dbt"),
        DO_NOT_TRACK="1",
    )
    return env


def run_dbt(args: list[str], smoke: bool = False, cfg: dict[str, Any] | None = None) -> None:
    """Invoke `dbt <args>` inside dbt/ with config-derived vars; raise on failure."""
    cfg = cfg or load_config()
    dbt_dir = repo_root() / "dbt"
    if smoke:
        warehouse = path("smoke_warehouse", cfg)
        month_file = cfg["sources"]["yellow_path"].format(month=cfg["smoke"]["month"])
        yglob = (path("raw_yellow", cfg) / Path(month_file).name).resolve().as_posix()
        dvars = dbt_vars(cfg, yellow_glob=yglob)
    else:
        warehouse = path("warehouse", cfg)
        dvars = dbt_vars(cfg)
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    dbt_bin = Path(sys.executable).with_name("dbt")
    cmd = [str(dbt_bin), *args]
    if args and args[0] in {"run", "test", "build", "compile", "seed", "show"}:
        cmd += ["--vars", json.dumps(dvars)]
    env = dbt_env(cfg, warehouse)
    if not (dbt_dir / "dbt_packages").exists() and args[:1] != ["deps"]:
        subprocess.run([str(dbt_bin), "deps"], cwd=dbt_dir, env=env, check=True)
    subprocess.run(cmd, cwd=dbt_dir, env=env, check=True)
