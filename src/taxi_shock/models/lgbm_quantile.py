"""Global LightGBM quantile forecaster, one model per quantile (PLAN Phase 2, model 3).

Rounds: either fixed per quantile (`rounds`) or, when `early_stopping` is given, chosen at every
refit by early stopping on the last `holdout_weeks` of the training window (those weeks are held
out of the boosting data; the stopped booster is used as is, without a second fit on the full
window). `fit_info_` records rows, rounds and wall time of each fit.

One booster per quantile level (`objective='quantile'`), global across the modeled zones with
`zone_id` as a categorical feature. Features come from `taxi_shock.features.build_features`,
computed from the history the engine passes (truncated at the origin), plus the exogenous
calendar/weather table. Hyper-parameters and the number of boosting rounds per quantile come from
the 2023 validation grid (`scripts/04a_lgbm_tune.py` -> results/lgbm_params.json).

Predicted quantiles are sorted per row (monotone rearrangement) so q10 <= q50 <= q90, and clipped
at zero; `point` = q50.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd

from taxi_shock.features import WEATHER_FEATURES, build_features, feature_columns
from taxi_shock.models.base import BaseForecaster, quantile_col

ExtraFeatures = Callable[[pd.DataFrame], pd.DataFrame]


def training_frame(history: pd.DataFrame, exog: pd.DataFrame, train_start: pd.Timestamp | None,
                   weather: Sequence[str] = WEATHER_FEATURES, extra: ExtraFeatures | None = None
                   ) -> tuple[pd.DataFrame, np.ndarray]:
    """Feature rows for every history row with hour_ts >= train_start, and their targets."""
    tr = history if train_start is None else history[history["hour_ts"] >= train_start]
    rows = tr[["zone_id", "hour_ts"]].rename(columns={"hour_ts": "target_ts"})
    feats = build_features(history, rows.reset_index(drop=True), exog, weather)
    if extra is not None:
        feats = pd.concat([feats, extra(feats).set_index(feats.index)], axis=1)
    return feats, tr["pickups"].to_numpy("float32")


class GlobalLGBMQuantile(BaseForecaster):
    name = "lgbm_quantile"

    def __init__(self, exog: pd.DataFrame, quantiles: Sequence[float],
                 params: Mapping[str, object], rounds: Mapping[float, int], seed: int, *,
                 predict_history_days: int, weather: Sequence[str] = WEATHER_FEATURES,
                 threads: int = 0, early_stopping: Mapping[str, float] | None = None,
                 extra: ExtraFeatures | None = None,
                 extra_cols: Sequence[str] = ()) -> None:
        """`predict_history_days` (models.lgbm.predict_history_days): days of history before
        the target day handed to the feature builder at predict time; must cover the longest
        look-back (28-day rolling mean + 1 day) or the features would differ from training.
        `extra` (Phase 5, S6): a function of the feature rows (zone_id, target_ts) returning
        additional columns `extra_cols`, which must use only days before each target day."""
        self.exog = exog
        self.predict_history_days = int(predict_history_days)
        self.quantiles = sorted(quantiles)
        self.params = dict(params)
        self.rounds = {float(k): int(v) for k, v in rounds.items()}
        self.seed = seed
        self.weather = list(weather)
        self.threads = threads
        self.early_stopping = dict(early_stopping) if early_stopping else None
        self.fit_info_: dict[str, object] = {}
        self.extra = extra
        self.cols = [*feature_columns(self.weather), *extra_cols]
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
        t0 = time.perf_counter()
        feats, y = training_frame(history, self.exog, train_start, self.weather, self.extra)
        self.zones_ = sorted(int(z) for z in feats["zone_id"].unique())
        mat = self._matrix(feats)
        info: dict[str, object] = {"train_start": str(feats["target_ts"].min()),
                                   "train_end": str(feats["target_ts"].max())}
        es = self.early_stopping
        if es is None:
            data = lgb.Dataset(mat, y, categorical_feature=["zone_id"], free_raw_data=True)
            self.boosters_ = {q: lgb.train(self.booster_params(q), data,
                                           num_boost_round=self.rounds[q])
                              for q in self.quantiles}
            info.update(rows_boost=len(y), rows_holdout=0,
                        rounds={str(q): self.rounds[q] for q in self.quantiles})
        else:
            cut = feats["target_ts"].max().normalize() + pd.Timedelta(days=1) \
                - pd.Timedelta(weeks=int(es["holdout_weeks"]))
            hold = (feats["target_ts"] >= cut).to_numpy()
            d_tr = lgb.Dataset(mat[~hold], y[~hold], categorical_feature=["zone_id"],
                               free_raw_data=False)
            d_va = lgb.Dataset(mat[hold], y[hold], categorical_feature=["zone_id"],
                               reference=d_tr, free_raw_data=False)
            self.boosters_ = {}
            for q in self.quantiles:
                self.boosters_[q] = lgb.train(
                    {**self.booster_params(q), "metric": "quantile"}, d_tr,
                    num_boost_round=int(es["max_rounds"]), valid_sets=[d_va],
                    callbacks=[lgb.early_stopping(int(es["rounds"]), verbose=False,
                                                  min_delta=float(es["min_delta"]))])
            info.update(rows_boost=int((~hold).sum()), rows_holdout=int(hold.sum()),
                        holdout_start=str(cut),
                        rounds={str(q): int(b.best_iteration) for q, b in self.boosters_.items()})
        info["seconds"] = round(time.perf_counter() - t0, 1)
        self.fit_info_ = info
        return self

    def predict_quantiles(self, history: pd.DataFrame, targets: pd.DataFrame,
                          quantiles: Sequence[float]) -> pd.DataFrame:
        first = targets["target_ts"].min().normalize()
        hist = history[history["hour_ts"] >= first - pd.Timedelta(days=self.predict_history_days)]
        feats = build_features(hist, targets[["zone_id", "target_ts"]], self.exog, self.weather)
        if self.extra is not None:
            feats = pd.concat([feats, self.extra(feats).set_index(feats.index)], axis=1)
        mat = self._matrix(feats)
        qs = sorted(quantiles)
        pred = np.column_stack([self.boosters_[q].predict(mat) for q in qs])  # best iteration
        pred = np.clip(np.sort(pred, axis=1), 0.0, None)
        out = targets.copy()
        for j, q in enumerate(qs):
            out[quantile_col(q)] = pred[:, j]
        out["point"] = out[quantile_col(0.5)] if 0.5 in qs else pred[:, len(qs) // 2]
        return out
