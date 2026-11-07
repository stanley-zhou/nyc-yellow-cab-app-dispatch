"""Rolling-origin backtest engine and metric tables.

At each origin (local midnight of day D) the engine:
  1. truncates the panel to `hour_ts < origin` (the model never receives later rows);
  2. refits the model on the training window if the refit schedule says so;
  3. asks for quantile forecasts of every local hour of day D for every zone.

Training windows: `expanding` (from `model_start`) or `sliding_<N>m` (the last N months, never
earlier than `model_start`). Refit schedules: `monthly` (first origin of each calendar month),
`daily`, or `once` (first origin only, i.e. a frozen model).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from taxi_shock import metrics as mt
from taxi_shock.models.base import BaseForecaster, quantile_col
from taxi_shock.models.seasonal_naive import seasonal_residuals

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BacktestSpec:
    origins: pd.DatetimeIndex
    quantiles: tuple[float, ...]
    window: str = "expanding"
    refit: str = "monthly"
    model_start: pd.Timestamp | None = None


def daily_origins(start: str, end: str) -> pd.DatetimeIndex:
    """Local-midnight origins for every day in [start, end]."""
    return pd.date_range(start=start, end=end, freq="D")


def refit_mask(origins: pd.DatetimeIndex, refit: str) -> np.ndarray:
    if refit == "daily":
        return np.ones(len(origins), dtype=bool)
    if refit == "once":
        mask = np.zeros(len(origins), dtype=bool)
        mask[0] = True
        return mask
    if refit == "monthly":
        months = origins.to_period("M")
        return np.r_[True, months[1:] != months[:-1]]
    raise ValueError(f"unknown refit schedule {refit!r}")


def window_start(
    origin: pd.Timestamp, window: str, model_start: pd.Timestamp | None
) -> pd.Timestamp:
    floor = model_start if model_start is not None else pd.Timestamp.min
    if window == "expanding":
        return floor
    m = re.fullmatch(r"sliding_(\d+)m", window)
    if not m:
        raise ValueError(f"unknown training window {window!r}")
    return max(floor, origin - pd.DateOffset(months=int(m.group(1))))


def targets_for(origin: pd.Timestamp, hours: pd.DatetimeIndex, zones: np.ndarray) -> pd.DataFrame:
    """Every (zone, local hour) of calendar day `origin`; horizon = hour-of-day + 1."""
    day = hours[(hours >= origin) & (hours < origin + pd.Timedelta(days=1))]
    idx = pd.MultiIndex.from_product([zones, day], names=["zone_id", "target_ts"])
    t = idx.to_frame(index=False)
    t["horizon"] = (t["target_ts"].dt.hour + 1).astype("int16")
    return t


def run_backtest(
    panel: pd.DataFrame,
    model_factory: Callable[[], BaseForecaster],
    spec: BacktestSpec,
) -> pd.DataFrame:
    """Forecasts for every origin, joined to actuals `y` and the per-zone MASE scale."""
    panel = panel.sort_values(["hour_ts", "zone_id"], kind="stable").reset_index(drop=True)
    ts = panel["hour_ts"].to_numpy()
    hours = pd.DatetimeIndex(np.unique(ts))
    zones = np.sort(panel["zone_id"].unique())
    refit = refit_mask(spec.origins, spec.refit)
    model: BaseForecaster | None = None
    scale: pd.Series | None = None
    fit_start = fit_end = None
    out: list[pd.DataFrame] = []
    for origin, do_refit in zip(spec.origins, refit, strict=True):
        cut = int(np.searchsorted(ts, np.datetime64(origin), side="left"))
        history = panel.iloc[:cut]
        if do_refit or model is None:
            lo = window_start(origin, spec.window, spec.model_start)
            train = history[history["hour_ts"] >= lo]
            model = model_factory().fit(train)
            res = seasonal_residuals(train)
            scale = res.assign(a=res["resid"].abs()).groupby("zone_id")["a"].mean()
            fit_start, fit_end = train["hour_ts"].min(), train["hour_ts"].max()
            log.info("%s fit at %s on %s..%s (%d rows)", model.name, origin.date(),
                     fit_start, fit_end, len(train))
        targets = targets_for(origin, hours, zones)
        pred = model.predict_quantiles(history, targets, spec.quantiles)
        pred["origin"] = origin
        pred["train_start"] = fit_start
        pred["train_end"] = fit_end
        pred["mase_scale"] = pred["zone_id"].map(scale)
        out.append(pred)
    fc = pd.concat(out, ignore_index=True)
    actual = panel.rename(columns={"hour_ts": "target_ts", "pickups": "y"})[
        ["zone_id", "target_ts", "y"]
    ]
    fc = fc.merge(actual, on=["zone_id", "target_ts"], how="left")
    fc["model"] = model.name if model else "none"
    fc["window"] = spec.window
    return fc


def horizon_bucket(h: pd.Series, buckets: Sequence[Sequence[int]]) -> pd.Series:
    labels = pd.Series("", index=h.index, dtype="object")
    for lo, hi in buckets:
        labels[(h >= lo) & (h <= hi)] = f"h{lo:02d}-{hi:02d}"
    return labels


def evaluate(
    fc: pd.DataFrame,
    quantiles: Sequence[float],
    horizon_buckets: Sequence[Sequence[int]],
    zone_groups: pd.Series | None = None,
    interval: tuple[float, float] | None = None,
) -> pd.DataFrame:
    """Long metric table (model, window, zone_group, horizon_bucket, subset, metric, value, n).

    `subset` is `all`, `y_zero` (hours with y = 0) or `y_pos` (y > 0), so zero-demand hours are
    reported explicitly. `interval` defaults to the outermost quantile pair.
    """
    fc = fc.copy()
    fc["zone_group"] = fc["zone_id"].map(zone_groups) if zone_groups is not None else "all"
    fc["horizon_bucket"] = horizon_bucket(fc["horizon"], horizon_buckets)
    qs = sorted(quantiles)
    lo_q, hi_q = interval or (qs[0], qs[-1])
    lo_c, hi_c = quantile_col(lo_q), quantile_col(hi_q)
    cov_name = f"coverage_{round((hi_q - lo_q) * 100)}"
    width_name = f"width_{round((hi_q - lo_q) * 100)}"

    rows: list[dict[str, object]] = []
    groups = [("all", None)] + [(g, g) for g in sorted(fc["zone_group"].dropna().unique())
                                if g != "all"]
    buckets = [("all", None)] + [(b, b) for b in sorted(fc["horizon_bucket"].unique())]
    subsets = {"all": None, "y_zero": 0, "y_pos": 1}
    for (model, window), d0 in fc.groupby(["model", "window"], sort=True):
        for g_label, g in groups:
            d1 = d0 if g is None else d0[d0["zone_group"] == g]
            for b_label, b in buckets:
                d2 = d1 if b is None else d1[d1["horizon_bucket"] == b]
                for s_label, s in subsets.items():
                    if s is None:
                        d = d2
                    elif s == 0:
                        d = d2[d2["y"] == 0]
                    else:
                        d = d2[d2["y"] > 0]
                    d = d[d["y"].notna()]
                    base = dict(model=model, window=window, zone_group=g_label,
                                horizon_bucket=b_label, subset=s_label, n=len(d))
                    vals: dict[str, float] = {
                        "mae": mt.mae(d["y"], d["point"]),
                        "bias": mt.mean_signed_error(d["y"], d["point"]),
                        cov_name: mt.coverage(d["y"], d[lo_c], d[hi_c]),
                        width_name: mt.interval_width(d[lo_c], d[hi_c]),
                        "n_missing_forecast": float(d["point"].isna().sum()),
                    }
                    if s_label != "y_zero":  # undefined when every actual is zero
                        vals["wape"] = mt.wape(d["y"], d["point"])
                        vals["mase"] = mt.mase(d["y"], d["point"], d["mase_scale"])
                    for q in qs:
                        qc = quantile_col(q)
                        vals[f"pinball_{qc}"] = mt.pinball(d["y"], d[qc], q)
                    rows.extend({**base, "metric": k, "value": v} for k, v in vals.items())
    return pd.DataFrame(rows)
