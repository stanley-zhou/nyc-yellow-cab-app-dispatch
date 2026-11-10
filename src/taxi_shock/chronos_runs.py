"""Chronos-2 Colab runs: their specification, validation and merge into the result files.

Two runs use the same Colab script (`scripts/05_chronos_colab.py`), each with its own bundle and
manifest:
  main        origins `chronos.origins` (2024-01-01 -> 2026-09-30): the Phase-2 test year in
              `chronos.test_output`, later origins in `chronos.post_output`
  calib_2023  origins `chronos.calibration_run.origins` (2023-10-01 -> 2023-12-31): only the
              trailing history of the rolling conformal calibration (Stanley, 2026-11-09)
Rows of both live in the result files with a `run` column; each run keeps its own run record.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from taxi_shock.config import repo_root

KEY = ["variant", "zone_id", "target_ts"]
MAIN = "main"


@dataclass(frozen=True)
class RunSpec:
    name: str
    origins: tuple[str, str]
    test_period: tuple[str, str]   # the Colab script writes these origins to its "test" file
    bundle_dir: Path
    bundle: Path
    run_record: Path               # where the run's chronos_run.json is kept in the repo
    inbox: Path | None             # where the returned files are dropped (None: results/)


def run_spec(cfg: dict, name: str = MAIN) -> RunSpec:
    ch, root = cfg["chronos"], repo_root()
    if name == MAIN:
        return RunSpec(MAIN, tuple(ch["origins"]),
                       tuple(cfg["forecast"]["backtest"]["pre_shock_test"]),
                       root / ch["bundle_dir"], root / ch["bundle"], root / ch["run_record"],
                       None)
    cr = ch["calibration_run"]
    if name != cr["name"]:
        raise ValueError(f"unknown Chronos run {name!r} (known: {MAIN}, {cr['name']})")
    # every origin of the calibration run goes to the script's "test" file; its post file is empty
    return RunSpec(cr["name"], tuple(cr["origins"]), tuple(cr["origins"]),
                   root / cr["bundle_dir"], root / cr["bundle"], root / cr["run_record"],
                   root / cr["inbox"])


def expected_rows(manifest: dict, hours: pd.DatetimeIndex, zones: list[int]) -> pd.DataFrame:
    """Every (variant, origin, target hour, zone) the run must contain."""
    origins = pd.date_range(*manifest["origins"], freq="D")
    day = hours.normalize()
    parts = []
    for v in manifest["variants"]:
        for o in origins:
            ts = hours[day == o]
            parts.append(pd.DataFrame({"variant": v, "origin": o,
                                       "target_ts": np.repeat(ts.to_numpy(), len(zones)),
                                       "zone_id": np.tile(zones, len(ts))}))
    return pd.concat(parts, ignore_index=True)


def validate_run(manifest: dict, run: dict, test: pd.DataFrame, post: pd.DataFrame,
                 hours: pd.DatetimeIndex, zones: list[int]) -> tuple[bool, dict]:
    """Checks of one run's returned files against its manifest; (passed, checks)."""
    qcols = [f"q{round(q * 100):02d}" for q in manifest["quantiles"]]
    checks: dict[str, object] = {
        "full_run": run.get("dry_run") is False,
        "inputs_match_manifest": all(
            run["input_files"].get(k, {}).get("sha256") == v["sha256"]
            for k, v in manifest["files"].items()),
        "script_matches_manifest": run.get("script_sha256") == manifest["colab_script_sha256"],
    }
    exp = expected_rows(manifest, hours, zones)
    lo, hi = (pd.Timestamp(x) for x in manifest["test_period"])
    in_test = (exp["origin"] >= lo) & (exp["origin"] <= hi)
    for name, df, mask in (("test", test, in_test), ("post", post, ~in_test)):
        e = exp[mask].astype({"zone_id": "int64"})
        got = df[KEY + ["origin"]].astype({"zone_id": "int64", "variant": "object"})
        m = e.merge(got, on=KEY + ["origin"], how="outer", indicator=True)
        checks[f"{name}_rows"] = int(len(df))
        checks[f"{name}_expected_rows"] = int(len(e))
        checks[f"{name}_missing"] = int((m["_merge"] == "left_only").sum())
        checks[f"{name}_unexpected"] = int((m["_merge"] == "right_only").sum())
        checks[f"{name}_duplicates"] = int(df.duplicated(KEY).sum())
        checks[f"{name}_quantiles_finite"] = bool(np.isfinite(df[qcols].to_numpy()).all())
        # counted, not rejected: the evaluation sorts quantiles per row like every model's
        checks[f"{name}_quantile_crossings"] = int(
            ((df[qcols[0]] > df[qcols[1]]) | (df[qcols[1]] > df[qcols[2]])).sum())
        checks[f"{name}_horizon_ok"] = bool(
            (df["horizon"] == pd.to_datetime(df["target_ts"]).dt.hour + 1).all())
    must = ["full_run", "inputs_match_manifest", "script_matches_manifest"] + [
        f"{n}_{c}" for n in ("test", "post") for c in ("quantiles_finite", "horizon_ok")]
    zero = [f"{n}_{c}" for n in ("test", "post") for c in ("missing", "unexpected",
                                                           "duplicates")]
    ok = all(checks[k] for k in must) and all(checks[k] == 0 for k in zero)
    return ok, checks


def with_run(df: pd.DataFrame) -> pd.DataFrame:
    """Result-file rows with a `run` column (files written before the calibration run have
    none: all their rows are the main run's)."""
    return df if "run" in df else df.assign(run=MAIN)


def merge_run(existing: pd.DataFrame, new: pd.DataFrame, name: str) -> pd.DataFrame:
    """Replace run `name`'s rows of a result file by `new` (idempotent); other runs untouched.
    Fails if the new rows overlap another run's (variant, zone, target hour)."""
    base = with_run(existing)
    keep = base[base["run"] != name]
    add = new.drop(columns=["run"], errors="ignore").assign(run=name)
    clash = keep[KEY].merge(add[KEY], on=KEY)
    if len(clash):
        raise ValueError(f"run {name}: {len(clash)} rows overlap another run's forecasts")
    out = pd.concat([keep, add[keep.columns]], ignore_index=True)
    return out.sort_values(["run", "variant", "origin", "zone_id", "target_ts"],
                           kind="stable").reset_index(drop=True)
