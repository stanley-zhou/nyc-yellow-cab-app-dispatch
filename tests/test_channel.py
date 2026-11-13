"""Amendment 4 channel helpers and the vendor x zone-group break rule (Amendment 4a)."""

from __future__ import annotations

import pandas as pd

from taxi_shock.channel import series_breaks
from taxi_shock.config import load_config, path


def test_series_breaks_flags_halving_and_vanishing():
    wk = pd.date_range("2026-01-04", periods=6, freq="7D")
    a = pd.DataFrame({"g": "a", "week_start": wk, "pickups": [2000, 2100, 900, 950, 980, 990]})
    b = pd.DataFrame({"g": "b", "week_start": wk[:3], "pickups": [3000, 3100, 3050]})  # vanishes
    c = pd.DataFrame({"g": "c", "week_start": wk, "pickups": [500, 100, 120, 110, 100, 90]})
    late = pd.DataFrame({"g": "d", "week_start": wk[3:], "pickups": [1500, 1600, 1550]})
    br = series_breaks(pd.concat([a, b, c, late]), ["g"], 0.5, 1000)
    assert set(zip(br["g"], br["week_start"], strict=True)) == {("a", wk[2]), ("b", wk[3])}


def test_every_vendor_group_break_is_documented():
    """The committed weekly vendor x zone-group series (results/flex_vendor_weekly.csv, D0) may
    only contain the breaks listed with a reason in config channel.known_breaks."""
    cfg = load_config()
    ch = cfg["channel"]
    v = pd.read_csv(path("results", cfg) / "flex_vendor_weekly.csv", parse_dates=["week_start"])
    br = series_breaks(v, ["zone_group", "vendor_id"], ch["break_ratio"], ch["break_min_weekly"])
    found = {(r.zone_group, int(r.vendor_id), r.week_start.strftime("%Y-%m-%d"))
             for r in br.itertuples()}
    known = {(k["zone_group"], int(k["vendor_id"]), k["week_start"]) for k in ch["known_breaks"]}
    assert all(k["reason"] for k in ch["known_breaks"])
    assert found == known
