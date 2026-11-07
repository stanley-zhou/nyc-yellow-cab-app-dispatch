"""Forecast metrics: WAPE (primary), MASE, pinball loss, interval coverage and width.

All functions take 1-D array-likes and ignore rows where `y` is NaN. MAPE is deliberately not
offered as a primary metric (zeros and small counts); `mape_min_y` applies it only to hours with
`y >= min_y` and its name says so.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

ArrayLike = npt.ArrayLike


def _arr(*xs: ArrayLike) -> list[np.ndarray]:
    arrs = [np.asarray(x, dtype="float64") for x in xs]
    mask = ~np.isnan(arrs[0])
    for a in arrs[1:]:
        mask &= ~np.isnan(a)
    return [a[mask] for a in arrs]


def wape(y: ArrayLike, yhat: ArrayLike) -> float:
    """sum |y - yhat| / sum y. NaN if the actuals sum to zero."""
    y_, f_ = _arr(y, yhat)
    denom = y_.sum()
    return float(np.abs(y_ - f_).sum() / denom) if denom > 0 else float("nan")


def mae(y: ArrayLike, yhat: ArrayLike) -> float:
    y_, f_ = _arr(y, yhat)
    return float(np.abs(y_ - f_).mean()) if y_.size else float("nan")


def mean_signed_error(y: ArrayLike, yhat: ArrayLike) -> float:
    """mean(yhat - y): negative = under-forecast."""
    y_, f_ = _arr(y, yhat)
    return float((f_ - y_).mean()) if y_.size else float("nan")


def mase(y: ArrayLike, yhat: ArrayLike, scale: ArrayLike) -> float:
    """Mean of |y - yhat| / scale, where `scale` is the in-sample seasonal-naive MAE of each row's
    series (broadcast per row). Rows with scale <= 0 (series that never changed) are excluded."""
    y_, f_, s_ = _arr(y, yhat, scale)
    ok = s_ > 0
    return float((np.abs(y_[ok] - f_[ok]) / s_[ok]).mean()) if ok.any() else float("nan")


def pinball(y: ArrayLike, q_pred: ArrayLike, tau: float) -> float:
    """Mean pinball (quantile) loss at level `tau`."""
    if not 0.0 < tau < 1.0:
        raise ValueError("tau must be in (0, 1)")
    y_, q_ = _arr(y, q_pred)
    diff = y_ - q_
    return float(np.maximum(tau * diff, (tau - 1.0) * diff).mean()) if y_.size else float("nan")


def coverage(y: ArrayLike, lo: ArrayLike, hi: ArrayLike) -> float:
    """Share of actuals inside the closed interval [lo, hi]."""
    y_, lo_, hi_ = _arr(y, lo, hi)
    return float(((y_ >= lo_) & (y_ <= hi_)).mean()) if y_.size else float("nan")


def interval_width(lo: ArrayLike, hi: ArrayLike) -> float:
    lo_, hi_ = _arr(lo, hi)
    return float((hi_ - lo_).mean()) if lo_.size else float("nan")


def mape_min_y(y: ArrayLike, yhat: ArrayLike, min_y: float) -> float:
    """MAPE restricted to hours with y >= min_y (never a primary metric)."""
    y_, f_ = _arr(y, yhat)
    ok = y_ >= min_y
    return float((np.abs(y_[ok] - f_[ok]) / y_[ok]).mean()) if ok.any() else float("nan")
