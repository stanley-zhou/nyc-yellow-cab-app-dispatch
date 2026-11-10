"""taxi_shock.chronos_runs: run specs, validation of returned files, merge into result files."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_shock.chronos_runs import MAIN, merge_run, run_spec, validate_run, with_run
from taxi_shock.config import load_config


def _rows(origins: pd.DatetimeIndex, zones=(1, 2), variants=("a", "b")) -> pd.DataFrame:
    parts = []
    for v in variants:
        for o in origins:
            ts = pd.date_range(o, periods=24, freq="h")
            for z in zones:
                parts.append(pd.DataFrame({"variant": v, "zone_id": np.int16(z), "origin": o,
                                           "target_ts": ts, "horizon": ts.hour + 1,
                                           "q10": 1.0, "q50": 2.0, "q90": 3.0}))
    return pd.concat(parts, ignore_index=True)


def test_run_specs_from_config():
    cfg = load_config()
    main, cal = run_spec(cfg, MAIN), run_spec(cfg, cfg["chronos"]["calibration_run"]["name"])
    assert main.inbox is None and cal.inbox is not None
    assert cal.test_period == cal.origins                 # all its rows go to the test file
    assert pd.Timestamp(cal.origins[1]) < pd.Timestamp(main.origins[0])
    assert main.run_record != cal.run_record
    with pytest.raises(ValueError):
        run_spec(cfg, "nope")


def test_merge_run_is_idempotent_and_leaves_main_untouched():
    main = _rows(pd.date_range("2024-01-01", periods=3))
    cal = _rows(pd.date_range("2023-12-29", periods=3))
    once = merge_run(main, cal, "calib")
    twice = merge_run(once, cal, "calib")
    pd.testing.assert_frame_equal(once, twice)
    assert once["run"].value_counts().to_dict() == {MAIN: len(main), "calib": len(cal)}
    back = once[once["run"] == MAIN].drop(columns="run").reset_index(drop=True)
    pd.testing.assert_frame_equal(back, main.sort_values(["variant", "origin", "zone_id",
                                                          "target_ts"]).reset_index(drop=True))
    # a replacement run replaces, it does not append
    cal2 = cal.assign(q50=9.0)
    assert (merge_run(once, cal2, "calib").query("run == 'calib'")["q50"] == 9.0).all()
    # overlap with another run's forecasts is refused
    with pytest.raises(ValueError):
        merge_run(main, main.iloc[:5], "calib")
    assert (with_run(main)["run"] == MAIN).all()


def test_validate_run_counts_and_flags():
    origins = pd.date_range("2023-10-01", periods=3)
    hours = pd.date_range("2023-10-01", periods=72, freq="h")
    manifest = {"origins": ["2023-10-01", "2023-10-03"], "test_period": ["2023-10-01",
                                                                         "2023-10-03"],
                "variants": {"a": "past", "b": "future"}, "quantiles": [0.1, 0.5, 0.9],
                "files": {"x": {"sha256": "s"}}, "colab_script_sha256": "c"}
    run = {"dry_run": False, "input_files": {"x": {"sha256": "s"}}, "script_sha256": "c"}
    test = _rows(origins)
    post = test.iloc[:0]
    ok, checks = validate_run(manifest, run, test, post, hours, [1, 2])
    assert ok and checks["test_rows"] == checks["test_expected_rows"] == 2 * 3 * 24 * 2
    ok, checks = validate_run(manifest, run, test.iloc[1:], post, hours, [1, 2])
    assert not ok and checks["test_missing"] == 1
    ok, _ = validate_run(manifest, {**run, "dry_run": True}, test, post, hours, [1, 2])
    assert not ok
    ok, _ = validate_run(manifest, {**run, "script_sha256": "other"}, test, post, hours, [1, 2])
    assert not ok
