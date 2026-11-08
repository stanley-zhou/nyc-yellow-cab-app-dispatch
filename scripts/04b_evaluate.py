"""Phase-2 evaluation: split-conformal calibration, metric table, summary, fan-chart data.

Reads data/forecasts/<model>__<window>__<period>.parquet (scripts/04_backtest.py --full) and, if
present, the imported Chronos-2 forecasts (results/chronos_forecasts.parquet, both variants).

Writes:
    results/backtest_2024.csv      long metric table: model, window, calibration (raw |
                                   conformal), zone_group, horizon_bucket, subset (all, y_zero,
                                   y_pos), metric, value, n
    results/conformal.json         per (model, window, zone_group): n, Q, validation coverage,
                                   2024 coverage and mean width before / after
    results/forecast_summary.json  headline numbers (WAPE by zone group, coverage, relative WAPE
                                   vs seasonal naive) and the primary-window decision
    results/fan_chart_f2b.csv      input of F2b (busiest CBD zone of 2024, models.f2b.week_start)

Usage:
    python scripts/04b_evaluate.py
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import pandas as pd

from taxi_shock.backtest import evaluate
from taxi_shock.config import load_config, path, repo_root
from taxi_shock.conformal import conformal, rolling_conformal

TRAINED = ["seasonal_naive", "stat_ets_profile", "lgbm_quantile"]


def load_forecasts(cfg: dict, period: str) -> pd.DataFrame:
    frames = []
    for f in sorted(path("forecasts", cfg).glob(f"*__*__{period}.parquet")):
        model, window, _ = f.stem.split("__")
        if model in TRAINED:
            frames.append(pd.read_parquet(f).assign(model=model, window=window))
    if not frames:
        raise SystemExit(f"no {period} forecasts in {path('forecasts', cfg)}")
    return pd.concat(frames, ignore_index=True)


def chronos_forecasts(cfg: dict, scale_src: pd.DataFrame) -> pd.DataFrame | None:
    f = repo_root() / cfg["chronos"]["test_output"]
    if not f.exists():
        logging.warning("no %s yet: Chronos-2 not evaluated", f.name)
        return None
    ch = pd.read_parquet(f)
    ch["zone_id"] = ch["zone_id"].astype("int64")
    ch["model"] = "chronos2_" + ch["variant"].astype(str)
    ch["window"] = "zero_shot"
    ch["point"] = ch["q50"]
    key = ["zone_id", "target_ts"]
    act = scale_src[key + ["y", "origin", "mase_scale"]].drop_duplicates(key)
    ch = ch.drop(columns=["origin"]).merge(act, on=key, how="left")
    return ch.drop(columns=["variant"])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    ev, mc = cfg["forecast_eval"], cfg["models"]
    qs = tuple(cfg["forecast"]["quantiles"])
    lo, hi = (f"q{round(q * 100):02d}" for q in ev["interval"])
    zs = pd.read_csv(res / "zone_summary.csv")
    groups = zs.set_index("zone_id")["zone_group"]

    cc = mc["conformal"]
    val, test = load_forecasts(cfg, "validation"), load_forecasts(cfg, "test")
    cal, report = conformal(val, test, groups, cc["alpha"], lo, hi)
    frames = [test.assign(calibration="raw"), cal.assign(calibration="conformal_2023")]
    sn = test[(test["model"] == "seasonal_naive") & (test["window"] == "expanding")]
    ch = chronos_forecasts(cfg, sn)
    if ch is not None:
        frames.append(ch.assign(calibration="raw"))
    # primary calibration: rolling per-quantile conformal on the trailing weeks of residuals;
    # trained models use their 2023 forecasts as the history of the first 2024 origins
    origins = pd.DatetimeIndex(sorted(test["origin"].unique()))
    hist = pd.concat([val, test] + ([ch] if ch is not None else []), ignore_index=True)
    rolling_label = f"conformal_rolling_{cc['rolling_weeks']}w"
    uncal = {}
    for (m, w), d in hist.groupby(["model", "window"]):
        r = rolling_conformal(d, groups, list(qs), cc["rolling_weeks"], origins)
        uncal[f"{m}|{w}"] = r.attrs["n_origins_uncalibrated"]
        frames.append(r[r[lo].notna()].assign(calibration=rolling_label))
    allfc = pd.concat(frames, ignore_index=True)

    tables = []
    for c, d in allfc.groupby("calibration"):
        t = evaluate(d, qs, ev["horizon_buckets"], zone_groups=groups,
                     interval=tuple(ev["interval"]))
        tables.append(t.assign(calibration=c))
    table = pd.concat(tables, ignore_index=True)
    cols = ["model", "window", "calibration", "zone_group", "horizon_bucket", "subset", "metric",
            "value", "n"]
    table = table[cols].sort_values(cols[:7]).reset_index(drop=True)
    table.to_csv(res / "backtest_2024.csv", index=False, lineterminator="\n")
    (res / "conformal.json").write_text(json.dumps({
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": "split-conformal CQR: score max(q_lo - y, y - q_hi) on the validation year, "
                  "Q = ceil((n+1)(1-alpha))/n quantile, interval [max(q_lo - Q, 0), q_hi + Q]",
        "alpha": mc["conformal"]["alpha"], "validation_year": mc["validation_year"],
        "group_by": mc["conformal"]["group_by"],
        "not_calibrated": ["chronos2_* (no validation-year forecasts)"],
        "rows": report,
        "rolling": {
            "label": rolling_label, "primary": cc["primary"],
            "method": ("per origin D, zone group and quantile level tau: q_tau + the empirical "
                       "tau-quantile of y - q_tau over forecasts with target day in "
                       f"[D - {7 * cc['rolling_weeks']} d, D - 1]; quantiles re-sorted and "
                       "clipped at 0; point forecast unchanged (taxi_shock.conformal)"),
            "origins_without_full_trailing_window": uncal,
            "coverage_and_width": rolling_report(allfc, groups, lo, hi)}},
        indent=2) + "\n")
    write_summary(cfg, table, res)
    write_fan_chart(cfg, allfc, zs, res)
    logging.info("backtest_2024.csv: %d rows", len(table))


def rolling_report(allfc: pd.DataFrame, groups: pd.Series, lo: str, hi: str) -> list[dict]:
    """80% coverage and mean width per (model, window, calibration, zone group)."""
    d = allfc[allfc["y"].notna() & allfc[lo].notna()].assign(
        zone_group=allfc["zone_id"].map(groups))
    d = d.assign(inside=(d["y"] >= d[lo]) & (d["y"] <= d[hi]), width=d[hi] - d[lo])
    rows = []
    for keys, g in d.groupby(["model", "window", "calibration", "zone_group"]):
        rows.append({**dict(zip(["model", "window", "calibration", "zone_group"], keys,
                                strict=True)),
                     "n": len(g), "first_origin": str(g["origin"].min().date()),
                     "coverage_80": round(float(g["inside"].mean()), 4),
                     "width_80": round(float(g["width"].mean()), 4)})
    return rows


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
    logging.info("primary window: %s", primary)


def write_fan_chart(cfg: dict, allfc: pd.DataFrame, zs: pd.DataFrame, res) -> None:
    zone = int(zs[zs["is_cbd"]].sort_values("pickups_2024", ascending=False)["zone_id"].iloc[0])
    w0 = pd.Timestamp(cfg["models"]["f2b"]["week_start"])
    d = allfc[(allfc["zone_id"] == zone) & (allfc["target_ts"] >= w0)
              & (allfc["target_ts"] < w0 + pd.Timedelta(days=7))]
    d = d[d["model"].isin(["lgbm_quantile", "seasonal_naive"])
          & d["calibration"].isin(["raw", cfg["models"]["conformal"]["primary"]])]
    cols = ["model", "window", "calibration", "zone_id", "target_ts", "y", "point", "q10", "q50",
            "q90"]
    d[cols].sort_values(cols[:5]).to_csv(res / "fan_chart_f2b.csv", index=False,
                                         lineterminator="\n")


if __name__ == "__main__":
    main()
