"""Checkpoint 0 facts: machine resources and the measured size of the full download.

Writes results/machine_resources.json and results/download_plan.csv (+ summary JSON). Sizes are
Content-Length values from HEAD requests to the TLC CDN; nothing is downloaded.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.download import month_range, plan_downloads

GB = 1e9


def mem_total_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def main() -> None:
    cfg = load_config()
    out = path("results", cfg)
    out.mkdir(parents=True, exist_ok=True)

    disks = {}
    for label, p in {"repo_filesystem": repo_root(), "windows_c_drive": Path("/mnt/c")}.items():
        if p.exists():
            du = shutil.disk_usage(p)
            disks[label] = {"mount_probe": label, "total_gb": round(du.total / GB, 1),
                            "free_gb": round(du.free / GB, 1)}
    resources = {
        "checked_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "mem_total_gb": round((mem_total_bytes() or 0) / GB, 2),
        "disks": disks,
        # The WSL ext4 virtual disk reports a large nominal size but grows inside a VHDX file on
        # C:, so free space on C: is the real ceiling for data/ (CLAUDE.md, Checkpoint 0).
        "effective_ceiling": {
            "source": "windows_c_drive" if "windows_c_drive" in disks else "repo_filesystem",
            "free_gb": (disks.get("windows_c_drive") or disks["repo_filesystem"])["free_gb"],
        },
    }
    (out / "machine_resources.json").write_text(json.dumps(resources, indent=2) + "\n")

    src = cfg["sources"]
    plan = plan_downloads({
        "yellow_path": month_range(*cfg["data"]["yellow_months"]),
        "hvfhv_path": month_range(*src["hvfhv_months"]),
    }, cfg)
    plan.to_csv(out / "download_plan.csv", index=False)
    summary = {}
    for ds, d in plan.groupby("dataset"):
        ok = d[d["http_status"] == 200]
        summary[ds] = {
            "months_requested": int(len(d)),
            "months_available": int(len(ok)),
            "months_missing": d.loc[d["http_status"] != 200, "month"].tolist(),
            "total_gb": round(float(ok["bytes"].sum()) / GB, 2),
            "largest_file_gb": round(float(ok["bytes"].max()) / GB, 3),
        }
    (out / "download_plan_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"resources": resources, "download_plan": summary}, indent=2))


if __name__ == "__main__":
    main()
