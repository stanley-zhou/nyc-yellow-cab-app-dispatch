"""No forecast may depend on data at or after its origin.

For each origin we poison every value with hour_ts >= origin (huge numbers and NaN) and assert
that the forecasts are bit-for-bit identical to those from the clean panel. A power check
confirms that poisoning the *past* does change forecasts, so the test can actually fail.
Every trained model of Phase 2 is in MODELS (Chronos: tests/test_chronos_inputs.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_shock.backtest import BacktestSpec, run_backtest
from taxi_shock.features import WEATHER_FEATURES
from taxi_shock.models.lgbm_quantile import GlobalLGBMQuantile
from taxi_shock.models.seasonal_naive import SeasonalNaive
from taxi_shock.models.stat_baselines import ETSDailyProfile


def _exog() -> pd.DataFrame:
    hours = pd.date_range("2023-12-01", "2024-03-01", freq="h")
    rng = np.random.default_rng(1)
    ex = pd.DataFrame({c: rng.normal(size=len(hours)) for c in WEATHER_FEATURES}, index=hours)
    ex["is_holiday"] = False
    return ex


def lgbm_factory():
    return GlobalLGBMQuantile(_exog(), (0.1, 0.5, 0.9),
                              {"learning_rate": 0.1, "num_leaves": 7, "min_data_in_leaf": 5},
                              {0.1: 20, 0.5: 20, 0.9: 20}, seed=0, threads=1)


def lgbm_es_factory():
    """Rounds chosen per refit by early stopping on the last week of the training window."""
    return GlobalLGBMQuantile(_exog(), (0.1, 0.5, 0.9),
                              {"learning_rate": 0.1, "num_leaves": 7, "min_data_in_leaf": 5},
                              {}, seed=0, threads=1,
                              early_stopping={"holdout_weeks": 1, "rounds": 5,
                                              "min_delta": 0.0, "max_rounds": 30})


def stat_factory():
    return ETSDailyProfile(profile_weeks=2, residual_weeks=2)


lgbm_factory.name = "lgbm_quantile"
lgbm_es_factory.name = "lgbm_quantile_early_stopping"
stat_factory.name = "stat_ets_profile"
MODELS = [SeasonalNaive, stat_factory, lgbm_factory, lgbm_es_factory]
ORIGINS = ["2024-01-22", "2024-01-29", "2024-02-05"]
COLS = ["point", "q10", "q50", "q90"]


def _forecast(panel: pd.DataFrame, factory, origin: str) -> pd.DataFrame:
    spec = BacktestSpec(origins=pd.DatetimeIndex([origin]), quantiles=(0.1, 0.5, 0.9),
                        window="expanding", refit="daily")
    fc = run_backtest(panel, factory, spec)
    return fc.sort_values(["zone_id", "target_ts"]).reset_index(drop=True)


@pytest.mark.parametrize("factory", MODELS, ids=lambda f: f.name)
@pytest.mark.parametrize("origin", ORIGINS)
def test_future_poisoning_does_not_change_forecasts(synthetic_panel, factory, origin):
    clean = _forecast(synthetic_panel, factory, origin)
    future = synthetic_panel["hour_ts"] >= pd.Timestamp(origin)
    for poison in (1e6, np.nan):
        poisoned = synthetic_panel.copy()
        poisoned.loc[future, "pickups"] = poison
        got = _forecast(poisoned, factory, origin)
        pd.testing.assert_frame_equal(clean[COLS], got[COLS])


@pytest.mark.parametrize("factory", MODELS, ids=lambda f: f.name)
def test_past_poisoning_changes_forecasts(synthetic_panel, factory):
    origin = ORIGINS[1]
    clean = _forecast(synthetic_panel, factory, origin)
    poisoned = synthetic_panel.copy()
    past = poisoned["hour_ts"] < pd.Timestamp(origin)
    poisoned.loc[past, "pickups"] = poisoned.loc[past, "pickups"] * 3 + 5
    got = _forecast(poisoned, factory, origin)
    assert not np.allclose(clean["point"], got["point"])
