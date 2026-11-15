"""Import and validate the Chronos-2 outputs returned from Colab (PLAN Phase 2, model 4).

Two runs of the same Colab script exist (taxi_shock.chronos_runs): `main` (origins 2024-01-01 ->
2026-09-30, whose files Stanley copies straight into results/) and the calibration run
`calib_2023` (origins 2023-10-01 -> 2023-12-31; its three files go into
`chronos.calibration_run.inbox`).

    python scripts/05b_chronos_import.py                    validate what is in results/
    python scripts/05b_chronos_import.py --run calib_2023   validate the inbox files of that run,
                                                            then merge them into results/

Merging (only after the run's own checks pass): its rows replace any earlier rows of the same
run in `chronos.test_output` / `chronos.post_output`, tagged in a `run` column (idempotent; the
main run's rows are never touched), and its chronos_run.json is kept as the run's own record
(`chronos.calibration_run.run_record`); the main run keeps `chronos.run_record`.

Reads the run's bundle manifest (data/processed/chronos*/manifest.json) and its three returned
files. Writes results/chronos_import_check.json; when it merges a calibration run, also
results/chronos_forecasts.parquet, results/chronos_forecasts_post.parquet and that run's record
(results/chronos_run_calib_2023.json).

Checks per run, all in results/chronos_import_check.json (exit non-zero on any failure):
  - full run (not --dry-run) of exactly that run's bundle: input sha256s equal its manifest,
    script sha256 equals the manifest's `colab_script_sha256`; for the calibration run also
    the same script as the main run;
  - completeness: every (variant, modeled zone, grid hour of every origin day) exactly once;
  - quantiles finite; crossings counted (the evaluation sorts them); horizon = hour + 1.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from taxi_shock.chronos_runs import MAIN, RunSpec, merge_run, run_spec, validate_run, with_run
from taxi_shock.config import load_config, path, repo_root

RUN_FILES = ("chronos_forecasts.parquet", "chronos_forecasts_post.parquet", "chronos_run.json")


def bundle_grid(spec: RunSpec) -> tuple[dict, pd.DatetimeIndex, list[int]]:
    manifest = json.loads((spec.bundle_dir / "manifest.json").read_text())
    hours = pd.DatetimeIndex(pd.read_parquet(spec.bundle_dir / "covariates.parquet",
                                             columns=["hour_ts"])["hour_ts"])
    zones = sorted(pd.read_parquet(spec.bundle_dir / "pickups.parquet",
                                   columns=["zone_id"])["zone_id"].unique())
    return manifest, hours, zones


def check(spec: RunSpec, run: dict, test: pd.DataFrame, post: pd.DataFrame,
          main_manifest: dict) -> dict:
    manifest, hours, zones = bundle_grid(spec)
    ok, checks = validate_run(manifest, run, test, post, hours, zones)
    if spec.name != MAIN:
        checks["same_script_as_main"] = (manifest["colab_script_sha256"]
                                         == main_manifest["colab_script_sha256"])
        ok = ok and checks["same_script_as_main"]
    return {"passed": ok, "checks": checks,
            "run": {k: run.get(k) for k in ("generated_utc", "model_id", "model_revision",
                                            "environment", "n_zones", "n_origins",
                                            "variants")}}


def _write_atomic(df: pd.DataFrame, f: Path) -> None:
    tmp = f.with_name(f".{f.name}.tmp")
    df.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None,
                    help="merge this run's inbox files first (the calibration run's name)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    ch, root = cfg["chronos"], repo_root()
    main_spec = run_spec(cfg, MAIN)
    main_manifest = bundle_grid(main_spec)[0]
    report: dict[str, dict] = {}

    if args.run is not None:
        spec = run_spec(cfg, args.run)
        if spec.inbox is None:
            raise SystemExit("the main run is validated in place (no --run needed)")
        missing = [n for n in RUN_FILES if not (spec.inbox / n).exists()]
        if missing:
            raise SystemExit(f"{spec.inbox}: missing {', '.join(missing)}")
        run = json.loads((spec.inbox / "chronos_run.json").read_text())
        new_test = pd.read_parquet(spec.inbox / "chronos_forecasts.parquet")
        new_post = pd.read_parquet(spec.inbox / "chronos_forecasts_post.parquet")
        inbox_check = check(spec, run, new_test, new_post, main_manifest)
        if not inbox_check["passed"]:
            logging.error("%s inbox check FAILED: %s", spec.name, inbox_check["checks"])
            sys.exit(1)
        for out, new in ((root / ch["test_output"], new_test), (root / ch["post_output"],
                                                                new_post)):
            _write_atomic(merge_run(pd.read_parquet(out), new, spec.name), out)
        spec.run_record.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(spec.inbox / "chronos_run.json", spec.run_record)
        logging.info("%s: %d test-file rows merged into %s; run record %s", spec.name,
                     len(new_test), ch["test_output"], spec.run_record.name)

    # validate every run now present in the result files
    test = with_run(pd.read_parquet(root / ch["test_output"]))
    post = with_run(pd.read_parquet(root / ch["post_output"]))
    names = [MAIN] + sorted(set(test["run"]) - {MAIN})
    for name in names:
        spec = run_spec(cfg, name)
        run = json.loads(spec.run_record.read_text())
        report[name] = check(spec, run, test[test["run"] == name].drop(columns="run"),
                             post[post["run"] == name].drop(columns="run"), main_manifest)
    ok = all(r["passed"] for r in report.values())
    result = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
              "passed": ok, "runs": report}
    out = path("results", cfg) / "chronos_import_check.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    logging.info("chronos import check (%s): %s -> %s", ", ".join(names),
                 "PASS" if ok else "FAIL", out)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
