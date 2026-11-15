"""Statistical baseline (PLAN Phase 2, model 2): AutoETS with weekly seasonality, per zone.

statsforecast's ETS supports seasonal periods up to 24 only (in 2.0.1 a longer season is silently
dropped), so weekly seasonality on hourly data cannot be an ETS season directly. The baseline is
the standard top-down construction instead:
  1. daily total per zone ~ AutoETS(season_length=7) on local-day totals (weekly seasonality),
     fitted on the training window, re-filtered (`forward`, no re-estimation) with the daily
     history up to day D-1 at every origin;
  2. hourly split = the zone's hour-of-day share profile over the `profile_weeks` previous
     same weekdays (days D-7, D-14, ...), renormalised over the target day's hours (23 on
     spring-forward days);
  3. intervals: point + empirical quantiles of in-sample hourly residuals per (zone, hour of day)
     over the last `residual_weeks` weeks of the training window, where the in-sample forecast is
     the ETS one-step fitted daily total x the same lagged profile; clipped at zero.
If ETS cannot be fitted or re-filtered for a zone (e.g. a multiplicative model meeting a zero
day), that zone falls back to the daily total of day D-7; fallbacks are counted
(`fallbacks_`) and logged.

Pure computation on DataFrames and arrays; reads and writes no files.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np
import pandas as pd
from statsforecast.models import AutoETS

from taxi_shock.models.base import BaseForecaster, quantile_col

log = logging.getLogger(__name__)


def _hourly_wide(history: pd.DataFrame) -> pd.DataFrame:
    """date x (zone_id, hour) matrix over consecutive local dates (NaN = hour absent)."""
    h = pd.DataFrame({"zone_id": history["zone_id"].to_numpy(),
                      "date": history["hour_ts"].dt.normalize().to_numpy(),
                      "hour": history["hour_ts"].dt.hour.to_numpy(),
                      "y": history["pickups"].to_numpy("float64")})
    w = h.pivot_table(index="date", columns=["zone_id", "hour"], values="y", aggfunc="sum",
                      dropna=False)
    return w.reindex(pd.date_range(w.index.min(), w.index.max(), freq="D"))


def lagged_profile(wide: pd.DataFrame, weeks: int, days: pd.DatetimeIndex | None = None
                   ) -> pd.DataFrame:
    """Hour-of-day shares per zone for each date from the `weeks` previous same weekdays."""
    idx = wide.index if days is None else wide.index.union(days)
    w = wide.reindex(idx).fillna(0.0)
    s = sum(w.shift(7 * k) for k in range(1, weeks + 1))
    tot = s.T.groupby(level="zone_id").transform("sum").T
    return s / tot.where(tot > 0)


class ETSDailyProfile(BaseForecaster):
    name = "stat_ets_profile"

    def __init__(self, season_length: int = 7, profile_weeks: int = 8,
                 residual_weeks: int = 52) -> None:
        self.season_length = season_length
        self.profile_weeks = profile_weeks
        self.residual_weeks = residual_weeks
        self.models_: dict[int, AutoETS | None] = {}
        self.train_start_: pd.Timestamp | None = None
        self.resid_q_: pd.DataFrame | None = None
        self.fallbacks_ = 0

    @staticmethod
    def _daily(history: pd.DataFrame, start: pd.Timestamp | None) -> pd.DataFrame:
        h = history if start is None else history[history["hour_ts"] >= start]
        d = h.assign(date=h["hour_ts"].dt.normalize()).groupby(["date", "zone_id"])["pickups"]
        return d.sum().unstack("zone_id").astype("float64")  # noqa: PD010

    def fit(self, history: pd.DataFrame, train_start: pd.Timestamp | None = None
            ) -> ETSDailyProfile:
        self.train_start_ = train_start
        daily = self._daily(history, train_start)
        wide = _hourly_wide(history)
        prof = lagged_profile(wide, self.profile_weeks)
        res_from = (daily.index.max() - pd.Timedelta(weeks=self.residual_weeks)
                    + pd.Timedelta(days=1))
        resid = []
        for z in daily.columns:
            y = daily[z].to_numpy()
            try:
                m = AutoETS(season_length=self.season_length).fit(y)
                fitted = m.predict_in_sample()["fitted"]
            except Exception as err:  # noqa: BLE001 - any ETS failure -> documented fallback
                log.warning("zone %s: AutoETS fit failed (%s); weekly-naive fallback", z, err)
                m, fitted = None, np.r_[np.full(7, np.nan), y[:-7]]
            self.models_[int(z)] = m
            fd = pd.Series(fitted, index=daily.index)
            fd = fd[fd.index >= res_from]
            hours = [c for c in wide.columns if c[0] == z]
            sub = wide.loc[fd.index, hours]
            pr = prof.loc[fd.index, hours]
            r = sub.to_numpy() - fd.to_numpy()[:, None] * pr.to_numpy()
            resid.append(pd.DataFrame(r, columns=[h for _, h in hours]).melt(
                var_name="hour", value_name="r").assign(zone_id=int(z)))
        self._resid = pd.concat(resid, ignore_index=True).dropna()
        self.resid_q_ = None
        return self

    def predict_quantiles(self, history: pd.DataFrame, targets: pd.DataFrame,
                          quantiles: Sequence[float]) -> pd.DataFrame:
        qs = sorted(quantiles)
        cols = [quantile_col(q) for q in qs]
        if self.resid_q_ is None or list(self.resid_q_.columns) != cols:
            g = self._resid.groupby(["zone_id", "hour"])["r"]
            self.resid_q_ = pd.DataFrame({quantile_col(q): g.quantile(q) for q in qs})
        day = targets["target_ts"].min().normalize()
        daily = self._daily(history, self.train_start_)
        totals = {}
        for z, m in self.models_.items():
            y = daily[z].to_numpy() if z in daily else np.array([])
            tot = np.nan
            if m is not None and len(y):
                try:
                    tot = float(m.forward(y=y, h=1)["mean"][0])
                except Exception as err:  # noqa: BLE001
                    log.warning("zone %s on %s: ETS forward failed (%s)", z, day.date(), err)
            if not np.isfinite(tot):
                self.fallbacks_ += 1
                tot = float(daily[z].iloc[-7]) if z in daily and len(daily) >= 7 else np.nan
            totals[z] = max(tot, 0.0)
        recent = history[history["hour_ts"] >= day - pd.Timedelta(weeks=self.profile_weeks)]
        prof = lagged_profile(_hourly_wide(recent), self.profile_weeks,
                              pd.DatetimeIndex([day])).loc[day]
        out = targets.copy()
        hour = out["target_ts"].dt.hour
        share = prof.reindex(pd.MultiIndex.from_arrays([out["zone_id"], hour])).to_numpy()
        share = np.nan_to_num(share, nan=0.0)
        norm = pd.Series(share).groupby(out["zone_id"].to_numpy()).transform("sum").to_numpy()
        share = np.where(norm > 0, share / np.where(norm > 0, norm, 1), 0.0)
        out["point"] = out["zone_id"].map(totals).to_numpy() * share
        rq = self.resid_q_.reindex(pd.MultiIndex.from_arrays([out["zone_id"], hour]))
        qv = out["point"].to_numpy()[:, None] + np.nan_to_num(rq[cols].to_numpy(), nan=0.0)
        qv = np.clip(np.sort(qv, axis=1), 0.0, None)
        for j, c in enumerate(cols):
            out[c] = qv[:, j]
        return out
