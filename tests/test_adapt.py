"""Phase 5 S6 end to end (review fix 9): the LightGBM forecaster with the channel features,
run through run_backtest, must not depend on the channel table at or after the origin day; a
power check shows that the channel table before the origin is used."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from test_leakage import LGBM_PARAMS, _exog

from taxi_shock.adapt import channel_feature_fn, channel_features, channel_table
from taxi_shock.backtest import BacktestSpec, run_backtest
from taxi_shock.models.lgbm_quantile import GlobalLGBMQuantile

WIN, CITY = (7, 28), 7
FEATS = channel_features(WIN, CITY)
ORIGINS = ["2024-01-29", "2024-02-05"]
COLS = ["point", "q10", "q50", "q90"]


def _channel_daily(panel: pd.DataFrame) -> pd.DataFrame:
    d = panel.assign(day=panel["hour_ts"].dt.normalize()).groupby(
        ["zone_id", "day"], as_index=False)["pickups"].sum().rename(columns={"pickups": "total"})
    # informative shares (synthetic data only): a zone-day's app share rises with the next
    # day's volume, so the trailing-share features carry signal the model can use
    nxt = d.groupby("zone_id")["total"].shift(-1).fillna(d["total"])
    rel = nxt / d.groupby("zone_id")["total"].transform("mean")
    d["app"] = np.floor(d["total"] * np.clip(0.3 * rel, 0.02, 0.95))
    return d


def _forecast(panel: pd.DataFrame, daily: pd.DataFrame, origin: str) -> pd.DataFrame:
    extra = channel_feature_fn(channel_table(daily, WIN, CITY), FEATS)
    exog = _exog()

    def factory():
        return GlobalLGBMQuantile(exog, (0.1, 0.5, 0.9), LGBM_PARAMS,
                                  {0.1: 20, 0.5: 20, 0.9: 20}, seed=0, threads=1,
                                  predict_history_days=30, extra=extra, extra_cols=FEATS)

    spec = BacktestSpec(origins=pd.DatetimeIndex([origin]), quantiles=(0.1, 0.5, 0.9),
                        window="expanding", refit="daily")
    fc = run_backtest(panel, factory, spec)
    return fc.sort_values(["zone_id", "target_ts"]).reset_index(drop=True)


@pytest.mark.parametrize("origin", ORIGINS)
def test_channel_table_from_origin_day_does_not_change_s6_forecasts(synthetic_panel, origin):
    daily = _channel_daily(synthetic_panel)
    clean = _forecast(synthetic_panel, daily, origin)
    for poison in (1e6, 0.0):
        p = daily.copy()
        late = p["day"] >= pd.Timestamp(origin)
        p.loc[late, "app"] = poison
        p.loc[late, "total"] = poison
        pd.testing.assert_frame_equal(clean[COLS], _forecast(synthetic_panel, p, origin)[COLS])


def test_channel_table_before_origin_changes_s6_forecasts(synthetic_panel):
    origin = ORIGINS[0]
    daily = _channel_daily(synthetic_panel)
    clean = _forecast(synthetic_panel, daily, origin)
    p = daily.copy()
    early = p["day"] < pd.Timestamp(origin)
    # shuffle the shares across zone-days (a monotone change such as s -> 1 - s would leave
    # tree partitions, and so the forecasts, unchanged)
    share = (p.loc[early, "app"] / p.loc[early, "total"]).to_numpy()
    p.loc[early, "app"] = np.floor(p.loc[early, "total"]
                                   * np.random.default_rng(3).permutation(share))
    got = _forecast(synthetic_panel, p, origin)
    assert not np.allclose(clean[COLS].to_numpy(), got[COLS].to_numpy())
