"""features_demand lag/rolling values vs an independent pandas computation (full warehouse).

The pandas side works on (local date, local hour) keys taken from fct_hourly_zone_demand, so a
"k-day lag" is the same wall-clock hour k calendar days earlier, whatever the DST offset. Checked
for two zones (one busy CBD zone, one sparse outer zone) over the spring-forward and fall-back
weeks of 2024, including the NULL lag at the non-existent 02:00 hour.
"""

import numpy as np
import pandas as pd
import pytest

from taxi_shock.io import connect

pytestmark = pytest.mark.warehouse

ZONES = [161, 3]                       # Midtown Center (CBD) and a sparse Bronx zone
WINDOWS = [("2024-03-06", "2024-03-20"), ("2024-10-29", "2024-11-12")]
LAGS = {"lag_24": 1, "lag_48": 2, "lag_168": 7, "lag_336": 14}
COLS = list(LAGS) + ["mean_same_hour_prev_7d", "mean_same_hour_prev_28d", "mean_prev_day"]


def _expected(hourly: pd.DataFrame) -> pd.DataFrame:
    h = hourly.assign(date=hourly["hour_ts"].dt.normalize(), hour=hourly["hour_ts"].dt.hour)
    by_key = h.set_index(["zone_id", "date", "hour"])["pickups"]
    daily_mean = h.groupby(["zone_id", "date"])["pickups"].mean()
    out = h[["zone_id", "hour_ts", "date", "hour"]].copy()
    for col, k in LAGS.items():
        keys = list(zip(out["zone_id"], out["date"] - pd.Timedelta(days=k), out["hour"],
                        strict=True))
        out[col] = by_key.reindex(keys).to_numpy()
    for col, n in (("mean_same_hour_prev_7d", 7), ("mean_same_hour_prev_28d", 28)):
        vals = np.column_stack([
            by_key.reindex(list(zip(out["zone_id"], out["date"] - pd.Timedelta(days=d),
                                    out["hour"], strict=True))).to_numpy()
            for d in range(1, n + 1)])
        cnt = np.sum(~np.isnan(vals), axis=1)
        with np.errstate(invalid="ignore"):
            out[col] = np.where(cnt > 0, np.nansum(vals, axis=1) / np.maximum(cnt, 1), np.nan)
    out["mean_prev_day"] = daily_mean.reindex(
        list(zip(out["zone_id"], out["date"] - pd.Timedelta(days=1), strict=True))).to_numpy()
    return out


@pytest.mark.parametrize("lo, hi", WINDOWS)
def test_lag_and_rolling_features_match_pandas(warehouse_db, lo, hi):
    hist_lo = (pd.Timestamp(lo) - pd.Timedelta(days=30)).date().isoformat()
    with connect(warehouse_db) as con:
        hourly = con.execute(
            "select zone_id, hour_ts, pickups::double as pickups from fct_hourly_zone_demand "
            "where zone_id in (?, ?) and hour_ts >= ? and hour_ts < ?",
            [*ZONES, hist_lo, hi]).df()
        feats = con.execute(
            f"select zone_id, hour_ts, {', '.join(COLS)} from features_demand "
            "where zone_id in (?, ?) and hour_ts >= ? and hour_ts < ?",
            [*ZONES, lo, hi]).df()
    exp = _expected(hourly)
    m = feats.merge(exp, on=["zone_id", "hour_ts"], suffixes=("", "_exp"))
    assert len(m) == len(feats) > 0
    for col in COLS:
        got, want = m[col].astype(float), m[f"{col}_exp"].astype(float)
        assert (got.isna() == want.isna()).all(), f"{col}: NULL pattern differs"
        np.testing.assert_allclose(got[got.notna()], want[want.notna()], rtol=1e-9,
                                   err_msg=col)


def test_lags_are_null_where_the_source_hour_does_not_exist(warehouse_db):
    """2024-03-10 02:00 does not exist: lag_24 on 03-11 02:00 and lag_168 on 03-17 02:00 are
    NULL, while 03:00 on the same days has values."""
    with connect(warehouse_db) as con:
        rows = con.execute("""
            select hour_ts, lag_24, lag_168 from features_demand
            where zone_id = 161 and hour_ts in (timestamp '2024-03-11 02:00',
                timestamp '2024-03-17 02:00', timestamp '2024-03-11 03:00',
                timestamp '2024-03-17 03:00') order by hour_ts""").df().set_index("hour_ts")
    assert pd.isna(rows.loc["2024-03-11 02:00", "lag_24"])
    assert pd.isna(rows.loc["2024-03-17 02:00", "lag_168"])
    assert rows.loc["2024-03-11 03:00", "lag_24"] >= 0
    assert rows.loc["2024-03-17 03:00", "lag_168"] >= 0
