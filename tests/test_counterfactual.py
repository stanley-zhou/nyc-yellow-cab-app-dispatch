"""taxi_shock.causal.counterfactual: monthly implied effect from daily sums."""

from __future__ import annotations

import pandas as pd
import pytest

from taxi_shock.causal.counterfactual import implied_effect_by_month


def test_implied_effect_by_month():
    ts = pd.date_range("2024-12-30", "2025-01-03 23:00", freq="h")
    fc = pd.DataFrame({"target_ts": ts, "y": 11.0, "point": 10.0})
    fc.loc[fc["target_ts"].dt.day == 2, "y"] = 8.0          # one day at -20%
    m = implied_effect_by_month(fc, "2024-12-31").set_index("month")
    assert m.loc["2024-12", "mean_daily_rel"] == pytest.approx(0.1)
    assert m.loc["2025-01", "mean_daily_rel"] == pytest.approx((0.1 - 0.2 + 0.1) / 3)
    assert m.loc["2024-12", "in_sample"] and not m.loc["2025-01", "in_sample"]
    assert m.loc["2025-01", "n_days"] == 3
