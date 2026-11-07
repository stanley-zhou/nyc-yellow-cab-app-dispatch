"""Checkpoint 0 facts: machine resources and the measured size of the full download.

Writes results/machine_resources.json and results/download_plan.csv (+ summary JSON). Sizes are
Content-Length values from HEAD requests to the TLC CDN; nothing is downloaded.

Units are explicit in every key (PLAN amendment, Phase 1 item 4): `_gb_decimal` = 10^9 bytes (what
the download plan uses), `_gib` = 2^30 bytes (what `df -h` and `free -g` print).

Usage:
    python scripts/checkpoint0.py                  # machine facts + download plan
    python scripts/checkpoint0.py --machine-only   # refresh results/machine_resources.json only
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.download import month_range, plan_downloads

GB = 1e9
GIB = 2**30


def mem_total_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--machine-only", action="store_true")
    machine_only = ap.parse_args().machine_only
    cfg = load_config()
    out = path("results", cfg)
    out.mkdir(parents=True, exist_ok=True)

    disks = {}
    for label, p in {"repo_filesystem": repo_root(), "windows_c_drive": Path("/mnt/c")}.items():
        if p.exists():
            du = shutil.disk_usage(p)
            disks[label] = {"mount_probe": label,
                            "total_gb_decimal": round(du.total / GB, 1),
                            "free_gb_decimal": round(du.free / GB, 1),
                            "total_gib": round(du.total / GIB, 1),
                            "free_gib": round(du.free / GIB, 1)}
    resources = {
        "checked_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "mem_total_gb_decimal": round((mem_total_bytes() or 0) / GB, 2),
        "mem_total_gib": round((mem_total_bytes() or 0) / GIB, 2),
        "disks": disks,
        # The WSL ext4 virtual disk reports a large nominal size but grows inside a VHDX file on
        # C:, so free space on C: is the real ceiling for data/ (CLAUDE.md, Checkpoint 0).
        "effective_ceiling": {
            "source": "windows_c_drive" if "windows_c_drive" in disks else "repo_filesystem",
            "free_gb_decimal": (disks.get("windows_c_drive")
                                or disks["repo_filesystem"])["free_gb_decimal"],
            "free_gib": (disks.get("windows_c_drive") or disks["repo_filesystem"])["free_gib"],
        },
    }
    (out / "machine_resources.json").write_text(json.dumps(resources, indent=2) + "\n")
    if machine_only:
        print(json.dumps(resources, indent=2))
        return

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
            "total_gb_decimal": round(float(ok["bytes"].sum()) / GB, 2),
            "largest_file_gb_decimal": round(float(ok["bytes"].max()) / GB, 3),
        }
    (out / "download_plan_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"resources": resources, "download_plan": summary}, indent=2))


if __name__ == "__main__":
    main()
