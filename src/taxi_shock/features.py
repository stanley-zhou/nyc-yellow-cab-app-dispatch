"""Leakage-safe, horizon-aware feature builder (Phase 2). Lags are >= 24 h by design.

The same definitions as the dbt model `features_demand`, computed in Python from whatever demand
history the caller passes, so a model can only ever see the history it is given (the backtest
engine truncates it at the origin; tests/test_leakage.py poisons everything after the origin).
`tests/test_features_python.py` checks that, given the full panel, the values equal
`features_demand` in the warehouse.

Definitions (day-ahead task: every target hour lies on the origin's calendar day D):
  lag_k            pickups at the same local hour k/24 calendar days earlier (wall clock)
  mean_same_hour_prev_7d / _28d   mean over the same local hour of days D-7..D-1 / D-28..D-1,
                   over the hours that exist; NULL while the window reaches before the first
                   day of the history
  mean_prev_day    mean hourly pickups of day D-1
  horizon          local hour + 1 (1..24): forecasts are issued at 00:00 of day D
  calendar         dow (0 = Monday), dom, month, is_weekend, is_holiday (exogenous table)
  weather          observed hourly weather at the target hour (PLAN limitation: actual weather
                   is used as if known in advance)
Every input of a target on day D comes from days <= D-1 or from the exogenous table.

Pure computation on DataFrames and arrays; reads and writes no files.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

LAGS_DAYS: dict[str, int] = {"lag_24": 1, "lag_48": 2, "lag_168": 7, "lag_336": 14}
ROLLING_DAYS: dict[str, int] = {"mean_same_hour_prev_7d": 7, "mean_same_hour_prev_28d": 28}
DEMAND_FEATURES: list[str] = [*LAGS_DAYS, *ROLLING_DAYS, "mean_prev_day"]
CALENDAR_FEATURES: list[str] = ["horizon", "dow", "dom", "month", "is_weekend", "is_holiday"]
WEATHER_FEATURES: list[str] = ["temp_f", "apparent_temp_f", "precip_in", "rain_in", "snowfall_in",
                               "weather_code", "cloud_cover_pct", "wind_mph", "rel_humidity_pct"]


def _wide(history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """history -> matrix indexed by consecutive local dates, columns (zone_id, hour)."""
    h = history[["zone_id", "hour_ts", "pickups"]]
    date = h["hour_ts"].dt.normalize()
    w = pd.DataFrame({"zone_id": h["zone_id"].to_numpy(), "hour": h["hour_ts"].dt.hour.to_numpy(),
                      "date": date.to_numpy(), "pickups": h["pickups"].to_numpy("float64")})
    wide = w.pivot_table(index="date", columns=["zone_id", "hour"], values="pickups",
                         aggfunc="sum", dropna=False)
    days = pd.date_range(date.min(), date.max(), freq="D")
    return wide.reindex(days), days


def demand_features(history: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """Demand-history features for `rows` (zone_id, target_ts) from `history` only.

    `history` is (zone_id, hour_ts, pickups); nothing in it at or after a row's calendar day is
    used (every feature is a shift by >= 1 day). Hours missing from `history` (spring-forward
    02:00) are NaN, as in the warehouse.
    """
    wide, days = _wide(history)
    d0 = days.min()
    # the target days may lie after the last history day (prediction): extend the date axis
    target_days = pd.DatetimeIndex(rows["target_ts"].dt.normalize().unique())
    ext = wide.reindex(days.union(target_days))
    present = ext.notna().astype("float64")
    filled = ext.fillna(0.0)
    mats: dict[str, pd.DataFrame] = {name: ext.shift(k) for name, k in LAGS_DAYS.items()}
    for name, n in ROLLING_DAYS.items():
        s = filled.rolling(n, min_periods=1).sum().shift(1)
        c = present.rolling(n, min_periods=1).sum().shift(1)
        m = s / c.where(c > 0)
        m[m.index < d0 + pd.Timedelta(days=n)] = np.nan
        mats[name] = m
    out = rows[["zone_id", "target_ts"]].copy()
    ri = ext.index.get_indexer(rows["target_ts"].dt.normalize())
    ci = ext.columns.get_indexer(pd.MultiIndex.from_arrays(
        [rows["zone_id"].to_numpy(), rows["target_ts"].dt.hour.to_numpy()]))
    for name, mat in mats.items():
        out[name] = _take(mat.to_numpy(), ri, ci)
    zone_sum = filled.T.groupby(level="zone_id").sum().T
    zone_cnt = present.T.groupby(level="zone_id").sum().T
    daily_mean = (zone_sum / zone_cnt.where(zone_cnt > 0)).shift(1)   # mean over hours present
    zi = daily_mean.columns.get_indexer(rows["zone_id"].to_numpy())
    out["mean_prev_day"] = _take(daily_mean.to_numpy(), ri, zi)
    return out


def _take(mat: np.ndarray, ri: np.ndarray, ci: np.ndarray) -> np.ndarray:
    """mat[ri, ci] with NaN where a row or column index is missing (-1)."""
    ok = (ri >= 0) & (ci >= 0)
    res = np.full(len(ri), np.nan)
    res[ok] = mat[ri[ok], ci[ok]]
    return res


def build_features(history: pd.DataFrame, rows: pd.DataFrame, exog: pd.DataFrame,
                   weather: Sequence[str] = WEATHER_FEATURES) -> pd.DataFrame:
    """Full feature frame for `rows` (zone_id, target_ts): demand history + calendar + weather.

    `exog` is indexed by hour_ts with the calendar flags and weather columns
    (`taxi_shock.io.read_exog`)."""
    out = demand_features(history, rows)
    ts = out["target_ts"]
    out["horizon"] = (ts.dt.hour + 1).astype("int16")
    out["dow"] = ts.dt.day_of_week.astype("int16")
    out["dom"] = ts.dt.day.astype("int16")
    out["month"] = ts.dt.month.astype("int16")
    ex = exog.reindex(ts.to_numpy())
    out["is_weekend"] = (ts.dt.day_of_week >= 5).astype("int8").to_numpy()
    out["is_holiday"] = ex["is_holiday"].astype("float64").to_numpy()
    for c in weather:
        out[c] = ex[c].to_numpy("float64")
    return out


def feature_columns(weather: Sequence[str] = WEATHER_FEATURES) -> list[str]:
    """Model feature list (zone_id is added by the model as a categorical)."""
    return [*DEMAND_FEATURES, *CALENDAR_FEATURES, *weather]
