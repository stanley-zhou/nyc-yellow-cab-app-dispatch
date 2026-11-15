"""Split-conformal calibration of forecast intervals (PLAN Phase 2, mandatory).

Conformalized quantile regression (Romano, Patterson & Candes, 2019): on a calibration period,
score = max(q_lo - y, y - q_hi) (positive when y falls outside the interval); Q = the
ceil((n + 1)(1 - alpha))-th smallest score; the calibrated interval is [q_lo - Q, q_hi + Q],
with the lower end clipped at zero (counts). Q < 0 narrows an over-wide interval. Applied per
(model, window, zone group).

Pure computation on DataFrames and arrays; reads and writes no files.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def conformal_q(score: np.ndarray, alpha: float) -> float:
    """The finite-sample split-conformal quantile of the calibration scores."""
    n = len(score)
    if n == 0:
        raise ValueError("no calibration scores")
    k = min(math.ceil((n + 1) * (1 - alpha)), n)
    return float(np.sort(score)[k - 1])


def conformal(val: pd.DataFrame, test: pd.DataFrame, groups: pd.Series, alpha: float,
              lo: str, hi: str) -> tuple[pd.DataFrame, list[dict]]:
    """CQR per (model, window, zone_group); returns calibrated test forecasts and a report."""
    val = val.assign(zone_group=val["zone_id"].map(groups))
    test = test.assign(zone_group=test["zone_id"].map(groups))
    out, report = [], []
    for (m, w, g), t in test.groupby(["model", "window", "zone_group"]):
        v = val[(val["model"] == m) & (val["window"] == w) & (val["zone_group"] == g)]
        v = v[v["y"].notna() & v[lo].notna()]
        score = np.maximum(v[lo] - v["y"], v["y"] - v[hi]).to_numpy()
        n = len(score)
        q = conformal_q(score, alpha)
        c = t.copy()
        c[lo] = np.clip(t[lo] - q, 0.0, None)
        c[hi] = t[hi] + q
        out.append(c)
        # rows without a forecast are dropped, as in evaluate() and the rolling table
        tt = t[t["y"].notna() & t[lo].notna()]
        cc = c[c["y"].notna() & c[lo].notna()]
        report.append({
            "model": m, "window": w, "zone_group": g, "n_calibration": n, "Q": round(q, 4),
            "coverage_validation_raw": round(float(((v["y"] >= v[lo]) & (v["y"] <= v[hi]))
                                                   .mean()), 4),
            "coverage_test_raw": round(float(((tt["y"] >= tt[lo]) & (tt["y"] <= tt[hi]))
                                             .mean()), 4),
            "coverage_test_conformal": round(float(((cc["y"] >= cc[lo]) & (cc["y"] <= cc[hi]))
                                                   .mean()), 4),
            "width_test_raw": round(float((tt[hi] - tt[lo]).mean()), 4),
            "width_test_conformal": round(float((cc[hi] - cc[lo]).mean()), 4),
        })
    return pd.concat(out, ignore_index=True).drop(columns="zone_group"), report


def rolling_conformal(fc: pd.DataFrame, groups: pd.Series, quantiles: list[float],
                      weeks: int, origins: pd.DatetimeIndex) -> pd.DataFrame:
    """Rolling per-quantile calibration (Stanley, 2026-11-08; primary calibration).

    For each origin D in `origins`, zone group g and quantile level tau: the adjustment is the
    empirical tau-quantile of the residuals y - q_tau of the forecasts in `fc` whose target day
    lies in the trailing `weeks` weeks [D - 7*weeks days, D - 1] (all resolved at the 00:00
    origin, so no future information); q_tau' = q_tau + adjustment, then the quantiles are
    re-sorted per row and clipped at zero. The point forecast is unchanged. An origin whose
    trailing window is not fully covered by forecasts in `fc` gets no calibrated values (NaN)
    and is counted in `n_origins_uncalibrated` of the returned frame's attrs.

    `fc` holds one model/window's forecasts over the calibration history and the evaluation
    period (zone_id, target_ts, origin, y, q*); returns the rows with origin in `origins`.
    """
    qs = sorted(quantiles)
    cols = [f"q{round(q * 100):02d}" for q in qs]
    fc = fc[fc["y"].notna()].assign(zone_group=fc["zone_id"].map(groups),
                                    day=fc["target_ts"].dt.normalize())
    days_present = set(fc["day"].unique())
    span = pd.Timedelta(days=7 * weeks)
    # residual arrays per (zone group, day, quantile column), built once; rows without a
    # forecast (NaN quantiles, e.g. seasonal naive's missing lag hour a week after a DST
    # spring-forward day) are left out of the pool rather than turning every shift into NaN
    resid: dict[tuple[str, pd.Timestamp], np.ndarray] = {}
    for (g, day), d in fc[fc[cols].notna().all(axis=1)].groupby(["zone_group", "day"]):
        resid[(g, day)] = (d["y"].to_numpy()[:, None] - d[cols].to_numpy())
    out, skipped = [], 0
    by_origin = {o: d for o, d in fc[fc["origin"].isin(origins)].groupby("origin")}
    for origin in origins:
        target = by_origin.get(origin)
        if target is None:
            continue
        window = pd.date_range(origin - span, origin - pd.Timedelta(days=1), freq="D")
        if not set(window) <= days_present:
            skipped += 1
            out.append(target.assign(**{c: np.nan for c in cols}))
            continue
        parts = []
        for g, t in target.groupby("zone_group"):
            pool = [resid[(g, d)] for d in window if (g, d) in resid]
            if not pool:
                raise ValueError(f"zone group {g}: no residuals in the window before {origin}")
            pool = np.concatenate(pool)
            shift = np.array([np.quantile(pool[:, j], q) for j, q in enumerate(qs)])
            t = t.copy()
            t[cols] = t[cols].to_numpy() + shift
            parts.append(t)
        out.append(pd.concat(parts))
    res = pd.concat(out, ignore_index=True)
    ok = res[cols].notna().all(axis=1)
    res.loc[ok, cols] = np.clip(np.sort(res.loc[ok, cols].to_numpy(), axis=1), 0.0, None)
    res = res.drop(columns=["zone_group", "day"])
    res.attrs["n_origins_uncalibrated"] = skipped
    return res
