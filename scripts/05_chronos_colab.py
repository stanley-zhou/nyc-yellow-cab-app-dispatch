"""Chronos-2 zero-shot day-ahead forecasts (PLAN Phase 2, model 4). Runs on Google Colab (GPU).

Standalone on purpose: it needs only numpy, pandas, pyarrow, torch and chronos-forecasting, not the
`taxi_shock` package. Every setting (model, context length, quantiles, origins, covariates,
variants) comes from `manifest.json` in the bundle written locally by
`scripts/05a_chronos_export.py` from config/project.yaml; the script refuses to run if an input
file's sha256 differs from the manifest.

Task (README): at 00:00 of each day D, forecast pickups for each modeled zone for every local
hour of D. For origin D the model sees the last `context_hours` grid hours strictly before D
(`make_inputs`; tests/test_chronos_inputs.py proves nothing at or after the origin is used,
except the covariate values the variant declares known over the target day: calendar always,
observed weather only in the `weather_future` variant).

Work is cut into (variant, month of origins) chunks written to `<out-dir>/chunks/`; a chunk that
exists is skipped, so after a Colab disconnect the same command resumes. When every chunk exists
the outputs are merged and written to <out-dir>:
    chronos_forecasts.parquet       origins inside the Phase-2 test period
    chronos_forecasts_post.parquet  origins after it (Phases 3 and 5)
    chronos_run.json                versions, device, timings, input hashes

Usage (Colab):
    python 05_chronos_colab.py --bundle /content/bundle --out-dir /content/drive/MyDrive/x/out
    python 05_chronos_colab.py --bundle ... --out-dir ... --dry-run    # 2 zones x 2 origins
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("chronos_colab")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def qcol(q: float) -> str:
    return f"q{round(q * 100):02d}"


# ------------------------------------------------------------------------------------- inputs
def load_bundle(
    bundle: Path,
) -> tuple[dict, np.ndarray, pd.DatetimeIndex, np.ndarray, pd.DataFrame]:
    """manifest, zone ids, hour index, dense pickups matrix (zones x hours), covariates."""
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    for name, meta in manifest["files"].items():
        got = sha256(bundle / name)
        if got != meta["sha256"]:
            raise ValueError(f"{name}: sha256 {got} differs from manifest {meta['sha256']}")
    p = pd.read_parquet(bundle / "pickups.parquet")
    cov = pd.read_parquet(bundle / "covariates.parquet").set_index("hour_ts").sort_index()
    wide = p.pivot_table(index="zone_id", columns="hour_ts", values="pickups", aggfunc="sum")
    hours = pd.DatetimeIndex(wide.columns)
    if wide.isna().to_numpy().any():
        raise ValueError("pickups panel is not complete (zone x hour grid has holes)")
    if not cov.index.equals(hours):
        raise ValueError("covariate hours differ from the pickups hours")
    return manifest, wide.index.to_numpy(), hours, wide.to_numpy(dtype=np.float32), cov


def day_positions(hours: pd.DatetimeIndex, origin: pd.Timestamp) -> tuple[int, int]:
    """(first, end) positions of the grid hours of calendar day `origin` (23, 24 hours)."""
    # integer nanoseconds: avoids a NumPy generic-timedelta deprecation under pandas 2.x
    ns = hours.as_unit("ns").asi8
    start = pd.Timestamp(origin).as_unit("ns")
    lo = int(np.searchsorted(ns, start.value, side="left"))
    hi = int(np.searchsorted(ns, start.value + 86_400 * 10**9, side="left"))  # + 1 day
    return lo, hi


def make_inputs(y: np.ndarray, cov: pd.DataFrame, pos: int, n_h: int, context: int,
                past: list[str], future: list[str]) -> list[dict]:
    """One Chronos-2 input dict per zone (row of `y`) for the origin at grid position `pos`.

    target / past covariates: positions [pos - context, pos), strictly before the origin.
    future covariates: positions [pos, pos + n_h), only for the names in `future` (known over
    the target day by assumption of the variant). Names in `past` but not in `future` are
    past-only covariates. Chronos-2 requires future keys to be a subset of past keys."""
    if pos - context < 0:
        raise ValueError(f"not enough history: position {pos} < context {context}")
    if not set(future) <= set(past):
        raise ValueError("future covariates must also be past covariates")
    ctx = slice(pos - context, pos)
    fut = slice(pos, pos + n_h)
    past_cov = {c: cov[c].to_numpy(dtype=np.float32)[ctx] for c in past}
    fut_cov = {c: cov[c].to_numpy(dtype=np.float32)[fut] for c in future}
    out = []
    for row in y:
        d: dict = {"target": row[ctx].astype(np.float32), "past_covariates": past_cov}
        if fut_cov:
            d["future_covariates"] = fut_cov
        out.append(d)
    return out


def variant_covariates(manifest: dict, variant: str) -> tuple[list[str], list[str]]:
    cal, wx = manifest["calendar_covariates"], manifest["weather_covariates"]
    mode = manifest["variants"][variant]
    if mode == "past":
        return cal + wx, cal
    if mode == "future":
        return cal + wx, cal + wx
    raise ValueError(f"variant {variant}: unknown weather mode {mode!r}")


# ------------------------------------------------------------------------------------ predict
def forecast_chunk(pipeline, manifest: dict, zones: np.ndarray, hours: pd.DatetimeIndex,
                   y: np.ndarray, cov: pd.DataFrame, origins: pd.DatetimeIndex,
                   variant: str) -> pd.DataFrame:
    """Forecasts for every (origin, zone, target hour) of `origins`; one model call per
    prediction length (23 on spring-forward days, else 24) so all inputs share a schema."""
    qs = list(manifest["quantiles"])
    past, future = variant_covariates(manifest, variant)
    context = int(manifest["context_hours"])
    by_len: dict[int, list[tuple[pd.Timestamp, int]]] = {}
    for o in origins:
        lo, hi = day_positions(hours, o)
        if hi - lo == 0:
            raise ValueError(f"origin {o.date()} has no grid hours")
        by_len.setdefault(hi - lo, []).append((o, lo))
    frames = []
    for n_h, items in sorted(by_len.items()):
        inputs = []
        for _, lo in items:
            inputs += make_inputs(y, cov, lo, n_h, context, past, future)
        quant, _ = pipeline.predict_quantiles(
            inputs, prediction_length=n_h, quantile_levels=qs,
            batch_size=int(manifest["batch_size"]), context_length=context)
        arr = np.stack([t.detach().float().cpu().numpy()[0] for t in quant])  # (n, n_h, n_q)
        k = 0
        for o, lo in items:
            block = arr[k:k + len(zones)]
            k += len(zones)
            ts = hours[lo:lo + n_h]
            df = pd.DataFrame({
                "zone_id": np.repeat(zones, n_h).astype("int16"),
                "origin": o,
                "target_ts": np.tile(ts.to_numpy(), len(zones)),
                "horizon": np.tile(ts.hour.to_numpy() + 1, len(zones)).astype("int8"),
            })
            for j, q in enumerate(qs):
                df[qcol(q)] = block[:, :, j].reshape(-1).astype("float32")
            frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.insert(0, "variant", variant)
    return out.sort_values(["origin", "zone_id", "target_ts"], kind="stable").reset_index(drop=True)


def load_pipeline(model_id: str, device: str):
    from chronos import Chronos2Pipeline  # imported here: the local test suite has no chronos

    return Chronos2Pipeline.from_pretrained(model_id, device_map=device)


def environment(device: str) -> dict:
    import chronos
    import torch
    import transformers

    env = {"python": platform.python_version(), "torch": torch.__version__,
           "transformers": transformers.__version__,
           "chronos_forecasting": getattr(chronos, "__version__", "unknown"),
           "device": device}
    if device.startswith("cuda") and torch.cuda.is_available():
        env["gpu"] = torch.cuda.get_device_name(0)
    return env


def model_revision(model_id: str) -> str | None:
    try:
        from huggingface_hub import HfApi

        return HfApi().model_info(model_id).sha
    except Exception as err:  # offline or API change: record why, do not fail the run
        return f"unavailable: {type(err).__name__}"


# --------------------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent,
                    help="folder with manifest.json, pickups.parquet, covariates.parquet")
    ap.add_argument("--out-dir", type=Path, required=True, help="output folder (Google Drive)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dry-run", action="store_true",
                    help="2 zones x 2 origins x every variant, written to <out-dir>/dry_run/")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    manifest, zones, hours, y, cov = load_bundle(args.bundle)
    origins = pd.date_range(*manifest["origins"], freq="D")
    variants = list(manifest["variants"])
    out_dir = args.out_dir / ("dry_run" if args.dry_run else "")
    chunk_dir = out_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        zones, y, origins = zones[:2], y[:2], origins[[0, -1]]
    log.info("%d zones, %d origins %s..%s, variants %s", len(zones), len(origins),
             origins[0].date(), origins[-1].date(), variants)

    pipeline = load_pipeline(manifest["model_id"], args.device)
    timings = {}
    months = origins.to_period("M")
    todo = [(v, m) for v in variants for m in months.unique()]
    t_all = time.perf_counter()
    for i, (variant, month) in enumerate(todo, 1):
        f = chunk_dir / f"{variant}_{month}.parquet"
        if f.exists():
            log.info("[%d/%d] %s %s: exists, skipped", i, len(todo), variant, month)
            continue
        t0 = time.perf_counter()
        fc = forecast_chunk(pipeline, manifest, zones, hours, y, cov, origins[months == month],
                            variant)
        tmp = f.with_suffix(".tmp")
        fc.to_parquet(tmp, index=False)
        tmp.rename(f)  # atomic: a half-written chunk never looks finished
        timings[f.stem] = round(time.perf_counter() - t0, 1)
        done = len(timings)
        eta = (time.perf_counter() - t_all) / done * (len(todo) - i)
        log.info("[%d/%d] %s %s: %d rows in %.0fs, ETA %.0f min", i, len(todo), variant, month,
                 len(fc), timings[f.stem], eta / 60)

    fc = pd.concat([pd.read_parquet(chunk_dir / f"{v}_{m}.parquet") for v, m in todo],
                   ignore_index=True)
    expected = sum((day_positions(hours, o)[1] - day_positions(hours, o)[0]) for o in origins)
    expected *= len(zones) * len(variants)
    if len(fc) != expected or fc.duplicated(["variant", "zone_id", "target_ts"]).any():
        raise ValueError(f"merged forecasts: {len(fc)} rows, expected {expected} unique rows")
    test_lo, test_hi = (pd.Timestamp(x) for x in manifest["test_period"])
    is_test = (fc["origin"] >= test_lo) & (fc["origin"] <= test_hi)
    fc[is_test].to_parquet(out_dir / "chronos_forecasts.parquet", index=False,
                           compression="zstd")
    fc[~is_test].to_parquet(out_dir / "chronos_forecasts_post.parquet", index=False,
                            compression="zstd")
    run = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "model_id": manifest["model_id"],
        "model_revision": model_revision(manifest["model_id"]),
        "environment": environment(args.device),
        "manifest_sha256": sha256(args.bundle / "manifest.json"),
        "script_sha256": sha256(Path(__file__).resolve()),
        "input_files": manifest["files"],
        "n_zones": len(zones), "n_origins": len(origins), "variants": variants,
        "rows": {"test": int(is_test.sum()), "post": int((~is_test).sum())},
        "chunk_seconds_this_session": timings,
        "note": "chunks skipped as already present were timed in an earlier session",
    }
    (out_dir / "chronos_run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    log.info("done: %s", out_dir)


if __name__ == "__main__":
    main()
