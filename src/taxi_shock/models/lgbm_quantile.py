"""Global LightGBM quantile forecaster, one model per quantile (PLAN Phase 2, model 3).

One booster per quantile level (`objective='quantile'`), global across the modeled zones with
`zone_id` as a categorical feature. Features come from `taxi_shock.features.build_features`,
computed from the history the engine passes (truncated at the origin), plus the exogenous
calendar/weather table. Hyper-parameters and the number of boosting rounds per quantile come from
the 2023 validation grid (`scripts/04a_lgbm_tune.py` -> results/lgbm_params.json).

Predicted quantiles are sorted per row (monotone rearrangement) so q10 <= q50 <= q90, and clipped
at zero; `point` = q50.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd

from taxi_shock.features import WEATHER_FEATURES, build_features, feature_columns
from taxi_shock.models.base import BaseForecaster, quantile_col

HISTORY_DAYS_FOR_FEATURES = 30   # >= 28-day rolling mean + 1 day; lag_336 needs 14


def training_frame(history: pd.DataFrame, exog: pd.DataFrame, train_start: pd.Timestamp | None,
                   weather: Sequence[str] = WEATHER_FEATURES) -> tuple[pd.DataFrame, np.ndarray]:
    """Feature rows for every history row with hour_ts >= train_start, and their targets."""
    tr = history if train_start is None else history[history["hour_ts"] >= train_start]
    rows = tr[["zone_id", "hour_ts"]].rename(columns={"hour_ts": "target_ts"})
    feats = build_features(history, rows.reset_index(drop=True), exog, weather)
    return feats, tr["pickups"].to_numpy("float32")


class GlobalLGBMQuantile(BaseForecaster):
    name = "lgbm_quantile"

    def __init__(self, exog: pd.DataFrame, quantiles: Sequence[float],
                 params: Mapping[str, object], rounds: Mapping[float, int], seed: int,
                 weather: Sequence[str] = WEATHER_FEATURES, threads: int = 0) -> None:
        self.exog = exog
        self.quantiles = sorted(quantiles)
        self.params = dict(params)
        self.rounds = {float(k): int(v) for k, v in rounds.items()}
        self.seed = seed
        self.weather = list(weather)
        self.threads = threads
        self.cols = feature_columns(self.weather)
        self.boosters_: dict[float, lgb.Booster] = {}
        self.zones_: list[int] = []

    def _matrix(self, feats: pd.DataFrame) -> pd.DataFrame:
        mat = feats[self.cols].astype("float32")
        mat.insert(0, "zone_id", pd.Categorical(feats["zone_id"], categories=self.zones_))
        return mat

    def booster_params(self, q: float) -> dict[str, object]:
        return {"objective": "quantile", "alpha": q, "seed": self.seed,
                "deterministic": True, "force_row_wise": True, "verbose": -1,
                "num_threads": self.threads, **self.params}

    def fit(self, history: pd.DataFrame, train_start: pd.Timestamp | None = None
            ) -> GlobalLGBMQuantile:
        feats, y = training_frame(history, self.exog, train_start, self.weather)
        self.zones_ = sorted(int(z) for z in feats["zone_id"].unique())
        data = lgb.Dataset(self._matrix(feats), y, categorical_feature=["zone_id"],
                           free_raw_data=True)
        self.boosters_ = {q: lgb.train(self.booster_params(q), data,
                                       num_boost_round=self.rounds[q])
                          for q in self.quantiles}
        return self

    def predict_quantiles(self, history: pd.DataFrame, targets: pd.DataFrame,
                          quantiles: Sequence[float]) -> pd.DataFrame:
        first = targets["target_ts"].min().normalize()
        hist = history[history["hour_ts"] >= first - pd.Timedelta(days=HISTORY_DAYS_FOR_FEATURES)]
        feats = build_features(hist, targets[["zone_id", "target_ts"]], self.exog, self.weather)
        mat = self._matrix(feats)
        qs = sorted(quantiles)
        pred = np.column_stack([self.boosters_[q].predict(mat) for q in qs])
        pred = np.clip(np.sort(pred, axis=1), 0.0, None)
        out = targets.copy()
        for j, q in enumerate(qs):
            out[quantile_col(q)] = pred[:, j]
        out["point"] = out[quantile_col(0.5)] if 0.5 in qs else pred[:, len(qs) // 2]
        return out
