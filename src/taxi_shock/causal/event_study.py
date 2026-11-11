"""Event-study specification and pre-trend joint test (Phase 4).

y_it = a_i + l_t + sum_k b_k * 1[bin(t) = k] * treated_i (+ controls). Bins: calendar months of
the week start relative to the policy month (monthly; the figure) or event weeks (weekly; the
appendix). The week before the policy (event_week -1) alone is the omitted reference, so in the
monthly version the bin of that month holds its other weeks. Pre-trend test: joint Wald test that
every pre-period coefficient is 0, with the cluster-robust covariance: the pre-registered
F = W / q on (q, G - 1) df, where G is the smallest number of clusters (and the chi-square
version), and the Hotelling-type small-sample version F* = W (G - q) / (q (G - 1)) on (q, G - q)
df. With q = 24 monthly pre bins and G ~ 60 clusters the first is badly oversized; its size and
the corrected test's are simulated in scripts/07d_pretrend_size.py
(results/pretrend_test_size.json).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy import stats

from taxi_shock.causal.did import Z95, fit


def bins(df: pd.DataFrame, policy_date: str, unit: str = "month") -> pd.Series:
    """Event-time bin per row; None marks the reference week (event_week == -1)."""
    if unit == "week":
        k = df["event_week"].astype(int)
    elif unit == "month":
        p = pd.Timestamp(policy_date)
        ws = df["week_start"]
        k = (ws.dt.year - p.year) * 12 + (ws.dt.month - p.month)
    else:
        raise ValueError(unit)
    return k.astype("Int64").mask(df["event_week"] == -1)


def term(k: int) -> str:
    return f"ev_{'m' if k < 0 else 'p'}{abs(k):02d}"


def event_study(df: pd.DataFrame, y: str, unit_col: str, cluster: Sequence[str],
                policy_date: str, unit: str = "month", weights: str | None = None,
                controls: Sequence[str] = ()) -> tuple[pd.DataFrame, dict]:
    keep = list(dict.fromkeys([unit_col, "week_start", "event_week", "treated", y, *controls,
                               *cluster, *([weights] if weights else [])]))
    d = df[keep].copy()            # only what the fit needs: the dummies are wide
    b = bins(d, policy_date, unit)
    ks = sorted(int(k) for k in b.dropna().unique())
    terms = [term(k) for k in ks]
    tr = (d["treated"] == 1).to_numpy()
    bv = b.to_numpy(dtype="float64", na_value=np.nan)
    d = pd.concat([d, pd.DataFrame({t: ((bv == k) & tr).astype(float)
                                    for k, t in zip(ks, terms, strict=True)}, index=d.index)],
                  axis=1)
    m, fml = fit(d, y, [*terms, *controls], [unit_col, "week_start"], cluster, weights)
    coef, se, pv = m.coef(), m.se(), m.pvalue()
    rows = []
    for k, t in zip(ks, terms, strict=True):
        n = int(((b == k).fillna(False) & (d["treated"] == 1)).sum())
        rows.append({"k": k, "term": t, "coef": float(coef[t]), "se": float(se[t]),
                     "ci_lo": float(coef[t] - Z95 * se[t]),
                     "ci_hi": float(coef[t] + Z95 * se[t]),
                     "pvalue": float(pv[t]), "n_treated_obs": n})
    table = pd.DataFrame(rows)
    pre = [t for k, t in zip(ks, terms, strict=True) if k < 0]
    test = wald(m, pre, min(d[c].nunique() for c in cluster))
    info = {"formula": fml, "n_obs": int(m._N), "reference": "event_week -1 (the week before "
            "the policy)", "bins": unit, "pretrend": test}
    return table, info


def wald(model, names: Sequence[str], n_clusters: int) -> dict[str, float]:
    """Joint test that the coefficients `names` are all 0 (cluster-robust covariance)."""
    cn = list(model._coefnames)
    idx = [cn.index(n) for n in names]
    if len(idx) >= n_clusters:
        # a cluster-robust covariance has rank <= G - 1: more restrictions are not testable
        return {"n_restrictions": len(idx), "n_clusters": n_clusters,
                "note": "not computed: restrictions >= clusters (cluster-robust covariance "
                        "is singular); the monthly-bin test is the pre-trend test"}
    b = np.asarray(model.coef())[idx]
    v = np.asarray(model._vcov)[np.ix_(idx, idx)]
    w = float(b @ np.linalg.solve(v, b))
    q = len(idx)
    f = w / q
    g = n_clusters
    f_h = w * (g - q) / (q * (g - 1))   # Hotelling-type small-sample correction
    return {"n_restrictions": q, "wald_chi2": w, "p_chi2": float(stats.chi2.sf(w, q)),
            "F": f, "df": [q, g - 1], "p_F": float(stats.f.sf(f, q, g - 1)),
            "F_hotelling": f_h, "df_hotelling": [q, g - q],
            "p_F_hotelling": float(stats.f.sf(f_h, q, g - q))}
