"""Adaptation strategies (Phase 5, re-scoped by Amendment 4 D6): helpers.

S6 channel-aware: lagged app-channel features for the LightGBM forecaster. From a daily table of
app and total pickups per zone (fct_daily_zone_channel; app = any e-hail app, Amendment 4a) the
feature of a target on day D uses days D-k .. D-1 only (as every demand feature, >= 24 h); the
windows k come from config `adapt.channel_windows_days` and `adapt.city_window_days`:

  app_share_<k>d        the zone's app pickups / all pickups over the previous k days
  city_app_share_<k>d   the same over all zones of the table
A feature is NaN until its window is fully covered (min_periods = k) or when the zone had no
pickups in it; days missing from the table count as 0 app and 0 total pickups.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def channel_features(windows: Sequence[int], city_window: int) -> list[str]:
    """Feature names, in the order channel_table writes them."""
    return [f"app_share_{k}d" for k in windows] + [f"city_app_share_{city_window}d"]


def channel_table(daily: pd.DataFrame, windows: Sequence[int], city_window: int) -> pd.DataFrame:
    """daily (zone_id, day, app, total) -> per (zone_id, day) the lagged channel features,
    computed only from days strictly before `day`."""
    d = daily.copy()
    d["day"] = pd.to_datetime(d["day"])
    days = pd.date_range(d["day"].min(), d["day"].max(), freq="D")
    app = d.pivot_table(index="day", columns="zone_id", values="app", aggfunc="sum").reindex(
        days).fillna(0.0)
    tot = d.pivot_table(index="day", columns="zone_id", values="total", aggfunc="sum").reindex(
        days).fillna(0.0)
    parts = []
    for k in windows:
        a = app.rolling(k, min_periods=k).sum().shift(1)
        t = tot.rolling(k, min_periods=k).sum().shift(1)
        r = (a / t.where(t > 0)).rename_axis("day").reset_index()
        parts.append(r.melt(id_vars="day", var_name="zone_id", value_name=f"app_share_{k}d")
                     .set_index(["day", "zone_id"]))
    k = city_window
    ca = app.sum(axis=1).rolling(k, min_periods=k).sum().shift(1)
    ct = tot.sum(axis=1).rolling(k, min_periods=k).sum().shift(1)
    res = pd.concat(parts, axis=1).reset_index()
    res[f"city_app_share_{k}d"] = res["day"].map(ca / ct)
    return res


def channel_feature_fn(table: pd.DataFrame, features: Sequence[str]):
    """Function rows (zone_id, target_ts) -> `features` for the forecaster's `extra`."""
    t = table.set_index(["zone_id", "day"])[list(features)]

    def f(rows: pd.DataFrame) -> pd.DataFrame:
        key = pd.MultiIndex.from_arrays([rows["zone_id"].to_numpy(),
                                         rows["target_ts"].dt.normalize().to_numpy()])
        return t.reindex(key).reset_index(drop=True).astype("float64")

    return f


def quarter_label(ts: pd.Series) -> pd.Series:
    return ts.dt.to_period("Q").astype(str)


def rolling_daily_wape(daily: pd.DataFrame, days: int) -> pd.DataFrame:
    """daily (strategy, zone_group, day, abs_err, y) -> rolling `days`-day WAPE per series."""
    out = []
    for (s, g), x in daily.sort_values("day").groupby(["strategy", "zone_group"]):
        x = x.set_index("day")[["abs_err", "y"]].asfreq("D")
        r = x.rolling(days, min_periods=days).sum()
        out.append(pd.DataFrame({"strategy": s, "zone_group": g, "day": r.index,
                                 "rolling_wape": (r["abs_err"] / r["y"]).to_numpy()}))
    return pd.concat(out, ignore_index=True).dropna()


