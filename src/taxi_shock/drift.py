"""CUSUM and rolling-bias drift monitors (PLAN Phase 3).

Both monitors watch a daily series x_d (here: log of actual / forecast daily totals of a zone
group), standardized with the mean and standard deviation of an in-control calibration period:
z_d = (x_d - mu) / sigma.

CUSUM (two-sided, tabular, Page 1954): S+_d = max(0, S+_{d-1} + z_d - k),
S-_d = max(0, S-_{d-1} - z_d - k); an alarm is raised on the first day either statistic exceeds
h, after which both restart at 0. The reference value k (in sigma units) sets the shift size the
chart is tuned to (k = 0.5 targets a ~1 sigma shift); h is calibrated: the smallest value on a
grid that gives at most `max_alarms` alarms over the calibration period.

Rolling bias: an alarm on the day a run of `consecutive_days` consecutive days with z beyond
+-n_sigma (same sign) is completed; counting restarts after an alarm.

Pure computation on DataFrames and arrays; reads and writes no files.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Alarm:
    position: int
    side: str          # "up" (actual above forecast) or "down"


def standardize(x: pd.Series, calibration: pd.Series) -> tuple[pd.Series, float, float]:
    """(z, mu, sigma) with mu, sigma from the calibration series (sample sd, ddof=1)."""
    mu, sd = float(calibration.mean()), float(calibration.std(ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        raise ValueError("calibration series has no spread")
    return (x - mu) / sd, mu, sd


def cusum(z: np.ndarray, k: float, h: float) -> tuple[np.ndarray, np.ndarray, list[Alarm]]:
    """Two-sided tabular CUSUM with restart after each alarm; (S+, S-, alarms)."""
    z = np.asarray(z, dtype=float)
    if np.isnan(z).any():
        raise ValueError("CUSUM input contains NaN")
    sp, sn = np.zeros(len(z)), np.zeros(len(z))
    alarms: list[Alarm] = []
    up = down = 0.0
    for i, v in enumerate(z):
        up, down = max(0.0, up + v - k), max(0.0, down - v - k)
        sp[i], sn[i] = up, down
        if up > h or down > h:
            alarms.append(Alarm(i, "up" if up > h else "down"))
            up = down = 0.0
    return sp, sn, alarms


def calibrate_h(z: np.ndarray, k: float, max_alarms: int, grid: np.ndarray
                ) -> tuple[float, int]:
    """Smallest h on the ascending `grid` with at most `max_alarms` CUSUM alarms on `z`."""
    for h in np.asarray(grid, dtype=float):
        n = len(cusum(z, k, float(h))[2])
        if n <= max_alarms:
            return float(round(h, 6)), n
    raise ValueError(f"no h on the grid gives <= {max_alarms} alarms")


def rolling_mean_z(z_cal: np.ndarray, z_run: np.ndarray, window: int
                   ) -> tuple[np.ndarray, np.ndarray, float]:
    """Rolling reading of the bias rule (Phase 3 review, fix 2): the trailing `window`-day mean
    of z, standardized by the sd of the same rolling mean over the calibration period (so the
    autocorrelation of daily errors is accounted for). Returns (calibration, run, sd); the first
    window - 1 days of each are NaN."""
    def roll(z):
        return pd.Series(np.asarray(z, dtype=float)).rolling(window, min_periods=window).mean()

    rc, rr = roll(z_cal), roll(z_run)
    sd = float(rc.std(ddof=1))
    return (rc / sd).to_numpy(), (rr / sd).to_numpy(), sd


def rolling_bias_alarms(z: np.ndarray, n_sigma: float, consecutive: int) -> list[Alarm]:
    """Alarm when `consecutive` days in a row have z > n_sigma (up) or z < -n_sigma (down)."""
    alarms: list[Alarm] = []
    run, side = 0, ""
    for i, v in enumerate(np.asarray(z, dtype=float)):
        s = "up" if v > n_sigma else "down" if v < -n_sigma else ""
        run = run + 1 if s and s == side else (1 if s else 0)
        side = s
        if run >= consecutive:
            alarms.append(Alarm(i, side))
            run, side = 0, ""
    return alarms
