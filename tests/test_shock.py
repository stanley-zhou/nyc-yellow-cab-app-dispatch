"""taxi_shock.shock: daily sums per zone group and trailing-window error metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_shock.shock import daily_table, rolling_table


def _fc(days: int = 40) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=24 * days, freq="h")
    rows = []
    for z, base in ((1, 10.0), (2, 30.0)):
        y = np.full(len(ts), base)
        point = y * 1.25                                # over-forecast by 25 %
        rows.append(pd.DataFrame({"model": "m", "series": "s", "zone_id": z, "target_ts": ts,
                                  "y": y, "point": point, "in_sample": ts < "2025-01-10"}))
    return pd.concat(rows, ignore_index=True)


GROUPS = {"a": [1], "b": [2], "all": [1, 2]}


def test_daily_sums_and_group_membership():
    d = daily_table(_fc(), GROUPS)
    one = d[(d["zone_group"] == "all") & (d["day"] == pd.Timestamp("2025-01-12"))].iloc[0]
    assert one["actual"] == 24 * 40.0 and one["forecast"] == 24 * 50.0
    assert one["n_hours"] == 48 and one["signed_error"] == 24 * 10.0
    assert not one["in_sample"]
    assert d.loc[d["day"] == pd.Timestamp("2025-01-02"), "in_sample"].all()


def test_rolling_metrics_conventions_and_complete_windows():
    fc = _fc()
    fc.loc[fc["target_ts"] == pd.Timestamp("2025-01-05 03:00"), "point"] = np.nan  # dropped
    t = rolling_table(daily_table(fc, GROUPS), 28)
    r = t[(t["zone_group"] == "b") & (t["window_days"] == 28)]
    assert r["date"].min() == pd.Timestamp("2025-01-28")      # first complete 28-day window
    assert r["wape"].iloc[-1] == pytest.approx(0.25)
    assert r["bias"].iloc[-1] == pytest.approx(7.5)            # forecast - actual per hour
    assert r["log_actual_over_forecast"].iloc[-1] == pytest.approx(np.log(1 / 1.25))
    first = r.iloc[0]
    assert first["in_sample"] and not r["in_sample"].iloc[-1]  # window touching in-sample days
    daily = t[(t["window_days"] == 1) & (t["zone_group"] == "b")]
    assert daily["n_hours"].min() == 23                        # the NaN forecast hour is dropped
