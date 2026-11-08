"""Split-conformal calibration of forecast intervals (PLAN Phase 2, mandatory).

Conformalized quantile regression (Romano, Patterson & Candes, 2019): on a calibration period,
score = max(q_lo - y, y - q_hi) (positive when y falls outside the interval); Q = the
ceil((n + 1)(1 - alpha))-th smallest score; the calibrated interval is [q_lo - Q, q_hi + Q],
with the lower end clipped at zero (counts). Q < 0 narrows an over-wide interval. Applied per
(model, window, zone group).
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
        tt = t[t["y"].notna()]
        cc = c[c["y"].notna()]
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
