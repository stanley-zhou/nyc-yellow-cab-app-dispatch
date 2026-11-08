"""Chronos-2 inputs use nothing at or after the origin except declared known-future covariates.

Chronos is zero-shot and runs only on Colab, so the leakage guarantee is checked where it is
decided: the input construction of scripts/05_chronos_colab.py (no torch / chronos needed).
Poisoning every target value and every past-only covariate at or after the origin must leave the
inputs bit-for-bit unchanged; poisoning the context must change them (power check).
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from taxi_shock.config import repo_root

spec = importlib.util.spec_from_file_location(
    "chronos_colab", repo_root() / "scripts" / "05_chronos_colab.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

MANIFEST = {"calendar_covariates": ["hour_sin", "is_holiday"],
            "weather_covariates": ["temp_f", "precip_in"],
            "variants": {"weather_past": "past", "weather_future": "future"}}
CONTEXT = 72


def _data():
    # local wall-clock grid with the 2024-03-10 02:00 hour missing (spring forward)
    hours = pd.date_range("2024-03-05", "2024-03-13 23:00", freq="h")
    hours = pd.DatetimeIndex(hours[~((hours.date == pd.Timestamp("2024-03-10").date())
                                     & (hours.hour == 2))])
    rng = np.random.default_rng(0)
    y = rng.poisson(20, size=(3, len(hours))).astype(np.float32)
    cov = pd.DataFrame({c: rng.normal(size=len(hours)).astype(np.float32)
                        for c in ["hour_sin", "is_holiday", "temp_f", "precip_in"]}, index=hours)
    return hours, y, cov


def _inputs(hours, y, cov, origin, variant):
    lo, hi = cc.day_positions(hours, pd.Timestamp(origin))
    past, future = cc.variant_covariates(MANIFEST, variant)
    return cc.make_inputs(y, cov, lo, hi - lo, CONTEXT, past, future), lo, hi


def _flat(inputs):
    parts = []
    for d in inputs:
        parts.append(d["target"])
        parts += [d["past_covariates"][k] for k in sorted(d["past_covariates"])]
        parts += [d.get("future_covariates", {})[k] for k in sorted(d.get("future_covariates",
                                                                            {}))]
    return np.concatenate(parts)


@pytest.mark.parametrize("variant", ["weather_past", "weather_future"])
@pytest.mark.parametrize("origin", ["2024-03-10", "2024-03-11", "2024-03-12"])
def test_future_poisoning_does_not_change_inputs(variant, origin):
    hours, y, cov = _data()
    clean, lo, _ = _inputs(hours, y, cov, origin, variant)
    past, future = cc.variant_covariates(MANIFEST, variant)
    y_p, cov_p = y.copy(), cov.copy()
    y_p[:, lo:] = 1e6                                         # every target at/after the origin
    cov_p.iloc[lo:, [cov.columns.get_loc(c) for c in past if c not in future]] = np.nan
    got, _, _ = _inputs(hours, y_p, cov_p, origin, variant)
    np.testing.assert_array_equal(_flat(clean), _flat(got))


def test_context_poisoning_changes_inputs():
    hours, y, cov = _data()
    clean, lo, _ = _inputs(hours, y, cov, "2024-03-11", "weather_past")
    y_p = y.copy()
    y_p[:, lo - 1] += 5
    got, _, _ = _inputs(hours, y_p, cov, "2024-03-11", "weather_past")
    assert not np.array_equal(_flat(clean), _flat(got))


def test_context_ends_right_before_origin_and_targets_follow_the_local_day():
    hours, y, cov = _data()
    for origin, n_expected in (("2024-03-10", 23), ("2024-03-11", 24)):
        inputs, lo, hi = _inputs(hours, y, cov, origin, "weather_future")
        assert hi - lo == n_expected
        assert hours[lo] == pd.Timestamp(origin)
        assert len(inputs) == y.shape[0]
        np.testing.assert_array_equal(inputs[1]["target"], y[1, lo - CONTEXT:lo])
        assert len(inputs[0]["future_covariates"]["temp_f"]) == n_expected


def test_weather_is_future_known_only_in_the_future_variant():
    past, future = cc.variant_covariates(MANIFEST, "weather_past")
    assert set(future) == {"hour_sin", "is_holiday"} and {"temp_f", "precip_in"} <= set(past)
    past, future = cc.variant_covariates(MANIFEST, "weather_future")
    assert set(future) == set(past)


def test_insufficient_history_fails():
    hours, y, cov = _data()
    lo, hi = cc.day_positions(hours, pd.Timestamp("2024-03-06"))
    with pytest.raises(ValueError, match="not enough history"):
        cc.make_inputs(y, cov, lo, hi - lo, CONTEXT, ["temp_f"], [])
