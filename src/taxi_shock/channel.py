"""Channel analyses (app dispatch vs street hail; PLAN Amendment 4): helpers shared by scripts
and tests. Pure computation: takes weekly series as a DataFrame and returns a DataFrame."""

from __future__ import annotations

import pandas as pd


def series_breaks(df: pd.DataFrame, keys: list[str], ratio: float, min_base: float,
                  value: str = "pickups", time: str = "week_start") -> pd.DataFrame:
    """Rows where a series (one per `keys` combination) falls below `ratio` x its previous week,
    with a previous week of at least `min_base`. Missing weeks inside a series' span count as 0,
    so a series that vanishes is flagged too (the check added for the CMT outer-borough break,
    PLAN Amendment 4a)."""
    weeks = pd.Index(sorted(df[time].unique()), name=time)
    out = []
    for k, x in df.groupby(keys):
        s = x.groupby(time)[value].sum().reindex(weeks, fill_value=0)
        s = s.loc[s.index >= s[s > 0].index.min()]
        prev = s.shift()
        hit = (prev >= min_base) & (s < ratio * prev)
        for t in s.index[hit]:
            out.append({**dict(zip(keys, k if isinstance(k, tuple) else (k,), strict=True)),
                        time: t, "previous": float(prev[t]), value: float(s[t])})
    return pd.DataFrame(out, columns=[*keys, time, "previous", value])
