"""No forecast may depend on data at or after its origin — with one by-design exception.

For each origin we poison every pickup with hour_ts >= origin (huge numbers and NaN) and assert
that the forecasts are bit-for-bit identical to those from the clean panel. A power check
confirms that poisoning the *past* does change forecasts, so the test can actually fail.
Every trained model of Phase 2 is in MODELS (Chronos: tests/test_chronos_inputs.py).

The exception: LightGBM reads observed weather at the target hour, i.e. over the target day
after the origin (PLAN lists this as a limitation; the "weather_future" Chronos-2 variant gets
the same information). The exogenous table is therefore poisoned only from origin + 1 day on
(beyond the forecast day), which must leave the forecasts unchanged; a power check shows the
target day's weather is used.
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


LGBM_PARAMS = {"learning_rate": 0.1, "num_leaves": 7, "min_data_in_leaf": 5}


def make_lgbm(exog: pd.DataFrame, early_stopping: bool = False):
    def factory():
        if early_stopping:   # rounds chosen per refit on the last week of the training window
            return GlobalLGBMQuantile(exog, (0.1, 0.5, 0.9), LGBM_PARAMS, {}, seed=0, threads=1,
                                      predict_history_days=30,
                                      early_stopping={"holdout_weeks": 1, "rounds": 5,
                                                      "min_delta": 0.0, "max_rounds": 30})
        return GlobalLGBMQuantile(exog, (0.1, 0.5, 0.9), LGBM_PARAMS,
                                  {0.1: 20, 0.5: 20, 0.9: 20}, seed=0, threads=1,
                                  predict_history_days=30)
    return factory


lgbm_factory = make_lgbm(_exog())
lgbm_es_factory = make_lgbm(_exog(), early_stopping=True)


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


@pytest.mark.parametrize("early_stopping", [False, True], ids=["fixed_rounds", "early_stopping"])
@pytest.mark.parametrize("origin", ORIGINS)
def test_exog_beyond_the_target_day_does_not_change_forecasts(synthetic_panel, early_stopping,
                                                              origin):
    clean = _forecast(synthetic_panel, make_lgbm(_exog(), early_stopping), origin)
    beyond = _exog().index >= pd.Timestamp(origin) + pd.Timedelta(days=1)
    for poison in (1e6, np.nan):
        ex = _exog()
        ex.loc[beyond, WEATHER_FEATURES] = poison
        ex.loc[beyond, "is_holiday"] = True
        got = _forecast(synthetic_panel, make_lgbm(ex, early_stopping), origin)
        pd.testing.assert_frame_equal(clean[COLS], got[COLS])


def test_target_day_weather_is_used(synthetic_panel):
    """Power check for the by-design exception: the target day's weather reaches the model."""
    origin = ORIGINS[1]
    clean = _forecast(synthetic_panel, lgbm_factory, origin)
    ex = _exog()
    day = (ex.index >= pd.Timestamp(origin)) & \
        (ex.index < pd.Timestamp(origin) + pd.Timedelta(days=1))
    ex.loc[day, WEATHER_FEATURES] = ex.loc[day, WEATHER_FEATURES] * 50 + 100
    got = _forecast(synthetic_panel, make_lgbm(ex), origin)
    # all quantiles: with noise weather the small q50 booster may never split on it, q10/q90 do
    assert not np.allclose(clean[COLS].to_numpy(), got[COLS].to_numpy())
