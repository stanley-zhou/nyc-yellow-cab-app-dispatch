"""Phase 5 (re-scoped by Amendment 4 D6): forecasting through the channel shift.

Strategies, evaluated on day-ahead origins adapt.eval_window (2025-02-01 -> 2026-09-30) with the
Phase-2 metrics (WAPE, MAE, MASE, bias, pinball, 80% coverage and width; raw and the primary
rolling 12-week conformal calibration):
  S0 frozen       the Phase-3 frozen LightGBM (trained once to 2024-12-31; never refitted)
  S1 retrain      LightGBM refitted monthly on a sliding 24-month window (the Phase-2 model,
                  tuned parameters and refit early stopping)
  S4 chronos      Chronos-2 zero-shot, primary variant (weather as past covariate), adapting
                  only through its context window (imported Colab forecasts)
  S6 channel      S1 + lagged app-channel features (taxi_shock.adapt: the zone's app share of
                  pickups over the previous 7 and 28 days and the citywide previous-7-day
                  share; app = any e-hail app, Amendment 4a)
No S3 (Amendment 4: no level correction from the causal estimate).

S1 and S6 run month by month (one refit at the first origin of each month, then daily forecasts
for that month) from adapt.run_start, so that the rolling conformal calibration has 12 weeks of
their own forecasts before the evaluation window; each month is written to
data/forecasts/adapt/<strategy>/<YYYY-MM>.parquet and skipped when present (resumable; a crash
costs at most one month). MASE uses one fixed per-zone scale for every strategy (in-sample
seasonal-naive MAE from data.model_start to adapt.scale_end), so the strategies are comparable.

Usage:
    python scripts/08_adapt.py --run s1|s6     # monthly refits (long)
    python scripts/08_adapt.py --evaluate      # metrics, daily errors, bootstrap gaps

Writes results/adaptation.csv (strategy, calibration, period, zone_group, horizon bucket, subset,
metric, value, n), results/adaptation_daily.csv, results/adaptation_gaps.csv,
results/adaptation_refits.csv, results/adaptation_summary.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.adapt import CHANNEL_FEATURES, channel_feature_fn, channel_table, quarter_label
from taxi_shock.backtest import BacktestSpec, daily_origins, evaluate, run_backtest
from taxi_shock.config import load_config, path
from taxi_shock.conformal import rolling_conformal
from taxi_shock.evaluation import daily_errors, sort_clip_quantiles, wape_gap_bootstrap
from taxi_shock.io import connect, read_exog, read_modeled_panel
from taxi_shock.models.lgbm_quantile import GlobalLGBMQuantile
from taxi_shock.models.seasonal_naive import seasonal_residuals

LOG = logging.getLogger("adapt")
QCOLS = ["q10", "q50", "q90"]
KEEP = ["zone_id", "origin", "target_ts", "horizon", "y", *QCOLS, "point"]


def zones_and_groups(cfg: dict) -> tuple[list[int], pd.Series]:
    res = path("results", cfg)
    zones = json.loads((res / "modeled_zones.json").read_text())["zone_ids"]
    zs = pd.read_csv(res / "zone_summary.csv")
    return zones, zs.set_index("zone_id")["zone_group"]


def load_inputs(cfg: dict, zones: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    ac = cfg["adapt"]
    first = pd.Timestamp(ac["run_start"]) - pd.DateOffset(months=24) - pd.Timedelta(
        days=cfg["models"]["feature_history_days"])
    end = (pd.Timestamp(ac["eval_window"][1]) + pd.Timedelta(days=1)).date().isoformat()
    db = path("warehouse", cfg)
    panel = read_modeled_panel(db, zones, first.date().isoformat(), end, cfg)
    exog = read_exog(db, first.date().isoformat(), end, cfg)
    return panel, exog


def channel_fn(cfg: dict, zones: list[int]):
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        d = con.execute("""
            select zone_id, day, sum(pickups) filter (where channel = 'app') as app,
                   sum(pickups) as total
            from fct_daily_zone_channel group by all""").df()
    d = d[d["zone_id"].isin(zones)].fillna({"app": 0})
    return channel_feature_fn(channel_table(d))


def run(cfg: dict, strategy: str) -> None:
    ac, mc = cfg["adapt"], cfg["models"]
    zones, _ = zones_and_groups(cfg)
    panel, exog = load_inputs(cfg, zones)
    tuned = json.loads((path("results", cfg) / "lgbm_params.json").read_text())
    extra = channel_fn(cfg, zones) if strategy == "s6" else None
    fits: list[dict] = []

    def make():
        m = GlobalLGBMQuantile(exog, cfg["forecast"]["quantiles"], tuned["params"],
                               {float(k): v for k, v in tuned["rounds"].items()},
                               seed=cfg["seed"], threads=mc["threads"],
                               predict_history_days=mc["lgbm"]["predict_history_days"],
                               early_stopping=mc["lgbm"].get("refit_early_stopping"),
                               extra=extra, extra_cols=CHANNEL_FEATURES if extra else ())
        fit0 = m.fit

        def fit(history, train_start=None):
            fit0(history, train_start)
            fits.append(dict(m.fit_info_))
            return m

        m.fit = fit
        return m

    out_dir = path("forecasts", cfg) / "adapt" / strategy
    out_dir.mkdir(parents=True, exist_ok=True)
    origins = daily_origins(ac["run_start"], ac["eval_window"][1])
    ms = pd.Timestamp(cfg["data"]["model_start"])
    rec_f = path("results", cfg) / "adaptation_refits.csv"
    for month, o in pd.Series(origins, index=origins).groupby(origins.to_period("M")):
        f = out_dir / f"{month}.parquet"
        if f.exists():
            LOG.info("%s %s: exists, skipped", strategy, month)
            continue
        t0 = time.perf_counter()
        n0 = len(fits)
        spec = BacktestSpec(origins=pd.DatetimeIndex(o.to_numpy()),
                            quantiles=tuple(cfg["forecast"]["quantiles"]),
                            window=ac["window"], refit="monthly", model_start=ms, scale_start=ms)
        fc = run_backtest(panel, make, spec)[KEEP]
        tmp = f.with_suffix(".tmp")
        fc.to_parquet(tmp, index=False)
        tmp.replace(f)
        rec = pd.DataFrame([{**fits[n0], "strategy": strategy, "month": str(month),
                             "rounds": json.dumps(fits[n0].get("rounds")),
                             "wall_seconds": round(time.perf_counter() - t0, 1)}])
        old = pd.read_csv(rec_f) if rec_f.exists() else pd.DataFrame()
        if len(old):
            old = old[~((old["strategy"] == strategy) & (old["month"] == str(month)))]
        pd.concat([old, rec], ignore_index=True).to_csv(rec_f, index=False, lineterminator="\n")
        LOG.info("%s %s: %d rows in %.0fs", strategy, month, len(fc), time.perf_counter() - t0)


def load_strategy(cfg: dict, s: str, panel: pd.DataFrame) -> pd.DataFrame:
    if s == "s0":
        fc = pd.read_parquet(path("forecasts", cfg) / "frozen" / "lgbm_quantile.parquet")
    elif s == "s4":
        v = cfg["chronos"]["primary_variant"]
        res = path("results", cfg)
        parts = [pd.read_parquet(res / f) for f in ("chronos_forecasts.parquet",
                                                     "chronos_forecasts_post.parquet")]
        fc = pd.concat([p[p["variant"] == v] for p in parts], ignore_index=True)
        fc = sort_clip_quantiles(fc, QCOLS)
        fc["point"] = fc["q50"]
        act = panel.rename(columns={"hour_ts": "target_ts", "pickups": "y"})[
            ["zone_id", "target_ts", "y"]]
        fc = fc.merge(act, on=["zone_id", "target_ts"], how="left")
        fc["horizon"] = (fc["target_ts"].dt.hour + 1).astype("int16")
    else:
        files = sorted((path("forecasts", cfg) / "adapt" / s).glob("*.parquet"))
        fc = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    return fc[KEEP]


def retrain_cost(cfg: dict) -> dict:
    """Compute cost of each strategy: S1/S6 wall time of the monthly local refits
    (results/adaptation_refits.csv; 12 cores, CPU); S4 has no refit, only its Colab inference
    per month of daily origins (results/chronos_run.json, primary variant); S0 nothing."""
    res = path("results", cfg)
    out: dict = {"s0": {"note": "no refit, no inference beyond the frozen forecasts"}}
    f = res / "adaptation_refits.csv"
    if f.exists():
        r = pd.read_csv(f)
        out |= {s: {"n_refits": int(len(x)), "wall_seconds_total": float(x["wall_seconds"].sum()),
                    "wall_seconds_median": float(x["wall_seconds"].median()),
                    "hardware": "local CPU, 12 cores"}
                for s, x in r.groupby("strategy")}
    j = res / "chronos_run.json"
    if j.exists():
        run = json.loads(j.read_text())
        v = cfg["chronos"]["primary_variant"]
        sec = [t for k, t in run.get("chunk_seconds_this_session", {}).items()
               if k.startswith(f"{v}_")]
        if sec:
            out["s4"] = {"n_months": len(sec), "inference_seconds_total": float(sum(sec)),
                         "inference_seconds_median_per_month": float(np.median(sec)),
                         "hardware": run.get("environment", {}).get("gpu", "")}
    return out


def evaluate_all(cfg: dict) -> None:
    ac = cfg["adapt"]
    zones, groups = zones_and_groups(cfg)
    panel, _ = load_inputs(cfg, zones)
    ms = pd.Timestamp(cfg["data"]["model_start"])
    res = seasonal_residuals(panel[panel["hour_ts"] < pd.Timestamp(ac["scale_end"])
                                   + pd.Timedelta(days=1)])
    res = res[res["hour_ts"] >= ms]
    scale = res.assign(a=res["resid"].abs()).groupby("zone_id")["a"].mean()
    lo, hi = (pd.Timestamp(x) for x in ac["eval_window"])
    eval_origins = daily_origins(*ac["eval_window"])
    w = int(cfg["models"]["conformal"]["rolling_weeks"])
    qs = list(cfg["forecast"]["quantiles"])
    ev = cfg["forecast_eval"]
    names = ac["strategies"]
    rows, daily, boot, coverage_note = [], [], [], {}
    for s in names:
        fc = load_strategy(cfg, s, panel)
        fc = fc[fc["zone_id"].isin(zones)]
        cal = rolling_conformal(fc, groups, qs, w, eval_origins)
        coverage_note[s] = {"n_origins_uncalibrated": int(cal.attrs.get(
            "n_origins_uncalibrated", 0))}
        raw = fc[(fc["origin"] >= lo) & (fc["origin"] <= hi)]
        for calib, d in (("raw", raw), (cfg["models"]["conformal"]["primary"], cal)):
            d = d.assign(model=s, window=calib, mase_scale=d["zone_id"].map(scale))
            d = d[d["y"].notna()]
            for per, x in [("all", d), *d.groupby(quarter_label(d["origin"]))]:
                m = evaluate(x, qs, ev["horizon_buckets"], zone_groups=groups,
                             interval=tuple(ev["interval"]))
                rows.append(m.rename(columns={"model": "strategy", "window": "calibration"})
                            .assign(period=per))
        boot.append(daily_errors(raw, groups).assign(model=s))
        dd = raw.assign(zone_group=raw["zone_id"].map(groups), day=raw["target_ts"].dt.normalize(),
                        abs_err=(raw["y"] - raw["point"]).abs(), err=raw["point"] - raw["y"])
        daily.append(dd.groupby(["zone_group", "day"])[["abs_err", "err", "y"]].sum()
                     .reset_index().assign(strategy=s))
        LOG.info("%s evaluated", s)
    met = pd.concat(rows, ignore_index=True)
    met = met[(met["horizon_bucket"] == "all") | (met["period"] == "all")]
    met.to_csv(path("results", cfg) / "adaptation.csv", index=False, lineterminator="\n",
               float_format="%.6g")
    dl = pd.concat(daily, ignore_index=True)
    alld = dl.groupby(["strategy", "day"])[["abs_err", "err", "y"]].sum().reset_index().assign(
        zone_group="all")
    dl = pd.concat([dl, alld], ignore_index=True)
    dl.to_csv(path("results", cfg) / "adaptation_daily.csv", index=False, lineterminator="\n",
              float_format="%.6g")
    # paired block-bootstrap WAPE gaps (Phase-2 method), every pair, per zone group
    bc = cfg["models"]["f2"]
    gaps = wape_gap_bootstrap(pd.concat(boot, ignore_index=True), bc["bootstrap_reps"],
                              bc["block_days"], cfg["seed"])
    gaps.to_csv(path("results", cfg) / "adaptation_gaps.csv", index=False, lineterminator="\n",
                float_format="%.6g")
    prim = cfg["models"]["conformal"]["primary"]
    sel = met[(met["calibration"] == prim) & (met["horizon_bucket"] == "all")
              & (met["subset"] == "all")]
    head = sel[sel["period"] == "all"].pivot_table(index=["strategy", "zone_group"],
                                                   columns="metric", values="value")
    summary = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
               "eval_window": ac["eval_window"], "strategies": names,
               "calibration": prim, "mase_scale": f"per-zone seasonal-naive MAE "
               f"{cfg['data']['model_start']} -> {ac['scale_end']}, common to all strategies",
               "uncalibrated_origins": coverage_note,
               "bias_pct_of_pickups": {f"{s}|{g}": float(r["err"] / r["y"] * 100)
                                       for (s, g), r in dl.groupby(["strategy", "zone_group"])
                                       [["err", "y"]].sum().iterrows()},
               "retrain_cost": retrain_cost(cfg),
               "headline": {f"{s}|{g}": {k: float(v) for k, v in r.items()
                                        if k in ("wape", "bias", "coverage_80", "mase")}
                            for (s, g), r in head.iterrows()}}
    (path("results", cfg) / "adaptation_summary.json").write_text(json.dumps(summary, indent=2)
                                                                 + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", choices=["s1", "s6"])
    g.add_argument("--evaluate", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if args.run:
        run(cfg, args.run)
    else:
        evaluate_all(cfg)


if __name__ == "__main__":
    main()
