"""Source outages: hours where the TLC files hold almost no yellow trips although nothing in
the city explains it (DECISIONS.md, Phase 4b).

Rule (`source_outages.rule`): an hour is low when citywide pickups are below `hour_share` of
the median of the same hour of the week over `weeks_each_side` weeks before and after (and that
median is at least `min_reference`). Consecutive low hours form a run. A run is explained when
its day had >= `snow_day_in` inches of snow or it lies in a `real_events` window (COVID onset);
every other run must be inside a configured outage window (`source_outages.windows`). Days that
touch an outage window are left out of the drift monitors. Pure computation: takes an hourly
citywide pickup series and the config, returns the low-volume runs and the outage days.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def low_volume_runs(hourly: pd.Series, rule: dict[str, Any]) -> pd.DataFrame:
    """Runs of consecutive low hours in a citywide hourly pickup series (DatetimeIndex)."""
    k = int(rule["weeks_each_side"])
    lags = [hourly.shift(168 * j) for j in range(-k, k + 1) if j != 0]
    ref = pd.concat(lags, axis=1).median(axis=1)
    low = (hourly < rule["hour_share"] * ref) & (ref >= rule["min_reference"])
    idx = hourly.index[low.to_numpy()]
    if not len(idx):
        return pd.DataFrame(columns=["start", "end", "hours", "pickups", "reference"])
    run = (idx.to_series().diff() != pd.Timedelta(hours=1)).cumsum().to_numpy()
    out = []
    for r in np.unique(run):
        hrs = idx[run == r]
        out.append({"start": hrs.min(), "end": hrs.max(), "hours": len(hrs),
                    "pickups": float(hourly[hrs].sum()), "reference": float(ref[hrs].sum())})
    return pd.DataFrame(out)


def windows(cfg: dict[str, Any]) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    return [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in cfg["source_outages"]["windows"]]


def outage_days(cfg: dict[str, Any]) -> set[pd.Timestamp]:
    """Every local date touched by a configured outage window."""
    days = set()
    for a, b in windows(cfg):
        days |= set(pd.date_range(a.normalize(), b.normalize(), freq="D"))
    return days


def in_any(ts: pd.Timestamp, spans: list[tuple[pd.Timestamp, pd.Timestamp]]) -> bool:
    return any(a <= ts <= b for a, b in spans)
