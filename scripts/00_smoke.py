"""End-to-end smoke pipeline on one sample month, timed stage by stage.

download month -> lookups -> weather -> dbt build (run + test; uses the committed
config/zones_cbd.csv) -> data-quality results -> seasonal-naive backtest ->
placeholder figure. Writes results/smoke/smoke_run.json and fails if the total runtime exceeds
smoke.max_runtime_minutes.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime

import pandas as pd

from taxi_shock.config import load_config, path, repo_root


def main() -> None:
    cfg = load_config()
    sm = cfg["smoke"]
    month = pd.Period(sm["month"], "M")
    py = sys.executable
    stages = [
        ("download", [py, "scripts/01_download.py", "--months", sm["month"]]),
        ("weather", [py, "scripts/02_weather.py", "--start", month.start_time.date().isoformat(),
                     "--end", month.end_time.date().isoformat()]),
        ("dbt_build", [py, "scripts/03_dbt.py", "build", "--smoke"]),
        ("data_results", [py, "scripts/03b_data_results.py", "--smoke"]),
        ("backtest", [py, "scripts/04_backtest.py", "--smoke"]),
        ("figure", [py, "scripts/09_figures.py", "--smoke"]),
    ]
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    for name, cmd in stages:
        s = time.perf_counter()
        print(f"[smoke] {name}: {' '.join(cmd[1:])}", flush=True)
        subprocess.run(cmd, cwd=repo_root(), check=True)
        timings[name] = round(time.perf_counter() - s, 1)
    total = round(time.perf_counter() - t0, 1)
    limit = float(sm["max_runtime_minutes"]) * 60
    report = {
        "month": sm["month"],
        "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "stage_seconds": timings,
        "total_seconds": total,
        "limit_seconds": limit,
        "passed": total <= limit,
        "python": platform.python_version(),
        "machine": platform.machine(),
    }
    out = path("smoke.results_dir", cfg)
    out.mkdir(parents=True, exist_ok=True)
    (out / "smoke_run.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[smoke] total {total}s (limit {limit:.0f}s)")
    if total > limit:
        sys.exit(f"smoke exceeded {limit:.0f}s")


if __name__ == "__main__":
    main()
