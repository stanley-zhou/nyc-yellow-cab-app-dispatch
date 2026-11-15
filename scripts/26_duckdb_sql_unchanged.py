"""Check that the dialect macros of the Snowflake port left the DuckDB SQL unchanged.

Evidence for running the dbt project on Snowflake (PLAN Amendment 4, E3).

Writes results/e3_duckdb_sql_check.json.

Compiles the dbt project for the DuckDB target twice, at `--base` (the commit before the
Snowflake port) and at the working tree, compares every compiled node with comments and
whitespace removed, and, for each differing model, checks in the DuckDB warehouse that the two
queries return the same rows (EXCEPT ALL in both directions). Differing tests are listed;
`dbt test` runs them.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.dbt_runner import dbt_env, dbt_vars
from taxi_shock.io import connect


def compile_project(project: Path, target_path: Path, cfg: dict) -> Path:
    env = dbt_env(cfg, path("warehouse", cfg))
    env["DBT_PROFILES_DIR"] = str(project)
    subprocess.run([str(Path(sys.executable).with_name("dbt")), "compile", "--vars",
                    json.dumps(dbt_vars(cfg)), "--target-path", str(target_path)],
                   cwd=project, env=env, check=True, capture_output=True)
    return target_path / "compiled" / "taxi_shock"


def norm(sql: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", sql)).strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--base", required=True, help="git commit before the port")
    args = ap.parse_args()
    cfg = load_config()
    root = repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        arch = subprocess.run(["git", "archive", args.base, "dbt"], cwd=root, check=True,
                              capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tmp)], input=arch, check=True)
        shutil.copytree(root / "dbt" / "dbt_packages", tmp / "dbt" / "dbt_packages")
        old = compile_project(tmp / "dbt", tmp / "t_old", cfg)
        new = compile_project(root / "dbt", tmp / "t_new", cfg)
        fo = {p.relative_to(old).as_posix(): p.read_text() for p in old.rglob("*.sql")}
        fn = {p.relative_to(new).as_posix(): p.read_text() for p in new.rglob("*.sql")}
        differ = sorted(k for k in fo if k in fn and norm(fo[k]) != norm(fn[k]))
        checks = {}
        with connect(path("warehouse", cfg), cfg=cfg) as con:
            for k in differ:
                if not k.startswith("models/"):
                    continue
                a, b = fo[k], fn[k]
                n = con.execute(f"select (select count(*) from (({a}) except all ({b}))), "
                                f"(select count(*) from (({b}) except all ({a}))), "
                                f"(select count(*) from ({a}))").fetchone()
                checks[k] = {"old_except_new": int(n[0]), "new_except_old": int(n[1]),
                             "rows": int(n[2]), "same_rows": n[0] == 0 and n[1] == 0}
    rec = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "base_commit": args.base, "target": "duckdb",
           "nodes_old": len(fo), "nodes_new": len(fn),
           "only_old": sorted(set(fo) - set(fn)), "only_new": sorted(set(fn) - set(fo)),
           "nodes_differing": differ, "model_row_checks": checks,
           "duckdb_unchanged": (set(fo) == set(fn)
                                and all(v["same_rows"] for v in checks.values()))}
    out = path("results", cfg) / "e3_duckdb_sql_check.json"
    out.write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("nodes_old", "nodes_differing", "model_row_checks",
                                          "duckdb_unchanged")}, indent=1))


if __name__ == "__main__":
    main()
