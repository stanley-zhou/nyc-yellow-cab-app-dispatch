"""Placebo-in-time, leave-one-zone-out and permutation-placebo power checks (Phase 4).

  placebo_in_time   the static DiD with a fake policy date on pre-policy data only
  leave_one_out     the static DiD dropping each zone in turn (stability of beta)
  permutation       Amendment 1 (A2): random fake policy week x random fake treated zone set,
                    on pre-policy data only; the distribution of the placebo estimates gives the
                    permutation p-value of the real estimate and the minimum detectable effect
                    MDE = (z_{1 - size/2} + z_{power}) * sd(placebo estimates)
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd
from scipy import stats

from taxi_shock.causal.did import fit


def with_fake_policy(df: pd.DataFrame, fake_week: pd.Timestamp) -> pd.DataFrame:
    """`event_week` re-defined relative to `fake_week` (a panel week start)."""
    return df.assign(event_week=((df["week_start"] - fake_week).dt.days // 7).astype(int))


def quick_beta(df: pd.DataFrame, y: str, unit: str, weights: str | None = None,
               controls: Sequence[str] = ()) -> float:
    """Point estimate of the static DiD (treated x post) with `controls`, unit + week FE; no
    SEs needed. Placebos pass the controls of the estimate they are compared with (the
    reported specification has weather x treated; DECISIONS.md, Phase 4 review round 3)."""
    d = df.assign(treated_post=(df["treated"] * (df["event_week"] >= 0)).astype(float))
    m, _ = fit(d, y, ["treated_post", *controls], [unit, "week_start"], [unit], weights)
    return float(m.coef()["treated_post"])


def leave_one_out(df: pd.DataFrame, zones: Sequence[int], estimate: Callable[[pd.DataFrame],
                  float], zone_cols: Sequence[str]) -> pd.DataFrame:
    """Re-estimate dropping every row that involves zone z (in any of `zone_cols`)."""
    rows = []
    for z in zones:
        keep = np.ones(len(df), dtype=bool)
        for c in zone_cols:
            keep &= df[c].to_numpy() != z
        rows.append({"dropped_zone": int(z), "coef": estimate(df[keep])})
    return pd.DataFrame(rows)


def permutation(pre: pd.DataFrame, zones: Sequence[int], n_treated: int, draws: int,
                fake_weeks: Sequence[pd.Timestamp], assign: Callable[[pd.DataFrame, set[int]],
                pd.DataFrame], estimate: Callable[[pd.DataFrame], float], seed: int
                ) -> pd.DataFrame:
    """`draws` placebo estimates: each draws a fake policy week from `fake_weeks` and a random
    set of `n_treated` zones from `zones`; `assign(pre, fake_set)` returns the estimation sample
    with a `treated` column, `estimate` the static DiD coefficient."""
    rng = np.random.default_rng(seed)
    pool = np.asarray(sorted(zones))
    rows = []
    for i in range(draws):
        wk = pd.Timestamp(fake_weeks[int(rng.integers(len(fake_weeks)))])
        fake = set(int(z) for z in rng.choice(pool, size=n_treated, replace=False))
        d = with_fake_policy(assign(pre, fake), wk)
        rows.append({"draw": i, "fake_week": wk, "coef": estimate(d)})
    return pd.DataFrame(rows)


def power_summary(placebo: pd.Series, beta: float, size: float, power: float) -> dict:
    sd = float(placebo.std(ddof=1))
    mult = float(stats.norm.ppf(1 - size / 2) + stats.norm.ppf(power))
    return {"n_draws": int(len(placebo)), "mean": float(placebo.mean()), "sd": sd,
            "quantiles": {q: float(placebo.quantile(q)) for q in (0.025, 0.05, 0.5, 0.95,
                                                                   0.975)},
            "share_abs_ge_abs_beta": float((placebo.abs() >= abs(beta)).mean()),
            "mde_multiplier": mult, "mde": mult * sd, "mde_pct": float(np.expm1(mult * sd)),
            "size": size, "power": power}
