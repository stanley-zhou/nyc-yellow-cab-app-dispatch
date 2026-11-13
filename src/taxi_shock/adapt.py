"""Adaptation strategies (Phase 5, re-scoped by Amendment 4 D6): helpers.

S6 channel-aware: lagged app-channel features for the LightGBM forecaster. From a daily table of
app and total pickups per zone (fct_daily_zone_channel; app = any e-hail app, Amendment 4a) the
feature of a target on day D uses days D-k .. D-1 only (as every demand feature, >= 24 h):

  app_share_7d / app_share_28d   the zone's app pickups / all pickups over the previous 7 / 28 days
  city_app_share_7d              the same over all zones of the table, previous 7 days
"""

from __future__ import annotations

import pandas as pd

CHANNEL_FEATURES = ["app_share_7d", "app_share_28d", "city_app_share_7d"]


def channel_table(daily: pd.DataFrame) -> pd.DataFrame:
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
    for k, name in ((7, "app_share_7d"), (28, "app_share_28d")):
        a = app.rolling(k, min_periods=k).sum().shift(1)
        t = tot.rolling(k, min_periods=k).sum().shift(1)
        r = (a / t.where(t > 0)).rename_axis("day").reset_index()
        parts.append(r.melt(id_vars="day", var_name="zone_id", value_name=name)
                     .set_index(["day", "zone_id"]))
    ca = app.sum(axis=1).rolling(7, min_periods=7).sum().shift(1)
    ct = tot.sum(axis=1).rolling(7, min_periods=7).sum().shift(1)
    res = pd.concat(parts, axis=1).reset_index()
    res["city_app_share_7d"] = res["day"].map(ca / ct)
    return res


def channel_feature_fn(table: pd.DataFrame):
    """Function rows (zone_id, target_ts) -> CHANNEL_FEATURES for the forecaster's `extra`."""
    t = table.set_index(["zone_id", "day"])[CHANNEL_FEATURES]

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


