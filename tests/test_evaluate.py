"""taxi_shock.evaluation: quantile post-processing, daily WAPE inputs, WAPE-gap bootstrap."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_shock.evaluation import (
    daily_errors,
    sort_clip_quantiles,
    tied_with_best,
    wape_gap_bootstrap,
)


def test_sort_clip_quantiles_removes_crossings_and_negatives():
    fc = pd.DataFrame({"q10": [5.0, -2.0, 1.0], "q50": [3.0, 1.0, 1.0],
                       "q90": [4.0, 0.5, 2.0], "point": [9.0, 9.0, 9.0]})
    out = sort_clip_quantiles(fc, ["q10", "q50", "q90"])
    np.testing.assert_array_equal(out[["q10", "q50", "q90"]].to_numpy(),
                                  [[3.0, 4.0, 5.0], [0.0, 0.5, 1.0], [1.0, 1.0, 2.0]])
    np.testing.assert_array_equal(out["point"], out["q50"])   # point = sorted median
    assert fc["q10"].iloc[1] == -2.0                           # input left untouched


def _forecasts(rng: np.random.Generator, noise: float, bias: float = 0.0) -> pd.DataFrame:
    origins = pd.date_range("2024-01-01", periods=70, freq="D")
    rows = []
    for o in origins:
        for z in (1, 2, 3):
            y = rng.poisson(20 * z, 24).astype(float)
            rows.append(pd.DataFrame({"origin": o, "zone_id": z, "y": y,
                                      "point": y + bias + rng.normal(0, noise, 24)}))
    return pd.concat(rows, ignore_index=True)


GROUPS = pd.Series({1: "a", 2: "a", 3: "b"})


def test_daily_errors_reproduce_wape():
    fc = _forecasts(np.random.default_rng(0), 3.0)
    fc.loc[5, "point"] = np.nan                     # a missing forecast is left out
    d = daily_errors(fc, GROUPS)
    ok = fc[fc["point"].notna()]
    wape = (ok["y"] - ok["point"]).abs().sum() / ok["y"].sum()
    allz = d[d["zone_group"] == "all"]
    assert allz["abs_err"].sum() / allz["y"].sum() == pytest.approx(wape)
    a = d[d["zone_group"] == "a"]
    ok_a = ok[ok["zone_id"].isin([1, 2])]
    assert a["y"].sum() == pytest.approx(ok_a["y"].sum())
    assert set(d["zone_group"]) == {"a", "b", "all"}


def _daily(models: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.concat([daily_errors(fc, GROUPS).assign(model=m) for m, fc in models.items()],
                     ignore_index=True)


def test_bootstrap_ties_identical_models_and_separates_a_worse_one():
    rng = np.random.default_rng(1)
    good = _forecasts(rng, 3.0)
    worse = good.assign(point=good["point"] + 6.0)        # uniformly worse on every hour
    daily = _daily({"good": good, "twin": good.copy(), "worse": worse})
    gaps = wape_gap_bootstrap(daily, reps=500, block_days=7, seed=0)
    pair = gaps.set_index(["zone_group", "model", "reference"])
    assert not pair.loc[("all", "twin", "good"), "distinguishable"]
    assert pair.loc[("all", "twin", "good"), "gap"] == 0.0
    assert pair.loc[("all", "worse", "good"), "distinguishable"]
    assert pair.loc[("all", "worse", "good"), "gap_ci_lo"] > 0
    # gaps are antisymmetric and the point WAPE equals sum |e| / sum y
    assert pair.loc[("all", "good", "worse"), "gap"] == \
        pytest.approx(-pair.loc[("all", "worse", "good"), "gap"])
    w = (good["y"] - good["point"]).abs().sum() / good["y"].sum()
    assert pair.loc[("all", "good", "worse"), "wape"] == pytest.approx(w, abs=1e-6)
    best, tied = tied_with_best(gaps, "all")
    assert best in {"good", "twin"} and tied == [{"good", "twin"}.difference({best}).pop()]


def test_bootstrap_is_reproducible():
    rng = np.random.default_rng(2)
    a, b = _forecasts(rng, 3.0), _forecasts(rng, 4.0)
    daily = _daily({"a": a, "b": b})
    pd.testing.assert_frame_equal(wape_gap_bootstrap(daily, 200, 7, 5),
                                  wape_gap_bootstrap(daily, 200, 7, 5))
