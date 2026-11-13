"""taxi_shock.drift: CUSUM, its calibration, and the rolling-bias rule."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_shock.drift import calibrate_h, cusum, rolling_bias_alarms, standardize


def test_cusum_detects_a_level_shift_quickly_and_restarts():
    rng = np.random.default_rng(0)
    z = np.r_[rng.normal(0, 1, 200), rng.normal(-2, 1, 60)]
    _, sn, alarms = cusum(z, k=0.5, h=5.0)
    first = next(a for a in alarms if a.position >= 200)
    assert first.side == "down" and first.position - 200 < 10
    assert sn[first.position] > 5.0
    assert sn[first.position + 1] < 5.0                  # restarted after the alarm


def test_cusum_up_side_and_nan_guard():
    _, _, alarms = cusum(np.r_[np.zeros(5), np.full(5, 3.0)], k=0.5, h=4.0)
    assert alarms[0].side == "up" and alarms[0].position == 6
    with pytest.raises(ValueError):
        cusum(np.array([0.0, np.nan]), 0.5, 4.0)


def test_calibrate_h_is_the_smallest_grid_value_meeting_the_rule():
    rng = np.random.default_rng(1)
    z = rng.normal(0, 1, 366)
    grid = np.arange(0.5, 30.0, 0.05)
    h, n = calibrate_h(z, 0.5, 1, grid)
    assert n <= 1
    assert len(cusum(z, 0.5, h - 0.05)[2]) > 1            # one step lower breaks the rule


def test_rolling_bias_needs_consecutive_same_sign_days():
    z = np.array([2.5] * 6 + [-2.5] + [2.5] * 7 + [0.0] + [-3.0] * 7)
    alarms = rolling_bias_alarms(z, 2.0, 7)
    assert [(a.position, a.side) for a in alarms] == [(13, "up"), (21, "down")]


def test_standardize_uses_calibration_moments():
    cal = pd.Series([1.0, 2.0, 3.0])
    z, mu, sd = standardize(pd.Series([2.0, 4.0]), cal)
    assert mu == 2.0 and sd == 1.0 and list(z) == [0.0, 2.0]
    with pytest.raises(ValueError):
        standardize(pd.Series([1.0]), pd.Series([1.0, 1.0]))


def test_rolling_mean_z_standardizes_by_its_own_calibration_sd():
    """Phase 3 review fix 2: the rolling reading divides the trailing mean by the sd of the same
    rolling mean over the calibration period, and a sustained shift is flagged."""
    from taxi_shock.drift import rolling_bias_alarms, rolling_mean_z

    rng = np.random.default_rng(0)
    cal = rng.normal(0, 1, 366)
    run = np.r_[rng.normal(0, 1, 60), rng.normal(1.5, 1, 60)]
    rc, rr, sd = rolling_mean_z(cal, run, 7)
    assert np.isnan(rc[:6]).all() and np.isnan(rr[:6]).all()
    m = pd.Series(cal).rolling(7).mean()
    assert sd == pytest.approx(float(m.std(ddof=1)))
    assert np.nanstd(rc, ddof=1) == pytest.approx(1.0)
    al = rolling_bias_alarms(np.nan_to_num(rr), 2.0, 7)
    assert al and al[0].side == "up" and al[0].position >= 60
