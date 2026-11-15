"""Static difference-in-differences with pyfixest (Phase 4).

`static_did` estimates y_it = a_i + l_t + b * treated_i * post_t (+ controls) on the static
window (PLAN: 52 weeks before the policy and every post week), with unit and week fixed effects
and cluster-robust SEs. `post_splits` replaces the single post dummy by one dummy per named post
sub-period (persistence: 2025-H1, 2025-H2, 2026). Weather enters as weather x treated, because
city-wide weekly weather is collinear with the week fixed effects (DECISIONS.md, Phase 4).

Pure computation on DataFrames and arrays; reads and writes no files.
"""

from __future__ import annotations

import gc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pyfixest as pf

Z95 = 1.959963984540054


@dataclass
class DidResult:
    coef: dict[str, float]
    se: dict[str, float]
    pvalue: dict[str, float]
    n_obs: int
    n_units: int
    n_treated_units: int
    n_clusters: dict[str, int]
    formula: str
    vcov: str
    weights: str | None
    extra: dict[str, object] = field(default_factory=dict)
    log_outcome: bool = True          # % effects (exp(b) - 1) only make sense for log outcomes

    def row(self, name: str) -> dict[str, float | None]:
        b, s = self.coef[name], self.se[name]
        pct = (lambda v: float(np.expm1(v))) if self.log_outcome else (lambda v: None)
        return {"coef": b, "se": s, "ci_lo": b - Z95 * s, "ci_hi": b + Z95 * s,
                "pvalue": self.pvalue[name], "pct": pct(b), "pct_ci_lo": pct(b - Z95 * s),
                "pct_ci_hi": pct(b + Z95 * s)}

    def to_dict(self) -> dict[str, object]:
        return {"terms": {k: self.row(k) for k in self.coef}, "n_obs": self.n_obs,
                "n_units": self.n_units, "n_treated_units": self.n_treated_units,
                "n_clusters": self.n_clusters, "formula": self.formula, "vcov": self.vcov,
                "weights": self.weights, **self.extra}


SEASONAL = [f"tr_month_{m:02d}" for m in range(2, 13)]


def add_seasonal(d: pd.DataFrame) -> pd.DataFrame:
    """treated x calendar month of the week start (January omitted): the robustness
    specification with treated-group-specific seasonality. Added after the pre-registered
    pre-trend test rejected (not pre-registered; DECISIONS.md, Phase 4)."""
    month = d["week_start"].dt.month.to_numpy()
    cols = {f"tr_month_{m:02d}": d["treated"].to_numpy() * (month == m) for m in range(2, 13)}
    return d.assign(**{k: v.astype(float) for k, v in cols.items()})


def add_unit_trends(d: pd.DataFrame, unit: str) -> tuple[pd.DataFrame, list[str]]:
    """Unit-specific linear trends (in years of event time), one column per unit: the
    robustness specification with zone-specific linear trends (demand wording, PLAN Amendment 3,
    C2; not pre-registered). With week FE one of them is collinear and is dropped by pyfixest.
    The trends are estimated on the whole static window, so they can absorb part of a gradual
    effect (stated with the result)."""
    t = d["event_week"].to_numpy() / 52.0
    u = d[unit].to_numpy()
    cols = {f"trend_{int(z)}": np.where(u == z, t, 0.0) for z in np.unique(u)}
    return d.assign(**cols), list(cols)


def static_window(df: pd.DataFrame, pre_weeks: int, post_end: pd.Timestamp | None = None
                  ) -> pd.DataFrame:
    """event_week in [-pre_weeks, -1] plus every post week (<= post_end if given)."""
    keep = df["event_week"] >= -pre_weeks
    if post_end is not None:
        keep &= df["week_start"] <= post_end
    return df[keep]


def vcov_spec(cluster: Sequence[str]) -> dict[str, str]:
    return {"CRV1": "+".join(cluster)}


def fit(df: pd.DataFrame, y: str, terms: Sequence[str], fe: Sequence[str],
        cluster: Sequence[str], weights: str | None = None) -> tuple[object, str]:
    fml = f"{y} ~ {' + '.join(terms)} | {' + '.join(fe)}"
    # lean / no data copies: only coefficients, SEs and the covariance are used, and the
    # pair-level speed designs (~1.2M rows) otherwise kept GBs alive per fit
    m = pf.feols(fml, data=df, vcov=vcov_spec(cluster), weights=weights, lean=True,
                 copy_data=False, store_data=False)
    gc.collect()
    return m, fml


def static_did(df: pd.DataFrame, y: str, unit: str, cluster: Sequence[str],
               pre_weeks: int, weights: str | None = None,
               controls: Sequence[str] = (),
               post_splits: Mapping[str, tuple[str, str]] | None = None,
               post_end: pd.Timestamp | None = None) -> DidResult:
    """Static DiD on `df` (columns unit, week_start, event_week, treated, y, controls)."""
    keep = list(dict.fromkeys([unit, "week_start", "event_week", "treated", y, *controls,
                               *cluster, *([weights] if weights else [])]))
    d = static_window(df[keep], pre_weeks, post_end).copy()
    post = d["event_week"] >= 0
    terms = []
    if post_splits:
        for name, (lo, hi) in post_splits.items():
            inside = post & (d["week_start"] >= pd.Timestamp(lo)) & \
                (d["week_start"] <= pd.Timestamp(hi))
            d[name] = (d["treated"] * inside).astype(float)
            terms.append(name)
        covered = sum(d[n] for n in terms) > 0
        if (post & (d["treated"] == 1) & ~covered).any():
            raise ValueError("post_splits do not cover every post week")
    else:
        d["treated_post"] = (d["treated"] * post).astype(float)
        terms.append("treated_post")
    m, fml = fit(d, y, [*terms, *controls], [unit, "week_start"], cluster, weights)
    coef, se, pv = m.coef(), m.se(), m.pvalue()
    return DidResult(
        coef={t: float(coef[t]) for t in terms}, se={t: float(se[t]) for t in terms},
        pvalue={t: float(pv[t]) for t in terms}, n_obs=int(m._N),
        n_units=int(d[unit].nunique()), n_treated_units=int(d.loc[d["treated"] == 1, unit]
                                                            .nunique()),
        n_clusters={c: int(d[c].nunique()) for c in cluster}, formula=fml,
        vcov=f"CRV1 by {' + '.join(cluster)}", weights=weights,
        extra={"controls": {c: float(coef[c]) for c in controls if c in coef}},
        log_outcome=y.startswith("log"))
