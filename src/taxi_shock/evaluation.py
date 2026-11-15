"""Evaluation helpers shared by scripts/04b_evaluate.py and the tests.

  sort_clip_quantiles   the post-processing every model's quantiles get (monotone rearrangement
                        per row, clip at zero)
  daily_errors          per origin day and zone group: sum |y - point| and sum y
  wape_gap_bootstrap    paired block bootstrap of WAPE differences between every pair of models

Pure computation on DataFrames and arrays; reads and writes no files.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def sort_clip_quantiles(fc: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    """Sort the quantile columns per row (removes crossings), clip at zero, point = median
    column. Returns a copy."""
    out = fc.copy()
    out[list(cols)] = np.clip(np.sort(out[list(cols)].to_numpy(), axis=1), 0.0, None)
    out["point"] = out[list(cols)[len(cols) // 2]]
    return out


def daily_errors(fc: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """Per origin and zone group (plus zone_group 'all'): abs_err = sum |y - point| and
    y = sum y over the rows with an actual and a forecast — so WAPE = abs_err / y."""
    d = fc.loc[fc["y"].notna() & fc["point"].notna(), ["origin", "zone_id", "y", "point"]]
    d = d.assign(zone_group=d["zone_id"].map(groups), abs_err=(d["y"] - d["point"]).abs())
    per = d.groupby(["origin", "zone_group"])[["abs_err", "y"]].sum().reset_index()
    tot = d.groupby("origin")[["abs_err", "y"]].sum().reset_index().assign(zone_group="all")
    return pd.concat([per, tot], ignore_index=True)


def wape_gap_bootstrap(daily: pd.DataFrame, reps: int, block_days: int, seed: int
                       ) -> pd.DataFrame:
    """Paired block bootstrap of WAPE(model) - WAPE(reference) for every ordered model pair.

    `daily`: daily_errors rows with a `model` column. Per zone group, the origin days every
    model covers are cut into consecutive blocks of `block_days`; each replicate resamples
    blocks with replacement (the same draw for all models: paired) and recomputes each model's
    WAPE with its own denominator. Reported per pair: point gap, 2.5/97.5% percentiles,
    `distinguishable` (the interval excludes 0) and `reference_is_best` (the reference has the
    lowest point WAPE of the group).
    """
    rng = np.random.default_rng(seed)
    rows = []
    for g, d in daily.groupby("zone_group", sort=True):
        err = d.pivot_table(index="origin", columns="model", values="abs_err")
        ys = d.pivot_table(index="origin", columns="model", values="y")
        common = err.dropna().index.intersection(ys.dropna().index).sort_values()
        err, y = err.loc[common], ys.loc[common, err.columns]
        block = np.arange(len(common)) // int(block_days)
        e_b = err.groupby(block).sum().to_numpy()          # blocks x models
        y_b = y.groupby(block).sum().to_numpy()            # blocks x models
        draw = rng.integers(0, len(y_b), size=(int(reps), len(y_b)))
        boot = e_b[draw].sum(axis=1) / y_b[draw].sum(axis=1)   # reps x models
        point = err.sum().to_numpy() / y.sum().to_numpy()
        best = int(np.argmin(point))
        models = list(err.columns)
        for j, m in enumerate(models):
            for k, r in enumerate(models):
                if j == k:
                    continue
                lo, hi = np.percentile(boot[:, j] - boot[:, k], [2.5, 97.5])
                rows.append({"zone_group": g, "model": m, "reference": r,
                             "wape": round(float(point[j]), 6),
                             "wape_reference": round(float(point[k]), 6),
                             "gap": round(float(point[j] - point[k]), 6),
                             "gap_ci_lo": round(float(lo), 6), "gap_ci_hi": round(float(hi), 6),
                             "distinguishable": bool(lo > 0.0 or hi < 0.0),
                             "reference_is_best": k == best,
                             "n_days": len(common), "block_days": int(block_days),
                             "reps": int(reps)})
    return (pd.DataFrame(rows).sort_values(["zone_group", "reference", "wape"])
            .reset_index(drop=True))


def tied_with_best(gaps: pd.DataFrame, zone_group: str) -> tuple[str, list[str]]:
    """(best model, models whose gap to it is not distinguishable from 0) for one group."""
    g = gaps[(gaps["zone_group"] == zone_group) & gaps["reference_is_best"]]
    best = str(g["reference"].iloc[0])
    return best, g.loc[~g["distinguishable"]].sort_values("wape")["model"].tolist()
