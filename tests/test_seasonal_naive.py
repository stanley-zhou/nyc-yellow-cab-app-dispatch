"""Seasonal-naive baseline: exact on a weekly-periodic series; quantiles ordered and >= 0."""

import numpy as np
import pandas as pd

from taxi_shock.backtest import targets_for
from taxi_shock.models.seasonal_naive import SeasonalNaive


def test_exact_on_periodic_series():
    hours = pd.date_range("2024-01-01", periods=24 * 7 * 3, freq="h")
    weekly = (hours.day_of_week * 24 + hours.hour).to_numpy().astype("float32")
    panel = pd.DataFrame({"zone_id": 7, "hour_ts": hours, "pickups": weekly})
    origin = pd.Timestamp("2024-01-15")
    hist = panel[panel.hour_ts < origin]
    m = SeasonalNaive().fit(hist)
    tg = targets_for(origin, pd.DatetimeIndex(hours), np.array([7]))
    pred = m.predict_quantiles(hist, tg, [0.1, 0.5, 0.9])
    truth = panel.set_index("hour_ts").loc[tg.target_ts, "pickups"].to_numpy()
    np.testing.assert_allclose(pred["point"], truth)
    # zero residuals -> degenerate interval equal to the point forecast
    np.testing.assert_allclose(pred["q10"], truth)
    np.testing.assert_allclose(pred["q90"], truth)


def test_quantiles_ordered_and_nonnegative(synthetic_panel):
    origin = pd.Timestamp("2024-02-01")
    hist = synthetic_panel[synthetic_panel.hour_ts < origin]
    m = SeasonalNaive().fit(hist)
    tg = targets_for(origin, pd.DatetimeIndex(synthetic_panel.hour_ts.unique()),
                     np.array([1, 2, 3]))
    p = m.predict_quantiles(hist, tg, [0.1, 0.5, 0.9])
    assert (p["q10"] <= p["q50"]).all() and (p["q50"] <= p["q90"]).all()
    assert (p[["q10", "q50", "q90"]] >= 0).all().all()
    assert len(p) == 3 * 24 and p["horizon"].between(1, 24).all()
