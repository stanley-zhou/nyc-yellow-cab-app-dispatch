"""Phase 6 / Amendment 4 code (review round 1, fix 8): HVFHV aggregation, the C6 gate, the D2
DML estimator and its time-blocked folds."""

from __future__ import annotations

import copy
import importlib.util

import duckdb
import numpy as np
import pandas as pd
import pytest

from taxi_shock.config import load_config, repo_root


def load_script(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, repo_root() / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hvfhv_aggregate_trip_types_bins_and_accounting(tmp_path):
    cfg = load_config()
    hv = load_script("hv11", "11_hvfhv_stream.py")
    cbd = pd.read_csv(repo_root() / cfg["paths"]["zones_cbd"])
    c = int(cbd.loc[cbd["is_cbd"], "zone_id"].iloc[0])
    n = int(cbd.loc[~cbd["is_cbd"] & (cbd["borough"] == "Brooklyn"), "zone_id"].iloc[0])
    ts = pd.Timestamp("2023-01-10 08:15")
    raw = pd.DataFrame({
        "PULocationID": [c, n, c, n, 264, n, n],
        "DOLocationID": [c, c, n, n, n, 265, n],
        "hvfhs_license_num": ["HV0003"] * 4 + ["HV0005"] * 3,
        "shared_request_flag": ["N", "Y", "N", "N", "N", "N", "N"],
        "shared_match_flag": ["N", "Y", "N", "N", "N", "N", "N"],
        "pickup_datetime": [ts] * 7,
        "trip_miles": [0.5, 1.29, 25.0, None, 3.0, 2.0, 1.0],
        "trip_time": [600] * 7, "base_passenger_fare": [10.0] * 7, "driver_pay": [8.0] * 7})
    f = tmp_path / "fhvhv_tripdata_2023-01.parquet"
    raw.to_parquet(f)
    out = tmp_path / "agg"
    out.mkdir()
    acc = hv.aggregate(duckdb.connect(), f, "2023-01", cfg, out)
    assert acc["rows_file"] == 7 and acc["rows_invalid_pu_zone"] == 1 and acc["rows_kept"] == 6
    assert acc["verified"] and not acc["has_cbd_congestion_fee"]
    z = pd.read_parquet(out / "zone_hour_2023-01.parquet")
    tt = z.groupby("trip_type")["trips"].sum().to_dict()
    assert tt == {"within": 1, "into": 1, "out_of": 1, "neither": 3}   # unknown dropoff = outside
    edges = cfg["hvfhv"]["distance_edges"]
    bins = z.groupby("trip_type")["dist_bin"].apply(sorted).to_dict()
    assert bins["within"] == [0]                                # 0.5 mi < first edge
    assert bins["into"] == [edges.index(1.29) + 1]              # an edge belongs to the next bin
    assert bins["out_of"] == [len(edges)]                       # beyond the last edge
    assert bins["neither"] == [-1, edges.index(1.29), edges.index(2) + 1]   # NULL, 1.0, 2.0
    assert z["trips_cbd_fee"].sum() == 0
    pw = pd.read_parquet(out / "pair_week_2023-01.parquet")
    assert pw["trips"].sum() == 6 and set(pw["week_start"].astype(str)) == {"2023-01-08"}


def _panel(pretrend: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2023-01-01", "2026-09-20", freq="7D")
    ev = ((weeks - pd.Timestamp("2025-01-05")).days // 7).to_numpy()
    rows = []
    for z in range(40):
        tr = int(z < 20)
        y = (rng.normal(6, 0.5) + 0.002 * ev + tr * pretrend * np.minimum(ev, 0) / 52
             + rng.normal(0, 0.03, len(weeks)))
        rows.append(pd.DataFrame({"zone_id": z, "week_start": weeks, "event_week": ev,
                                  "treated": tr, "fhv_x": np.expm1(y),
                                  "tr_mean_temp_f": tr * rng.normal(50, 10, len(weeks)),
                                  "tr_total_precip_in": tr * rng.gamma(1, 0.3, len(weeks))}))
    d = pd.concat(rows, ignore_index=True)
    d["log1p_fhv_x"] = np.log1p(d["fhv_x"])
    return d


def test_c6_gate_withholds_the_estimate_when_pretrends_reject():
    cfg = load_config()
    c6 = load_script("c6", "16_fhv_did.py")
    p4 = c6.phase4()
    bad, _ = c6.analyse(_panel(pretrend=0.3, seed=1), "fhv_x", None, cfg, p4)
    good, _ = c6.analyse(_panel(pretrend=0.0, seed=3), "fhv_x", None, cfg, p4)
    assert not bad["passes"] and "estimate" not in bad
    assert good["passes"] and "estimate" in good
    assert abs(good["estimate"]["terms"]["treated_post"]["coef"]) < 0.02


def test_dml_recovers_beta_and_clusters_widen_the_se():
    cfg = copy.deepcopy(load_config())
    cfg["incr"]["lgbm"] = {**cfg["incr"]["lgbm"], "n_estimators": 60}
    d2 = load_script("d2", "12_incrementality.py")
    rng = np.random.default_rng(0)
    weeks = pd.date_range("2023-01-01", periods=120, freq="7D")
    rows = []
    for z in range(30):
        u = np.zeros(len(weeks))
        v = np.zeros(len(weeks))
        for t in range(1, len(weeks)):                       # persistent within-zone shocks
            u[t] = 0.9 * u[t - 1] + rng.normal(0, 1)
            v[t] = 0.9 * v[t - 1] + rng.normal(0, 1)
        x1 = rng.normal(0, 1, len(weeks))
        app = 50 + 5 * np.sin(np.arange(len(weeks)) / 8) + 3 * x1 + 4 * v
        street = 200 - 0.4 * app + 2 * x1 ** 2 + 5 * u
        rows.append(pd.DataFrame({"zone_id": z, "week_start": weeks, "app": app,
                                  "street": street, "x1": x1}))
    p = pd.concat(rows, ignore_index=True)
    r = d2.dml_plr(d2.two_way(p, ["street", "app"]), ["x1"], cfg)
    assert r["beta_street_on_app"] == pytest.approx(-0.4, abs=0.1)
    assert r["se"] > r["se_doubleml_default"]
    assert r["theta"] == pytest.approx(1 + r["beta_street_on_app"])


def test_time_blocks_are_contiguous_disjoint_and_exhaustive():
    d2 = load_script("d2b", "12_incrementality.py")
    weeks = pd.Series(np.repeat(pd.date_range("2023-01-01", periods=23, freq="7D"), 3))
    blocks = d2.time_blocks(weeks, 5)
    tests = [te for _, te in blocks]
    assert sorted(np.concatenate(tests)) == list(range(len(weeks)))         # exhaustive, disjoint
    for tr, te in blocks:
        assert not set(tr) & set(te) and len(tr) + len(te) == len(weeks)
        u = np.sort(weeks.iloc[te].unique())
        all_u = np.sort(weeks.unique())
        i = int(np.searchsorted(all_u, u[0]))
        assert (all_u[i:i + len(u)] == u).all()                             # contiguous weeks


def test_channel_features_use_only_previous_days():
    """Phase 5 S6: the app-share features of day D come from days D-k..D-1; changing day D and
    later leaves them unchanged (the leakage rule of every demand feature)."""
    from taxi_shock.adapt import CHANNEL_FEATURES, channel_feature_fn, channel_table

    days = pd.date_range("2025-01-01", periods=60, freq="D")
    rng = np.random.default_rng(1)
    d = pd.DataFrame([{"zone_id": z, "day": t, "total": 100.0,
                       "app": float(rng.integers(0, 100))} for z in (1, 2) for t in days])
    rows = pd.DataFrame({"zone_id": [1, 1, 2], "target_ts": [days[40] + pd.Timedelta(hours=8),
                                                              days[40] + pd.Timedelta(hours=20),
                                                              days[45]]})
    base = channel_feature_fn(channel_table(d))(rows)
    poisoned = d.copy()
    poisoned.loc[poisoned["day"] >= days[40], "app"] = 1e6
    after = channel_feature_fn(channel_table(poisoned))(rows)
    pd.testing.assert_frame_equal(base.iloc[:2], after.iloc[:2])
    exp = d[(d["zone_id"] == 1) & d["day"].between(days[33], days[39])]
    assert base.loc[0, "app_share_7d"] == pytest.approx(exp["app"].sum() / exp["total"].sum())
    assert list(base.columns) == CHANNEL_FEATURES
    early = channel_feature_fn(channel_table(d))(pd.DataFrame({"zone_id": [1],
                                                               "target_ts": [days[3]]}))
    assert early.isna().all(axis=None)                     # window not yet covered
