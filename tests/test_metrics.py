"""Forecast metrics: WAPE, MAE, pinball loss, MASE, coverage, bias, interval width and the
thresholded MAPE, on known values and edge cases (zeros, NaN actuals).
"""

import numpy as np
import pytest

from taxi_shock import metrics as mt


def test_perfect_forecast():
    y = np.array([0.0, 1.0, 5.0, 10.0])
    assert mt.wape(y, y) == 0.0
    assert mt.mae(y, y) == 0.0
    assert mt.coverage(y, y, y) == 1.0
    assert mt.interval_width(y, y) == 0.0
    assert mt.pinball(y, y, 0.9) == 0.0


def test_wape_known_value():
    assert mt.wape([10, 0, 10], [12, 1, 7]) == pytest.approx((2 + 1 + 3) / 20)


def test_wape_all_zero_actuals_is_nan():
    assert np.isnan(mt.wape([0, 0], [1, 1]))


def test_pinball_asymmetry():
    # under-forecast by 10 at tau=0.9 costs 9; over-forecast by 10 costs 1
    assert mt.pinball([10], [0], 0.9) == pytest.approx(9.0)
    assert mt.pinball([0], [10], 0.9) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        mt.pinball([1], [1], 1.0)


def test_mase_scales_and_skips_zero_scale():
    y, f = np.array([10.0, 10.0, 4.0]), np.array([12.0, 8.0, 4.0])
    scale = np.array([2.0, 2.0, 0.0])
    assert mt.mase(y, f, scale) == pytest.approx(1.0)


def test_coverage_and_bias():
    y = np.array([1.0, 5.0, 9.0, 20.0])
    assert mt.coverage(y, np.full(4, 2.0), np.full(4, 10.0)) == pytest.approx(0.5)
    assert mt.mean_signed_error([10, 10], [8, 9]) == pytest.approx(-1.5)


def test_nan_actuals_are_ignored():
    assert mt.wape([10, np.nan], [8, 100]) == pytest.approx(0.2)


def test_mape_min_y_only_large_hours():
    assert mt.mape_min_y([1, 10, 20], [100, 11, 18], 10) == pytest.approx((0.1 + 0.1) / 2)
