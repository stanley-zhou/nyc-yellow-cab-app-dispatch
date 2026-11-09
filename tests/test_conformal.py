import numpy as np
import pandas as pd
import pytest

from taxi_shock.conformal import conformal, conformal_q


def test_conformal_q_finite_sample_index():
    s = np.arange(1, 11, dtype=float)          # n = 10, alpha 0.2 -> ceil(11 * 0.8) = 9th
    assert conformal_q(s, 0.2) == 9.0
    assert conformal_q(s, 0.01) == 10.0        # capped at n
    with pytest.raises(ValueError):
        conformal_q(np.array([]), 0.2)


def _fc(rng, n, width):
    y = rng.normal(10, 3, n)
    mid = y + rng.normal(0, 3, n)
    return pd.DataFrame({"model": "m", "window": "w", "zone_id": rng.integers(1, 3, n), "y": y,
                         "q10": mid - width, "q90": mid + width})


@pytest.mark.parametrize("width", [0.5, 8.0])   # too narrow / too wide raw intervals
def test_conformal_restores_nominal_coverage(width):
    rng = np.random.default_rng(0)
    val, test = _fc(rng, 4000, width), _fc(rng, 4000, width)
    groups = pd.Series({1: "a", 2: "b"})
    cal, rep = conformal(val, test, groups, 0.2, "q10", "q90")
    cov = ((cal["y"] >= cal["q10"]) & (cal["y"] <= cal["q90"])).mean()
    assert cov == pytest.approx(0.8, abs=0.03)
    assert {r["zone_group"] for r in rep} == {"a", "b"}
    assert (cal["q10"] >= 0).all()
    assert all((r["Q"] < 0) == (width == 8.0) for r in rep)   # wide intervals shrink


def test_rolling_conformal_uses_only_the_trailing_window_and_fixes_bias():
    from taxi_shock.conformal import rolling_conformal

    rng = np.random.default_rng(1)
    days = pd.date_range("2024-01-01", "2024-04-30", freq="D")
    rows = []
    for d in days:
        for z in (1, 2):
            ts = d + pd.to_timedelta(np.arange(24), unit="h")
            y = rng.normal(20, 4, 24)
            # forecasts biased low by 5 everywhere: raw q10/q50/q90 too low
            m = y - 5 + rng.normal(0, 4, 24)
            rows.append(pd.DataFrame({"zone_id": z, "target_ts": ts, "origin": d, "y": y,
                                      "q10": m - 5, "q50": m, "q90": m + 5}))
    fc = pd.concat(rows, ignore_index=True)
    groups = pd.Series({1: "a", 2: "a"})
    origins = pd.date_range("2024-03-01", "2024-04-30", freq="D")
    cal = rolling_conformal(fc, groups, [0.1, 0.5, 0.9], 4, origins)
    assert cal.attrs["n_origins_uncalibrated"] == 0
    assert ((cal["y"] >= cal["q10"]) & (cal["y"] <= cal["q90"])).mean() == \
        pytest.approx(0.8, abs=0.04)
    assert (cal["y"] <= cal["q50"]).mean() == pytest.approx(0.5, abs=0.04)
    # poisoning actuals on/after an origin day must not change that origin's calibration
    o = pd.Timestamp("2024-04-10")
    poisoned = fc.copy()
    poisoned.loc[poisoned["target_ts"] >= o, "y"] = 1e6
    a = rolling_conformal(fc, groups, [0.1, 0.5, 0.9], 4, pd.DatetimeIndex([o]))
    b = rolling_conformal(poisoned, groups, [0.1, 0.5, 0.9], 4, pd.DatetimeIndex([o]))
    np.testing.assert_allclose(a[["q10", "q50", "q90"]], b[["q10", "q50", "q90"]])
    # an origin without a full trailing window stays uncalibrated
    early = rolling_conformal(fc, groups, [0.1, 0.5, 0.9], 4,
                              pd.DatetimeIndex([pd.Timestamp("2024-01-10")]))
    assert early.attrs["n_origins_uncalibrated"] == 1 and early["q10"].isna().all()


def test_rolling_conformal_ignores_missing_forecasts_in_the_pool():
    """A NaN forecast inside the trailing window (seasonal naive after a DST spring-forward
    day) must not leave the origin uncalibrated; the NaN row itself stays NaN."""
    from taxi_shock.conformal import rolling_conformal

    rng = np.random.default_rng(2)
    days = pd.date_range("2024-01-01", "2024-03-31", freq="D")
    rows = []
    for d in days:
        ts = d + pd.to_timedelta(np.arange(24), unit="h")
        y = rng.normal(20, 4, 24)
        rows.append(pd.DataFrame({"zone_id": 1, "target_ts": ts, "origin": d, "y": y,
                                  "q10": y - 5, "q50": y, "q90": y + 5}))
    fc = pd.concat(rows, ignore_index=True)
    hole = fc["target_ts"] == pd.Timestamp("2024-03-10 02:00")
    fc.loc[hole, ["q10", "q50", "q90"]] = np.nan
    origins = pd.date_range("2024-03-11", "2024-03-31", freq="D")
    cal = rolling_conformal(fc, pd.Series({1: "a"}), [0.1, 0.5, 0.9], 4, origins)
    assert cal.attrs["n_origins_uncalibrated"] == 0
    assert len(cal) == 24 * len(origins)
    assert cal["q10"].notna().all()
