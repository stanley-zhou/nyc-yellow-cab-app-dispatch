"""Evidence for the Open-Meteo timezone decision (DECISIONS.md, Phase 0).

For one winter (EST) day and several DST (EDT) days, request the same day twice from the
archive API:
  A. `timezone=<project tz>` with default ISO local-time strings (what a naive pipeline does);
  B. `timezone=GMT` with unix seconds (what this pipeline does).
Then compare: (1) the UTC offset the API says it applied in A, (2) the true offset from the
IANA tz database, and (3) which absolute hour A's "00:00" value actually belongs to, by
matching A's temperature series against B's at every candidate shift.

Reads the Open-Meteo archive API (config `sources.weather_*`, `timezone`). Writes
results/open_meteo_offset_probe.json and prints the conclusion.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import numpy as np
import requests

from taxi_shock.config import load_config, path

PROBE_DAYS = ["2024-01-15", "2024-03-11", "2024-07-01", "2024-10-01", "2024-11-02"]
VAR = "temperature_2m"


def fetch(cfg: dict, day: str, tz: str, unixtime: bool, pad: int = 0) -> dict:
    src = cfg["sources"]
    d = dt.date.fromisoformat(day)
    params = {
        "latitude": src["weather_point"][0],
        "longitude": src["weather_point"][1],
        "start_date": (d - dt.timedelta(days=pad)).isoformat(),
        "end_date": (d + dt.timedelta(days=pad)).isoformat(),
        "hourly": VAR,
        "timezone": tz,
        **src["weather_units"],
    }
    if unixtime:
        params["timeformat"] = "unixtime"
    r = requests.get(src["weather_url"], params=params,
                     headers={"Accept-Encoding": "identity"},
                     timeout=float(src["http_timeout_seconds"]))
    r.raise_for_status()
    return r.json()


def main() -> None:
    cfg = load_config()
    tzname = cfg["timezone"]
    tz = ZoneInfo(tzname)
    rows = []
    for day in PROBE_DAYS:
        local = fetch(cfg, day, tzname, unixtime=False)
        gmt = fetch(cfg, day, "GMT", unixtime=True, pad=1)
        local_midnight = dt.datetime.fromisoformat(day).replace(tzinfo=tz)
        true_offset = int(local_midnight.utcoffset().total_seconds())
        api_offset = int(local["utc_offset_seconds"])
        a = np.array(local["hourly"][VAR], dtype=float)  # 24 values labelled 00:00..23:00 local
        g_t = np.array(gmt["hourly"]["time"], dtype=np.int64)
        g_v = np.array(gmt["hourly"][VAR], dtype=float)
        t0 = int(local_midnight.timestamp())  # true absolute time of local 00:00
        # For each candidate shift s (hours), compare A to GMT values at t0 + s h, ..., + 23 h.
        match = {}
        for s in (-2, -1, 0, 1, 2):
            idx = np.searchsorted(g_t, t0 + 3600 * (s + np.arange(len(a))))
            if idx.max() >= len(g_t) or not np.all(g_t[idx] == t0 + 3600 * (s + np.arange(len(a)))):
                continue
            match[s] = float(np.abs(g_v[idx] - a).max())
        exact = [s for s, err in match.items() if err == 0.0]
        rows.append({
            "day": day,
            "is_dst": bool(local_midnight.dst()),
            "true_utc_offset_seconds": true_offset,
            "api_reported_utc_offset_seconds": api_offset,
            "api_first_label": local["hourly"]["time"][0],
            "max_abs_temp_diff_by_shift_hours": {str(k): v for k, v in match.items()},
            "shifts_matching_exactly": exact,
            "true_hour_minus_label_hours": exact[0] if len(exact) == 1 else None,
        })
    dst_rows = [r for r in rows if r["is_dst"]]
    summary = {
        "checked_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "variable_compared": VAR,
        "probes": rows,
        "conclusion": {
            "api_offset_constant": len({r["api_reported_utc_offset_seconds"] for r in rows}) == 1,
            "dst_days_with_one_hour_label_shift": sum(
                r["true_hour_minus_label_hours"] == 1 for r in dst_rows),
            "dst_days_probed": len(dst_rows),
            "est_days_with_no_shift": sum(
                r["true_hour_minus_label_hours"] == 0 for r in rows if not r["is_dst"]),
            "est_days_probed": len(rows) - len(dst_rows),
        },
    }
    out = path("results", cfg) / "open_meteo_offset_probe.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["conclusion"], indent=2))
    for r in rows:
        print(r["day"], r["is_dst"], r["api_reported_utc_offset_seconds"],
              r["true_utc_offset_seconds"], r["max_abs_temp_diff_by_shift_hours"])


if __name__ == "__main__":
    main()
