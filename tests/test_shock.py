"""taxi_shock.shock: daily sums per zone group and trailing-window error metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_shock.shock import daily_table, rolling_table


def _fc(days: int = 40) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=24 * days, freq="h")
    rows = []
    for z, base in ((1, 10.0), (2, 30.0)):
        y = np.full(len(ts), base)
        point = y * 1.25                                # over-forecast by 25 %
        rows.append(pd.DataFrame({"model": "m", "series": "s", "zone_id": z, "target_ts": ts,
                                  "y": y, "point": point, "in_sample": ts < "2025-01-10"}))
    return pd.concat(rows, ignore_index=True)


GROUPS = {"a": [1], "b": [2], "all": [1, 2]}


def test_daily_sums_and_group_membership():
    d = daily_table(_fc(), GROUPS)
    one = d[(d["zone_group"] == "all") & (d["day"] == pd.Timestamp("2025-01-12"))].iloc[0]
    assert one["actual"] == 24 * 40.0 and one["forecast"] == 24 * 50.0
    assert one["n_hours"] == 48 and one["signed_error"] == 24 * 10.0
    assert not one["in_sample"]
    assert d.loc[d["day"] == pd.Timestamp("2025-01-02"), "in_sample"].all()


def test_rolling_metrics_conventions_and_complete_windows():
    fc = _fc()
    fc.loc[fc["target_ts"] == pd.Timestamp("2025-01-05 03:00"), "point"] = np.nan  # dropped
    t = rolling_table(daily_table(fc, GROUPS), 28)
    r = t[(t["zone_group"] == "b") & (t["window_days"] == 28)]
    assert r["date"].min() == pd.Timestamp("2025-01-28")      # first complete 28-day window
    assert r["wape"].iloc[-1] == pytest.approx(0.25)
    assert r["bias"].iloc[-1] == pytest.approx(7.5)            # forecast - actual per hour
    assert r["log_actual_over_forecast"].iloc[-1] == pytest.approx(np.log(1 / 1.25))
    first = r.iloc[0]
    assert first["in_sample"] and not r["in_sample"].iloc[-1]  # window touching in-sample days
    daily = t[(t["window_days"] == 1) & (t["zone_group"] == "b")]
    assert daily["n_hours"].min() == 23                        # the NaN forecast hour is dropped


def test_forecast_frozen_uses_only_history_before_each_origin(synthetic_panel):
    """Phase 3 review fix 4: poisoning every panel row at or after an origin leaves that origin's
    frozen forecasts unchanged (LightGBM and seasonal naive); poisoning the week before changes
    them (power check)."""
    from taxi_shock.features import WEATHER_FEATURES
    from taxi_shock.models.lgbm_quantile import GlobalLGBMQuantile
    from taxi_shock.models.seasonal_naive import SeasonalNaive
    from taxi_shock.shock import forecast_frozen

    panel = synthetic_panel.sort_values(["hour_ts", "zone_id"], kind="stable").reset_index(
        drop=True)
    hours = pd.DatetimeIndex(panel["hour_ts"].unique())
    rng = np.random.default_rng(3)
    exog = pd.DataFrame({"is_holiday": 0.0, **{c: rng.normal(0, 1, len(hours))
                                               for c in WEATHER_FEATURES}}, index=hours)
    train_end = pd.Timestamp("2024-01-29")
    qs = [0.1, 0.5, 0.9]
    lgbm = GlobalLGBMQuantile(exog, qs, {"learning_rate": 0.1, "num_leaves": 15,
                                         "min_data_in_leaf": 20}, {q: 30 for q in qs}, seed=0,
                              predict_history_days=30)
    models = {"lgbm": lgbm.fit(panel[panel["hour_ts"] < train_end]),
              "naive": SeasonalNaive().fit(panel[panel["hour_ts"] < train_end])}
    origins = pd.date_range("2024-02-01", "2024-02-05", freq="D")
    for name, m in models.items():
        clean = forecast_frozen(m, panel, origins, qs, history_days=30)
        for o in origins[[0, -1]]:
            bad = panel.copy()
            bad.loc[bad["hour_ts"] >= o, "pickups"] = 1e6
            fc = forecast_frozen(m, bad, pd.DatetimeIndex([o]), qs, history_days=30)
            ref = clean[clean["origin"] == o].reset_index(drop=True)
            pd.testing.assert_frame_equal(fc[["q10", "q50", "q90"]].reset_index(drop=True),
                                          ref[["q10", "q50", "q90"]], check_dtype=False)
        o = origins[2]
        bad = panel.copy()
        bad.loc[bad["hour_ts"].between(o - pd.Timedelta(days=7), o - pd.Timedelta(hours=1)),
                "pickups"] = 1e6
        fc = forecast_frozen(m, bad, pd.DatetimeIndex([o]), qs, history_days=30)
        ref = clean[clean["origin"] == o]
        assert not np.allclose(fc["q50"].to_numpy(), ref["q50"].to_numpy()), name
