"""Prove `make smoke` works on a clean clone: export the committed tree (HEAD) into an empty
temporary directory, run `make setup && make smoke` there, and record the result in
results/smoke/smoke_run_clean_clone.json. Uncommitted changes are deliberately not tested.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from taxi_shock.config import load_config, path, repo_root


def main() -> None:
    cfg = load_config()
    root = repo_root()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                            capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True,
                           capture_output=True, text=True).stdout.strip() != ""
    tmp = Path(tempfile.mkdtemp(prefix="taxi_shock_clean_"))
    try:
        archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=root,
                                 check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
            tf.extractall(tmp, filter="data")
        # results/smoke and the smoke figure are tracked; remove them so the run must recreate them
        shutil.rmtree(tmp / cfg["smoke"]["results_dir"], ignore_errors=True)
        shutil.rmtree(tmp / cfg["smoke"]["figures_dir"], ignore_errors=True)
        t0 = time.perf_counter()
        subprocess.run(["make", "setup"], cwd=tmp, check=True)
        setup_s = round(time.perf_counter() - t0, 1)
        subprocess.run(["make", "smoke"], cwd=tmp, check=True)
        run = json.loads((tmp / cfg["smoke"]["results_dir"] / "smoke_run.json").read_text())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    report = {
        **run,
        "git_commit": commit,
        "working_tree_dirty_at_run": dirty,
        "setup_seconds": setup_s,
        "context": "git archive HEAD into an empty temp dir, then make setup && make smoke; "
                   "setup_seconds depends on the local uv package cache",
    }
    out = path("smoke.results_dir", cfg) / "smoke_run_clean_clone.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not run.get("passed"):
        raise SystemExit("clean-clone smoke exceeded its time limit")


if __name__ == "__main__":
    main()
