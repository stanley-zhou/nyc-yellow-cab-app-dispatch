"""Forecast-based counterfactual from the frozen model (PLAN Phase 4).

Aggregate the CBD's hourly pickups and the frozen-LightGBM point forecasts to days; the implied
effect of a month is the mean over its days of (actual - forecast) / forecast. Months up to the
model's training end are flagged in-sample.
"""

from __future__ import annotations

import pandas as pd


def implied_effect_by_month(fc: pd.DataFrame, train_end: str) -> pd.DataFrame:
    """`fc`: hourly rows (target_ts, y, point) of the treated zones. Returns one row per month:
    actual, forecast (sums), mean_daily_rel, n_days, in_sample."""
    fc = fc[fc["y"].notna() & fc["point"].notna()]
    day = fc.assign(day=fc["target_ts"].dt.normalize()).groupby("day")[["y", "point"]].sum()
    day["rel"] = (day["y"] - day["point"]) / day["point"]
    m = day.groupby(day.index.to_period("M")).agg(
        actual=("y", "sum"), forecast=("point", "sum"), mean_daily_rel=("rel", "mean"),
        n_days=("rel", "size")).reset_index().rename(columns={"day": "month"})
    m["in_sample"] = m["month"] <= pd.Timestamp(train_end).to_period("M")
    m["month"] = m["month"].astype(str)
    return m
