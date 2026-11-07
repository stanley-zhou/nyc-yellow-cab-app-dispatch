"""Seasonal naive: forecast = value at the same local hour one week earlier (lag 168 h).

Intervals come from empirical quantiles of the in-sample seasonal-naive residuals
(y_t - y_{t-168}) of each zone over the training window, added to the point forecast and
clipped at zero (counts cannot be negative). The `point` column is the raw lag-168 value (used for
WAPE/MASE); q50 = point + median residual, so it can differ slightly from `point`.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from taxi_shock.models.base import BaseForecaster, quantile_col

SEASON = pd.Timedelta(days=7)


def seasonal_residuals(history: pd.DataFrame, season: pd.Timedelta = SEASON) -> pd.DataFrame:
    """In-sample residuals y_t - y_{t-season} per zone (wall-clock lag; DST-safe)."""
    lagged = history[["zone_id", "hour_ts", "pickups"]].copy()
    lagged["hour_ts"] = lagged["hour_ts"] + season
    merged = history.merge(lagged, on=["zone_id", "hour_ts"], suffixes=("", "_lag"))
    merged["resid"] = merged["pickups"] - merged["pickups_lag"]
    return merged[["zone_id", "hour_ts", "resid"]]


class SeasonalNaive(BaseForecaster):
    name = "seasonal_naive"

    def __init__(self, season: pd.Timedelta = SEASON) -> None:
        self.season = season
        self.resid_q_: pd.DataFrame | None = None
        self.scale_: pd.Series | None = None

    def fit(self, history: pd.DataFrame) -> SeasonalNaive:
        res = seasonal_residuals(history, self.season)
        if res.empty:
            raise ValueError("SeasonalNaive.fit needs more than one season of history")
        self._res = res
        self.scale_ = res.assign(a=res["resid"].abs()).groupby("zone_id")["a"].mean()
        self.resid_q_ = None
        return self

    def _quantiles(self, quantiles: Sequence[float]) -> pd.DataFrame:
        qs = sorted(quantiles)
        grouped = self._res.groupby("zone_id")["resid"]
        out = pd.DataFrame({quantile_col(q): grouped.quantile(q) for q in qs})
        return out

    def predict_quantiles(
        self,
        history: pd.DataFrame,
        targets: pd.DataFrame,
        quantiles: Sequence[float],
    ) -> pd.DataFrame:
        if self.resid_q_ is None or list(self.resid_q_.columns) != [
            quantile_col(q) for q in sorted(quantiles)
        ]:
            self.resid_q_ = self._quantiles(quantiles)
        recent = history[history["hour_ts"] >= targets["target_ts"].min() - self.season]
        lag = recent[["zone_id", "hour_ts", "pickups"]].rename(
            columns={"hour_ts": "lag_ts", "pickups": "point"}
        )
        out = targets.assign(lag_ts=targets["target_ts"] - self.season)
        out = out.merge(lag, on=["zone_id", "lag_ts"], how="left").drop(columns="lag_ts")
        out = out.merge(self.resid_q_, left_on="zone_id", right_index=True, how="left")
        for q in sorted(quantiles):
            c = quantile_col(q)
            out[c] = np.clip(out["point"] + out[c].fillna(0.0), 0.0, None)
        return out
