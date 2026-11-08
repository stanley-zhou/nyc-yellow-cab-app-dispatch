"""Validate the Chronos-2 outputs copied back from Colab into results/ (PLAN Phase 2, model 4).

Checks, each recorded in results/chronos_import_check.json (the script exits non-zero on any
failure):
  - chronos_run.json is a full run (not --dry-run) of exactly this bundle: input-file sha256s
    equal data/processed/chronos/manifest.json, and the script sha256 equals the manifest's
    `colab_script_sha256` (the committed scripts/05_chronos_colab.py);
  - completeness: every (variant, modeled zone, grid hour of every origin day) exactly once,
    test-period origins in chronos_forecasts.parquet and later origins in the _post file;
  - quantiles finite, non-crossing count reported (q10 <= q50 <= q90), horizon = hour + 1.

Usage:
    python scripts/05b_chronos_import.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.config import load_config, path, repo_root


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    ch = cfg["chronos"]
    root = repo_root()
    manifest = json.loads((path("processed", cfg) / "chronos" / "manifest.json").read_text())
    run = json.loads((root / ch["run_record"]).read_text())
    test = pd.read_parquet(root / ch["test_output"])
    post = pd.read_parquet(root / ch["post_output"])
    cov = pd.read_parquet(path("processed", cfg) / "chronos" / "covariates.parquet")
    hours = pd.DatetimeIndex(cov["hour_ts"])
    zones = sorted(pd.read_parquet(path("processed", cfg) / "chronos" / "pickups.parquet",
                                   columns=["zone_id"])["zone_id"].unique())
    qcols = [f"q{round(q * 100):02d}" for q in manifest["quantiles"]]
    checks: dict[str, object] = {}

    checks["full_run"] = run.get("dry_run") is False
    checks["inputs_match_manifest"] = all(
        run["input_files"].get(k, {}).get("sha256") == v["sha256"]
        for k, v in manifest["files"].items())
    checks["script_matches_manifest"] = run.get("script_sha256") == \
        manifest["colab_script_sha256"]

    origins = pd.date_range(*manifest["origins"], freq="D")
    lo, hi = (pd.Timestamp(x) for x in manifest["test_period"])
    day = hours.normalize()
    expected = []
    for v in manifest["variants"]:
        for o in origins:
            ts = hours[day == o]
            expected.append(pd.DataFrame({"variant": v, "origin": o,
                                          "target_ts": np.repeat(ts.to_numpy(), len(zones)),
                                          "zone_id": np.tile(zones, len(ts))}))
    exp = pd.concat(expected, ignore_index=True)
    key = ["variant", "zone_id", "target_ts"]
    for name, df, mask in (("test", test, (exp["origin"] >= lo) & (exp["origin"] <= hi)),
                           ("post", post, ~((exp["origin"] >= lo) & (exp["origin"] <= hi)))):
        e = exp[mask]
        got = df[key + ["origin"]].astype({"zone_id": "int64", "variant": "object"})
        m = e.astype({"zone_id": "int64"}).merge(got, on=key + ["origin"], how="outer",
                                                indicator=True)
        checks[f"{name}_rows"] = int(len(df))
        checks[f"{name}_expected_rows"] = int(len(e))
        checks[f"{name}_missing"] = int((m["_merge"] == "left_only").sum())
        checks[f"{name}_unexpected"] = int((m["_merge"] == "right_only").sum())
        checks[f"{name}_duplicates"] = int(df.duplicated(key).sum())
        checks[f"{name}_quantiles_finite"] = bool(np.isfinite(df[qcols].to_numpy()).all())
        checks[f"{name}_quantile_crossings"] = int(
            ((df[qcols[0]] > df[qcols[1]]) | (df[qcols[1]] > df[qcols[2]])).sum())
        checks[f"{name}_horizon_ok"] = bool(
            (df["horizon"] == pd.to_datetime(df["target_ts"]).dt.hour + 1).all())

    must = ["full_run", "inputs_match_manifest", "script_matches_manifest"] + [
        f"{n}_{c}" for n in ("test", "post") for c in ("quantiles_finite", "horizon_ok")]
    zero = [f"{n}_{c}" for n in ("test", "post") for c in ("missing", "unexpected",
                                                           "duplicates")]
    ok = all(checks[k] for k in must) and all(checks[k] == 0 for k in zero)
    result = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
              "passed": ok, "checks": checks,
              "run": {k: run.get(k) for k in ("generated_utc", "model_id", "model_revision",
                                              "environment", "n_zones", "n_origins",
                                              "variants")}}
    out = path("results", cfg) / "chronos_import_check.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    logging.info("chronos import check: %s -> %s", "PASS" if ok else "FAIL", out)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
