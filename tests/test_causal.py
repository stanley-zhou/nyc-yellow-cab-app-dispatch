"""taxi_shock.causal: static DiD, event study + pre-trend test, placebo helpers, pair categories.

A synthetic zone-week panel with a known treatment effect and parallel trends: the estimators
must recover the effect, the pre-trend test must not reject, and a planted differential pre-trend
must be detected.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_shock.causal.did import SEASONAL, add_seasonal, static_did
from taxi_shock.causal.event_study import bins, event_study
from taxi_shock.causal.panel import pair_category
from taxi_shock.causal.placebo import (
    leave_one_out,
    permutation,
    power_summary,
    quick_beta,
    with_fake_policy,
)

POLICY = "2025-01-05"


def panel(beta: float = -0.1, trend: float = 0.0, n_zones: int = 40, seed: int = 0
          ) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2023-01-01", "2026-09-20", freq="7D")
    ev = ((weeks - pd.Timestamp(POLICY)).days // 7).to_numpy()
    rows = []
    for z in range(n_zones):
        tr = int(z < n_zones // 2)
        y = (rng.normal(5, 1) + 0.002 * ev + 0.1 * np.sin(ev / 8)        # zone + common time
             + tr * beta * (ev >= 0) + tr * trend * np.minimum(ev, 0) / 52
             + rng.normal(0, 0.05, len(weeks)))
        rows.append(pd.DataFrame({"zone_id": z, "week_start": weeks, "event_week": ev,
                                  "treated": tr, "y": y}))
    return pd.concat(rows, ignore_index=True)


def test_static_did_recovers_the_effect_and_splits():
    d = panel(beta=-0.1)
    r = static_did(d, "y", "zone_id", ["zone_id"], 52)
    t = r.row("treated_post")
    assert t["coef"] == pytest.approx(-0.1, abs=0.01)
    assert t["ci_lo"] < -0.1 < t["ci_hi"]
    assert r.n_treated_units == 20 and r.n_clusters == {"zone_id": 40}
    splits = {"a": ("2025-01-05", "2025-12-27"), "b": ("2025-12-28", "2026-09-30")}
    s = static_did(d, "y", "zone_id", ["zone_id"], 52, post_splits=splits)
    assert s.coef["a"] == pytest.approx(-0.1, abs=0.015)
    assert s.coef["b"] == pytest.approx(-0.1, abs=0.015)
    with pytest.raises(ValueError):          # a split set that leaves post weeks uncovered
        static_did(d, "y", "zone_id", ["zone_id"], 52,
                   post_splits={"a": ("2025-01-05", "2025-03-01")})


def test_event_study_flat_pre_period_and_detects_a_planted_pretrend():
    t, info = event_study(panel(beta=-0.1), "y", "zone_id", ["zone_id"], POLICY, "month")
    assert t.loc[t["k"] >= 0, "coef"].mean() == pytest.approx(-0.1, abs=0.02)
    # the size-corrected test does not reject parallel trends (the uncorrected F is oversized
    # with 24 restrictions and 40 clusters: results/pretrend_test_size.json)
    assert info["pretrend"]["p_F_hotelling"] > 0.01
    assert info["pretrend"]["p_F"] <= info["pretrend"]["p_F_hotelling"]
    _, bad = event_study(panel(beta=-0.1, trend=0.3), "y", "zone_id", ["zone_id"], POLICY,
                         "month")
    assert bad["pretrend"]["p_F_hotelling"] < 0.001


def test_bins_reference_week_and_months():
    d = pd.DataFrame({"week_start": pd.to_datetime(["2024-12-22", "2024-12-29",
                                                    "2025-01-05", "2023-01-01"]),
                      "event_week": [-2, -1, 0, -105]})
    b = bins(d, POLICY, "month")
    assert b.tolist()[0] == -1 and pd.isna(b.tolist()[1])   # reference week omitted
    assert b.tolist()[2] == 0 and b.tolist()[3] == -24
    assert bins(d, POLICY, "week").tolist()[0] == -2


def test_seasonal_terms_and_fake_policy():
    d = add_seasonal(panel(n_zones=4))
    assert all(c in d for c in SEASONAL)
    jan = d["week_start"].dt.month == 1
    assert (d.loc[jan, SEASONAL].sum(axis=1) == 0).all()      # January is the base month
    f = with_fake_policy(d, pd.Timestamp("2024-01-07"))
    assert (f.loc[f["week_start"] == pd.Timestamp("2024-01-07"), "event_week"] == 0).all()


def test_placebo_helpers():
    d = panel(beta=0.0, n_zones=20, seed=3)
    pre = d[d["event_week"] < 0].drop(columns="treated")
    weeks = sorted(pre["week_start"].unique())

    def assign(df, fake):
        return df.assign(treated=df["zone_id"].isin(fake).astype(int))

    draws = permutation(pre, list(range(20)), 10, 30, weeks[26:-26], assign,
                        lambda x: quick_beta(x, "y", "zone_id"), seed=1)
    assert len(draws) == 30 and draws["coef"].abs().max() < 0.1
    s = power_summary(draws["coef"], 0.5, 0.05, 0.8)
    assert s["mde_multiplier"] == pytest.approx(1.959964 + 0.841621, abs=1e-4)
    assert s["mde"] == pytest.approx(s["mde_multiplier"] * draws["coef"].std(ddof=1))
    assert s["share_abs_ge_abs_beta"] == 0.0
    loo = leave_one_out(d, [0, 1, 39], lambda x: quick_beta(x, "y", "zone_id"), ["zone_id"])
    assert list(loo["dropped_zone"]) == [0, 1, 39]


def test_pair_categories():
    pu_cbd = pd.Series([True, False, True, False, False])
    do_cbd = pd.Series([True, True, False, False, False])
    pu_ctl = pd.Series([False, True, False, True, False])
    do_ctl = pd.Series([False, False, True, True, True])
    assert pair_category(pu_cbd, do_cbd, pu_ctl, do_ctl).tolist() == [
        "within_cbd", "entering", "leaving", "within_control", "other"]
