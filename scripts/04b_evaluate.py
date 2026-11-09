"""Phase-2 evaluation: split-conformal calibration, metric table, summary, fan-chart data.

Reads data/forecasts/<model>__<window>__<period>.parquet (scripts/04_backtest.py --full) and, if
present, the imported Chronos-2 forecasts (results/chronos_forecasts.parquet, both variants).

Resumable: the work is split into units, one per (model, window) — each Chronos-2 variant is its
own unit. A finished unit writes its metric rows, report rows and fan-chart rows to
data/forecasts/eval/<model>__<window>.{parquet,json}; the JSON is written last (atomically) and
records a fingerprint of the unit's input files (size, mtime), the evaluation settings and the
sha256 of the evaluation code (this script, taxi_shock.conformal/backtest/metrics). A
rerun skips every unit whose fingerprint still matches and only assembles the outputs, so a
killed run resumes where it stopped; `--force` re-evaluates everything. One unit at a time also
keeps peak memory at one model's forecasts instead of all of them.

Calibrations per unit: `raw`; `conformal_2023` (pre-specified split-conformal CQR on the
validation year; trained models only, Chronos-2 has no 2023 forecasts); and the primary
`conformal_rolling_<w>w` (taxi_shock.conformal.rolling_conformal).

Writes:
    results/backtest_2024.csv      long metric table: model, window, calibration, zone_group,
                                   horizon_bucket, subset (all, y_zero, y_pos), metric, value, n
    results/conformal.json         per (model, window, zone_group): n, Q, validation coverage,
                                   2024 coverage and mean width before / after; rolling block
    results/forecast_summary.json  headline numbers (WAPE by zone group, coverage, relative WAPE
                                   vs seasonal naive) and the primary-window decision
    results/fan_chart_f2b.csv      input of F2b (busiest CBD zone of 2024, models.f2b.week_start)

Usage:
    python scripts/04b_evaluate.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from taxi_shock.backtest import evaluate
from taxi_shock.config import load_config, path, repo_root
from taxi_shock.conformal import conformal, rolling_conformal

TRAINED = ["seasonal_naive", "stat_ets_profile", "lgbm_quantile"]
FAN_MODELS = ["lgbm_quantile", "seasonal_naive"]
CODE = [Path(__file__), *(repo_root() / "src" / "taxi_shock" / f
                          for f in ("conformal.py", "backtest.py", "metrics.py"))]
LOG = logging.getLogger("evaluate")


@dataclass
class Unit:
    model: str
    window: str
    inputs: list[Path]                       # files whose change invalidates the unit
    variant: str | None = None               # Chronos-2 variant
    files: dict[str, Path] = field(default_factory=dict)  # period -> forecast file

    @property
    def name(self) -> str:
        return f"{self.model}__{self.window}"


def units(cfg: dict) -> list[Unit]:
    fdir = path("forecasts", cfg)
    out = []
    for model in TRAINED:
        for f in sorted(fdir.glob(f"{model}__*__test.parquet")):
            window = f.stem.split("__")[1]
            val = fdir / f"{model}__{window}__validation.parquet"
            if not val.exists():
                raise SystemExit(f"missing {val.name}: run scripts/04_backtest.py --full")
            out.append(Unit(model, window, [val, f], files={"validation": val, "test": f}))
    if not out:
        raise SystemExit(f"no test forecasts in {fdir}")
    ch = repo_root() / cfg["chronos"]["test_output"]
    if ch.exists():
        sn = fdir / "seasonal_naive__expanding__test.parquet"
        variants = pd.read_parquet(ch, columns=["variant"])["variant"].astype(str).unique()
        out += [Unit(f"chronos2_{v}", "zero_shot", [ch, sn], variant=v,
                     files={"test": ch, "actuals": sn}) for v in sorted(variants)]
    else:
        LOG.warning("no %s yet: Chronos-2 not evaluated", ch.name)
    return out


def settings(cfg: dict) -> dict:
    return {"code": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in CODE},
            "quantiles": cfg["forecast"]["quantiles"],
            "forecast_eval": cfg["forecast_eval"], "conformal": cfg["models"]["conformal"],
            "zone_summary": _file_sig(path("results", cfg) / "zone_summary.csv")}


def _file_sig(f: Path) -> list[int]:
    st = f.stat()
    return [st.st_size, st.st_mtime_ns]


def fingerprint(unit: Unit, cfg: dict) -> str:
    payload = {"unit": unit.name, "inputs": {f.name: _file_sig(f) for f in unit.inputs},
               "settings": settings(cfg)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load_unit(unit: Unit) -> tuple[pd.DataFrame | None, pd.DataFrame]:
    """(validation or None, test) forecasts of one unit, with model/window columns."""
    if unit.variant is None:
        val, test = (pd.read_parquet(unit.files[p]).assign(model=unit.model, window=unit.window)
                     for p in ("validation", "test"))
        return val, test
    ch = pd.read_parquet(unit.files["test"], filters=[("variant", "==", unit.variant)])
    ch["zone_id"] = ch["zone_id"].astype("int64")
    ch["point"] = ch["q50"]
    key = ["zone_id", "target_ts"]
    act = pd.read_parquet(unit.files["actuals"], columns=key + ["y", "origin", "mase_scale"])
    ch = ch.drop(columns=["origin", "variant"]).merge(act.drop_duplicates(key), on=key,
                                                       how="left")
    return None, ch.assign(model=unit.model, window=unit.window)


def coverage_rows(fc: pd.DataFrame, groups: pd.Series, lo: str, hi: str) -> list[dict]:
    """80% coverage and mean width per (model, window, calibration, zone group)."""
    keep = ["model", "window", "calibration", "zone_id", "origin", "y", lo, hi]
    d = fc.loc[fc["y"].notna() & fc[lo].notna(), keep]
    d = d.assign(zone_group=d["zone_id"].map(groups),
                 inside=(d["y"] >= d[lo]) & (d["y"] <= d[hi]), width=d[hi] - d[lo])
    rows = []
    for keys, g in d.groupby(["model", "window", "calibration", "zone_group"]):
        rows.append({**dict(zip(["model", "window", "calibration", "zone_group"], keys,
                                strict=True)),
                     "n": len(g), "first_origin": str(g["origin"].min().date()),
                     "coverage_80": round(float(g["inside"].mean()), 4),
                     "width_80": round(float(g["width"].mean()), 4)})
    return rows


def evaluate_unit(unit: Unit, cfg: dict, groups: pd.Series, fan: dict, out_dir: Path) -> None:
    ev, cc = cfg["forecast_eval"], cfg["models"]["conformal"]
    qs = tuple(cfg["forecast"]["quantiles"])
    lo, hi = (f"q{round(q * 100):02d}" for q in ev["interval"])
    rolling_label = f"conformal_rolling_{cc['rolling_weeks']}w"
    val, test = load_unit(unit)
    frames, report = [test.assign(calibration="raw")], []
    if val is not None:
        cal, report = conformal(val, test, groups, cc["alpha"], lo, hi)
        frames.append(cal.assign(calibration="conformal_2023"))
    # rolling: trained models use their 2023 forecasts as the history of the first 2024 origins
    origins = pd.DatetimeIndex(sorted(test["origin"].dropna().unique()))
    hist = test if val is None else pd.concat([val, test], ignore_index=True)
    r = rolling_conformal(hist, groups, list(qs), cc["rolling_weeks"], origins)
    uncal = int(r.attrs["n_origins_uncalibrated"])
    frames.append(r[r[lo].notna()].assign(calibration=rolling_label))
    del hist, val
    fc = pd.concat(frames, ignore_index=True)
    del frames
    tables = [evaluate(d, qs, ev["horizon_buckets"], zone_groups=groups,
                       interval=tuple(ev["interval"])).assign(calibration=c)
              for c, d in fc.groupby("calibration")]
    pd.concat(tables, ignore_index=True).to_parquet(out_dir / f"{unit.name}__metrics.parquet")
    f = fc[(fc["zone_id"] == fan["zone"]) & (fc["target_ts"] >= fan["start"])
           & (fc["target_ts"] < fan["start"] + pd.Timedelta(days=7))
           & fc["model"].isin(FAN_MODELS) & fc["calibration"].isin(["raw", cc["primary"]])]
    f[FAN_COLS].to_parquet(out_dir / f"{unit.name}__fan.parquet")
    done = {"unit": unit.name, "fingerprint": fingerprint(unit, cfg),
            "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "conformal_2023": report, "origins_without_full_trailing_window": uncal,
            "coverage_and_width": coverage_rows(fc, groups, lo, hi)}
    tmp = out_dir / f".{unit.name}.json.tmp"
    tmp.write_text(json.dumps(done, indent=2) + "\n")
    os.replace(tmp, out_dir / f"{unit.name}.json")   # completion marker, written last


FAN_COLS = ["model", "window", "calibration", "zone_id", "target_ts", "y", "point", "q10", "q50",
            "q90"]


def is_done(unit: Unit, cfg: dict, out_dir: Path) -> bool:
    f = out_dir / f"{unit.name}.json"
    if not f.exists() or not all((out_dir / f"{unit.name}__{k}.parquet").exists()
                                 for k in ("metrics", "fan")):
        return False
    return json.loads(f.read_text()).get("fingerprint") == fingerprint(unit, cfg)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-evaluate every unit")
    args = ap.parse_args()
    cfg = load_config()
    res = path("results", cfg)
    out_dir = path("forecasts", cfg) / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    zs = pd.read_csv(res / "zone_summary.csv")
    groups = zs.set_index("zone_id")["zone_group"]
    fan = {"zone": int(zs[zs["is_cbd"]].sort_values("pickups_2024", ascending=False)
                       ["zone_id"].iloc[0]),
           "start": pd.Timestamp(cfg["models"]["f2b"]["week_start"])}

    todo = units(cfg)
    for i, u in enumerate(todo, 1):
        if not args.force and is_done(u, cfg, out_dir):
            LOG.info("[%d/%d] %s: done earlier, skipped", i, len(todo), u.name)
            continue
        t0 = datetime.now(UTC)
        evaluate_unit(u, cfg, groups, fan, out_dir)
        LOG.info("[%d/%d] %s: evaluated in %.0f s", i, len(todo), u.name,
                 (datetime.now(UTC) - t0).total_seconds())
    assemble(cfg, todo, out_dir, res)


def assemble(cfg: dict, todo: list[Unit], out_dir: Path, res: Path) -> None:
    cc = cfg["models"]["conformal"]
    table = pd.concat([pd.read_parquet(out_dir / f"{u.name}__metrics.parquet") for u in todo],
                      ignore_index=True)
    cols = ["model", "window", "calibration", "zone_group", "horizon_bucket", "subset", "metric",
            "value", "n"]
    table = table[cols].sort_values(cols[:7]).reset_index(drop=True)
    table.to_csv(res / "backtest_2024.csv", index=False, lineterminator="\n")
    LOG.info("backtest_2024.csv: %d rows", len(table))
    done = [json.loads((out_dir / f"{u.name}.json").read_text()) for u in todo]
    rolling_label = f"conformal_rolling_{cc['rolling_weeks']}w"
    (res / "conformal.json").write_text(json.dumps({
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": "split-conformal CQR: score max(q_lo - y, y - q_hi) on the validation year, "
                  "Q = ceil((n+1)(1-alpha))/n quantile, interval [max(q_lo - Q, 0), q_hi + Q]",
        "alpha": cc["alpha"], "validation_year": cfg["models"]["validation_year"],
        "group_by": cc["group_by"],
        "not_calibrated": ["chronos2_* (no validation-year forecasts)"],
        "rows": [r for d in done for r in d["conformal_2023"]],
        "rolling": {
            "label": rolling_label, "primary": cc["primary"],
            "method": ("per origin D, zone group and quantile level tau: q_tau + the empirical "
                       "tau-quantile of y - q_tau over forecasts with target day in "
                       f"[D - {7 * cc['rolling_weeks']} d, D - 1]; quantiles re-sorted and "
                       "clipped at 0; point forecast unchanged (taxi_shock.conformal)"),
            "origins_without_full_trailing_window": {
                d["unit"].replace("__", "|"): d["origins_without_full_trailing_window"]
                for d in done},
            "coverage_and_width": [r for d in done for r in d["coverage_and_width"]]}},
        indent=2) + "\n")
    write_summary(cfg, table, res)
    fan = pd.concat([pd.read_parquet(out_dir / f"{u.name}__fan.parquet") for u in todo],
                    ignore_index=True)
    fan[FAN_COLS].sort_values(FAN_COLS[:5]).to_csv(res / "fan_chart_f2b.csv", index=False,
                                                   lineterminator="\n")
    LOG.info("evaluation done")


def _metric(table: pd.DataFrame, metric: str, **kw) -> pd.DataFrame:
    sel = (table["metric"] == metric) & (table["horizon_bucket"] == "all") & \
        (table["subset"] == "all")
    for k, v in kw.items():
        sel &= table[k] == v
    return table[sel]


def write_summary(cfg: dict, table: pd.DataFrame, res) -> None:
    raw = table[table["calibration"] == "raw"]
    wape = _metric(raw, "wape").pivot_table(index=["model", "window"], columns="zone_group",
                                            values="value")
    base = wape.loc[("seasonal_naive", "expanding")]
    rel = wape.div(base, axis=1)
    pin = raw[(raw["metric"].str.startswith("pinball_")) & (raw["horizon_bucket"] == "all")
              & (raw["subset"] == "all") & (raw["zone_group"] == "all")]
    mean_pin = pin.groupby(["model", "window"])["value"].mean()
    rule = cfg["models"]["primary_window_rule"]
    lg = mean_pin.loc["lgbm_quantile"] if "lgbm_quantile" in mean_pin.index.get_level_values(0) \
        else None
    primary = None
    if lg is not None and {"expanding", "sliding_24m"} <= set(lg.index):
        diff = (lg["sliding_24m"] - lg["expanding"]) / lg["expanding"]
        primary = "sliding_24m" if diff < -rule["tie_relative"] else "expanding"
    cov = table[(table["metric"].str.startswith("coverage_")) & (table["horizon_bucket"] == "all")
                & (table["subset"] == "all") & (table["zone_group"] == "all")]
    out = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "results/backtest_2024.csv",
        "wape_by_zone_group": {f"{m}|{w}": {g: round(float(v), 4) for g, v in r.items()}
                               for (m, w), r in wape.iterrows()},
        "wape_relative_to_seasonal_naive_expanding": {
            f"{m}|{w}": {g: round(float(v), 4) for g, v in r.items()}
            for (m, w), r in rel.iterrows()},
        "mean_pinball_all_zones": {f"{m}|{w}": round(float(v), 4)
                                   for (m, w), v in mean_pin.items()},
        "coverage_80_all_zones": {f"{r.model}|{r.window}|{r.calibration}": round(r.value, 4)
                                  for r in cov.itertuples()},
        "primary_window": {"rule": rule, "lgbm_mean_pinball": None if lg is None else
                           {k: round(float(v), 4) for k, v in lg.items()},
                           "chosen": primary},
    }
    (res / "forecast_summary.json").write_text(json.dumps(out, indent=2) + "\n")
    LOG.info("primary window: %s", primary)


if __name__ == "__main__":
    main()
