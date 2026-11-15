"""Phase-3 error tables: daily sums per zone group and trailing-window metrics.

Conventions: `bias` = mean (forecast - actual) per zone-hour (the project's mean signed error;
positive = over-forecast); `log_actual_over_forecast` = log(sum actual / sum forecast) over the
group and window (negative = actual below forecast; exp(.) - 1 is the % gap).
Takes long forecast DataFrames and returns DataFrames; no file or warehouse access.
"""

from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from taxi_shock.backtest import targets_for

LOG = logging.getLogger(__name__)


def daily_table(allfc: pd.DataFrame, groups: dict[str, list[int]]) -> pd.DataFrame:
    """Per (model, series, zone group, local day): sums of y, point, |y - point|, point - y,
    hours, and whether any row is in-sample."""
    d = allfc[allfc["y"].notna() & allfc["point"].notna()].copy()
    d["day"] = d["target_ts"].dt.normalize()
    d["abs_err"] = (d["y"] - d["point"]).abs()
    d["signed"] = d["point"] - d["y"]
    out = []
    for g, zs in groups.items():
        sub = d[d["zone_id"].isin(zs)]
        agg = sub.groupby(["model", "series", "day"]).agg(
            actual=("y", "sum"), forecast=("point", "sum"), abs_error=("abs_err", "sum"),
            signed_error=("signed", "sum"), n_hours=("y", "size"),
            in_sample=("in_sample", "any")).reset_index()
        out.append(agg.assign(zone_group=g))
    return pd.concat(out, ignore_index=True)


def rolling_table(daily: pd.DataFrame, days: int) -> pd.DataFrame:
    """Trailing `days`-day sums ending on each day (only complete windows) and daily values."""
    rows = []
    sums = ["actual", "forecast", "abs_error", "signed_error", "n_hours"]
    for (m, s, g), d in daily.groupby(["model", "series", "zone_group"]):
        d = d.set_index("day").sort_index().asfreq("D")
        for w in (1, days):
            r = d[sums].rolling(w, min_periods=w).sum()
            ins = d["in_sample"].astype(float).rolling(w, min_periods=w).max() > 0
            r = r.dropna().assign(in_sample=ins.reindex(r.dropna().index))
            rows.append(r.reset_index().assign(model=m, series=s, zone_group=g,
                                               window_days=w))
    t = pd.concat(rows, ignore_index=True)
    t["wape"] = t["abs_error"] / t["actual"]
    t["bias"] = t["signed_error"] / t["n_hours"]          # mean (forecast - actual) per hour
    t["log_actual_over_forecast"] = np.log(t["actual"] / t["forecast"])
    t = t.rename(columns={"day": "date"})
    cols = ["date", "model", "series", "zone_group", "window_days", "n_hours", "actual",
            "forecast", "abs_error", "wape", "bias", "log_actual_over_forecast", "in_sample"]
    t["n_hours"] = t["n_hours"].astype("int64")
    return t[cols].sort_values(cols[:5]).reset_index(drop=True)


def forecast_frozen(model, panel: pd.DataFrame, origins: pd.DatetimeIndex, qs: list[float],
                    history_days: int = 35) -> pd.DataFrame:
    """Day-ahead forecasts for every origin with a model that is never refitted. `panel` must
    be sorted by hour_ts; each origin sees the `history_days` days before it (features need
    at most 30, models.lgbm.predict_history_days)."""
    ts = panel["hour_ts"].to_numpy()
    hours = pd.DatetimeIndex(np.unique(ts))
    zones = np.sort(panel["zone_id"].unique())
    out = []
    t0 = time.perf_counter()
    for i, origin in enumerate(origins, 1):
        start = origin - pd.Timedelta(days=history_days)
        lo = int(np.searchsorted(ts, np.datetime64(start), "left"))
        cut = int(np.searchsorted(ts, np.datetime64(origin), "left"))
        pred = model.predict_quantiles(panel.iloc[lo:cut], targets_for(origin, hours, zones), qs)
        out.append(pred.assign(origin=origin))
        if i % 100 == 0:
            LOG.info("  %d/%d origins (%.0f s)", i, len(origins), time.perf_counter() - t0)
    fc = pd.concat(out, ignore_index=True)
    act = panel.rename(columns={"hour_ts": "target_ts", "pickups": "y"})[
        ["zone_id", "target_ts", "y"]]
    return fc.merge(act, on=["zone_id", "target_ts"], how="left")
