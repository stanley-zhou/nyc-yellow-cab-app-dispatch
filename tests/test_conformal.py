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
