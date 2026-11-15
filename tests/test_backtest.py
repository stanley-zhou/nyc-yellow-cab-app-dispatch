"""Rolling-origin backtest engine: refit schedules, training windows, day-ahead targets across DST,
training end before every origin, and explicit zero hours in the evaluation.
"""

import numpy as np
import pandas as pd
import pytest

from taxi_shock.backtest import (
    BacktestSpec,
    daily_origins,
    evaluate,
    refit_mask,
    run_backtest,
    targets_for,
    window_start,
)
from taxi_shock.models.seasonal_naive import SeasonalNaive


def test_refit_monthly_marks_first_origin_of_each_month():
    o = daily_origins("2024-01-30", "2024-02-02")
    assert refit_mask(o, "monthly").tolist() == [True, False, True, False]
    assert refit_mask(o, "once").tolist() == [True, False, False, False]
    with pytest.raises(ValueError):
        refit_mask(o, "weekly")


def test_window_start():
    o, ms = pd.Timestamp("2024-06-01"), pd.Timestamp("2022-01-01")
    assert window_start(o, "expanding", ms) == ms
    assert window_start(o, "sliding_24m", ms) == pd.Timestamp("2022-06-01")
    assert window_start(o, "sliding_36m", ms) == ms  # never before model_start


def test_targets_follow_local_calendar_day_across_dst():
    # local wall-clock grid as built by int_hour_grid: 23 hours on spring-forward day
    hours = pd.date_range("2024-03-09", "2024-03-11 23:00", freq="h")
    hours = hours[~((hours.date == pd.Timestamp("2024-03-10").date()) & (hours.hour == 2))]
    t = targets_for(pd.Timestamp("2024-03-10"), pd.DatetimeIndex(hours), np.array([1]))
    assert len(t) == 23 and 3 not in t["horizon"].tolist()
    assert t["horizon"].min() == 1 and t["horizon"].max() == 24


def test_engine_records_training_end_before_origin(synthetic_panel):
    spec = BacktestSpec(origins=daily_origins("2024-01-29", "2024-02-03"),
                        quantiles=(0.1, 0.5, 0.9), refit="monthly")
    fc = run_backtest(synthetic_panel, SeasonalNaive, spec)
    assert (fc["train_end"] < fc["origin"]).all()
    assert fc.groupby("origin")["train_end"].first().nunique() == 2  # Jan fit, Feb refit
    assert fc["y"].notna().all()


def test_evaluate_reports_zero_hours_explicitly(synthetic_panel):
    spec = BacktestSpec(origins=daily_origins("2024-02-01", "2024-02-03"),
                        quantiles=(0.1, 0.5, 0.9))
    fc = run_backtest(synthetic_panel, SeasonalNaive, spec)
    table = evaluate(fc, (0.1, 0.5, 0.9), [[1, 12], [13, 24]])
    assert set(table["subset"]) == {"all", "y_zero", "y_pos"}
    assert {"wape", "mase", "coverage_80", "width_80", "pinball_q10", "pinball_q50",
            "pinball_q90"} <= set(table["metric"])
    n = table.query("metric == 'mae' and horizon_bucket == 'all' and zone_group == 'all'")
    n = n.set_index("subset")["n"]
    assert n["all"] == n["y_zero"] + n["y_pos"]
    assert not ((table["subset"] == "y_zero") & (table["metric"] == "wape")).any()
