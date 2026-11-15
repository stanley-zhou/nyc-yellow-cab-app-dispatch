"""Common forecaster interface used by the backtest engine.

Panel convention: a long DataFrame with columns `zone_id` (int), `hour_ts` (naive local
timestamp, hourly) and `pickups` (float). A forecast for origin `o` (local midnight) covers the
local hours of calendar day `o`; `horizon` = hour-of-day + 1 (1..24).

The engine passes `history` already truncated to `hour_ts < origin`, so a model cannot see the
future even by accident; `tests/test_leakage.py` checks this end to end.

Pure computation on DataFrames and arrays; reads and writes no files.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import pandas as pd


def quantile_col(q: float) -> str:
    """Column name for quantile level q, e.g. 0.1 -> 'q10'."""
    return f"q{round(q * 100):02d}"


class BaseForecaster(ABC):
    """fit on history, then predict quantiles for the day starting at `origin`."""

    name: str = "base"

    @abstractmethod
    def fit(self, history: pd.DataFrame, train_start: pd.Timestamp | None = None
            ) -> BaseForecaster:
        """Learn from `history` (all rows have hour_ts < the first origin served by this fit).

        Training targets are the rows with hour_ts >= `train_start` (None: all rows); earlier
        rows may only serve as lag inputs of those targets."""

    @abstractmethod
    def predict_quantiles(
        self,
        history: pd.DataFrame,
        targets: pd.DataFrame,
        quantiles: Sequence[float],
    ) -> pd.DataFrame:
        """Return `targets` (zone_id, target_ts, horizon) plus `point` and one column per quantile.

        `history` contains only rows with hour_ts < origin.
        """
