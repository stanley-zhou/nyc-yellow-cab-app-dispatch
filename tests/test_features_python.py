"""The Python feature builder (used by the models) equals dbt `features_demand` (full warehouse),
for a busy CBD zone and a sparse zone across both 2024 DST weeks."""

import numpy as np
import pandas as pd
import pytest

from taxi_shock.features import WEATHER_FEATURES, build_features
from taxi_shock.io import connect, read_exog, read_hourly_demand

pytestmark = pytest.mark.warehouse
ZONES = [161, 3]
COLS = ["lag_24", "lag_48", "lag_168", "lag_336", "mean_same_hour_prev_7d",
        "mean_same_hour_prev_28d", "mean_prev_day", "dow", "dom", "month", "is_weekend",
        "is_holiday", *WEATHER_FEATURES]


@pytest.mark.parametrize("lo, hi", [("2024-03-06", "2024-03-20"), ("2024-10-29", "2024-11-12")])
def test_python_features_equal_dbt(warehouse_db, lo, hi):
    # history starts well before the window, so rolling windows are complete in both sources
    hist = read_hourly_demand(warehouse_db, "2023-12-01", hi)
    hist = hist[hist["zone_id"].isin(ZONES)]
    rows = hist[hist["hour_ts"] >= lo][["zone_id", "hour_ts"]].rename(
        columns={"hour_ts": "target_ts"}).reset_index(drop=True)
    got = build_features(hist, rows, read_exog(warehouse_db, "2023-12-01", hi))
    with connect(warehouse_db) as con:
        want = con.execute(f"""
            select zone_id, hour_ts as target_ts, {", ".join(COLS)} from features_demand
            where zone_id in (?, ?) and hour_ts >= ? and hour_ts < ?""",
            [*ZONES, lo, hi]).df()
    m = got.merge(want, on=["zone_id", "target_ts"], suffixes=("", "_dbt"))
    assert len(m) == len(want) == len(rows) > 0
    assert (m["horizon"] == m["target_ts"].dt.hour + 1).all()
    for c in COLS:
        a, b = m[c].astype(float), m[f"{c}_dbt"].astype(float)
        assert (a.isna() == b.isna()).all(), c
        np.testing.assert_allclose(a[a.notna()], b[b.notna()], rtol=1e-9, err_msg=c)


def test_prediction_rows_after_history_end(warehouse_db):
    """Targets on the day after the history ends get lag_24 = the last history day."""
    hist = read_hourly_demand(warehouse_db, "2024-05-01", "2024-06-01")
    hist = hist[hist["zone_id"] == 161]
    rows = pd.DataFrame({"zone_id": 161, "target_ts": pd.date_range("2024-06-01", periods=24,
                                                                   freq="h")})
    got = build_features(hist, rows, read_exog(warehouse_db, "2024-05-01", "2024-06-02"))
    last = hist[hist["hour_ts"] >= "2024-05-31"]["pickups"].to_numpy()
    np.testing.assert_allclose(got["lag_24"].to_numpy(), last)
    assert (got["mean_prev_day"] == got["mean_prev_day"].iloc[0]).all()
    assert got["mean_prev_day"].iloc[0] == pytest.approx(last.mean())
