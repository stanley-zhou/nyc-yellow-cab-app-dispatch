"""Amendment 4, D1 (with the Amendment 4a rulings): the market shift, descriptively.

Channel (Amendment 4a): app = any e-hail app (Flex Fare before the request_source files,
request_source not NULL from them); street = street hail. The CMT outer-borough block
(`is_cmt_outer_block`; DECISIONS, D1) is its own series: every outer-borough figure is given with
and without it. Source: the dbt mart fct_weekly_zone_channel (valid in-grid pickups; complete panel
weeks of channel.window).

Outputs
    results/channel_weekly.csv        week x zone group: app, street, block, total
    results/channel_monthly.csv       month x zone group (weeks by the month of their start, the
                                      method of Amendment 4's motivating numbers): totals and app
                                      shares with and without the block
    results/channel_restatement.json  Amendment 4's motivating numbers, reproduced from
                                      record_format_shares.csv and restated with the channel
                                      definition, with and without the block
    results/channel_decomposition.csv growth accounting by zone group: change of mean weekly
                                      pickups 2023 -> 2025 (full years) and 2023 -> 2026 (the same
                                      Jan-Sep weeks of both years), split into app and street-hail
                                      contributions (block separate)
    results/channel_zone_share.csv    zone x period app share and mean weekly pickups (F6b; D2)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.causal.panel import full_weeks
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("channel")
GROUPS = ["cbd", "manhattan_non_cbd", "airports", "other"]


def load(cfg: dict) -> pd.DataFrame:
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        w = con.execute("""
            select zone_id, week_start, zone_group, channel, is_cmt_outer_block,
                   sum(pickups) as pickups
            from fct_weekly_zone_channel group by all""").df()
    w["week_start"] = pd.to_datetime(w["week_start"])
    w = full_weeks(w, cfg)
    w["series"] = np.where(w["is_cmt_outer_block"], "block", w["channel"])
    return w


def wide(w: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    x = w.pivot_table(index=keys, columns="series", values="pickups", aggfunc="sum",
                      fill_value=0).reindex(columns=["app", "street", "block"], fill_value=0)
    x["total"] = x.sum(axis=1)
    x["total_excl_block"] = x["app"] + x["street"]
    x["app_share"] = x["app"] / x["total"]
    x["app_share_excl_block"] = x["app"] / x["total_excl_block"]
    return x.reset_index()


def growth(w: pd.DataFrame, base: list[pd.Timestamp], end: list[pd.Timestamp],
           label: str) -> list[dict]:
    """Change of mean weekly pickups between two week sets, by zone group and series."""
    rows = []
    for g in [*GROUPS, "all"]:
        x = w if g == "all" else w[w["zone_group"] == g]
        n_b, n_e = len(base), len(end)
        s = {k: (x.loc[x["week_start"].isin(base) & (x["series"] == k), "pickups"].sum() / n_b,
                 x.loc[x["week_start"].isin(end) & (x["series"] == k), "pickups"].sum() / n_e)
             for k in ("app", "street", "block")}
        for incl in (True, False):
            keys = ["app", "street", "block"] if incl else ["app", "street"]
            b = sum(s[k][0] for k in keys)
            e = sum(s[k][1] for k in keys)
            d = e - b
            row = {"comparison": label, "zone_group": g, "with_cmt_block": incl,
                   "base_weeks": n_b, "end_weeks": n_e, "base_mean_weekly": b,
                   "end_mean_weekly": e, "change": d, "change_pct": d / b if b else None}
            for k in keys:
                row[f"{k}_base"], row[f"{k}_end"] = s[k]
                row[f"{k}_change"] = s[k][1] - s[k][0]
                row[f"{k}_contribution"] = (s[k][1] - s[k][0]) / d if d else None
            rows.append(row)
    return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    w = load(cfg)

    weekly = wide(w, ["week_start", "zone_group"])
    allw = wide(w, ["week_start"]).assign(zone_group="all")
    pd.concat([weekly, allw]).sort_values(["zone_group", "week_start"]).to_csv(
        res / "channel_weekly.csv", index=False, lineterminator="\n", float_format="%.6g")

    w["month"] = w["week_start"].dt.to_period("M").astype(str)
    monthly = wide(w, ["month", "zone_group"])
    # weeks are assigned to the month of their start, so months hold 4 or 5 weeks: per-week means
    # make months comparable (review round 1: 2023-01 has 5 weeks, 2026-01 has 4)
    nwk = w.groupby("month")["week_start"].nunique()
    monthly["n_weeks"] = monthly["month"].map(nwk)
    for c in ("app", "street", "block", "total", "total_excl_block"):
        monthly[f"{c}_per_week"] = monthly[c] / monthly["n_weeks"]
    monthly.to_csv(res / "channel_monthly.csv", index=False, lineterminator="\n",
                   float_format="%.6g")

    # Amendment 4's motivating numbers: reproduced (record_format_shares.csv, Flex share) and
    # restated (channel definition; with / without the block)
    rf = pd.read_csv(res / "record_format_shares.csv", parse_dates=["week_start"])
    rf["month"] = rf["week_start"].dt.to_period("M").astype(str)
    rfm = rf.groupby(["month", "zone_group"])[["pickups", "pickups_flex"]].sum()
    mm = monthly.set_index(["month", "zone_group"])
    rest = {}
    for m in cfg["channel"]["motivation_months"]:
        rest[m] = {}
        for g in ("cbd", "other"):
            r = rfm.loc[(m, g)]
            c = mm.loc[(m, g)]
            rest[m][g] = {
                "reproduced_pickups": int(r["pickups"]),
                "reproduced_flex_share": float(r["pickups_flex"] / r["pickups"]),
                "pickups": int(c["total"]), "app_share": float(c["app_share"]),
                "pickups_excl_cmt_block": int(c["total_excl_block"]),
                "app_share_excl_cmt_block": float(c["app_share_excl_block"]),
                "cmt_block_pickups": int(c["block"]), "n_weeks": int(c["n_weeks"]),
                "pickups_per_week": float(c["total_per_week"]),
                "street_per_week": float(c["street_per_week"]),
                "app_per_week": float(c["app_per_week"]),
                "pickups_excl_cmt_block_per_week": float(c["total_excl_block_per_week"])}
    (res / "channel_restatement.json").write_text(json.dumps({
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": "weeks assigned to the month of their week start (the method of Amendment 4's "
                  "figures, from results/record_format_shares.csv); months hold 4 or 5 weeks, "
                  "so compare the *_per_week values across months, not the monthly sums",
        "months": rest}, indent=2) + "\n")

    weeks = pd.Series(sorted(w["week_start"].unique()))
    yr = weeks.dt.year
    last = weeks.max()
    same = weeks[(weeks.dt.month < last.month) | ((weeks.dt.month == last.month)
                                                  & (weeks.dt.day <= last.day))]
    rows = (growth(w, list(weeks[yr == 2023]), list(weeks[yr == 2025]), "2023_to_2025")
            + growth(w, list(same[same.dt.year == 2023]), list(same[same.dt.year == 2026]),
                     "2023_to_2026_jan_sep"))
    pd.DataFrame(rows).to_csv(res / "channel_decomposition.csv", index=False,
                              lineterminator="\n", float_format="%.6g")

    # zone x period app share (F6b small multiples; same Jan-Sep span for 2026)
    w["period"] = w["week_start"].dt.year.astype(str)
    w.loc[w["period"] == "2026", "period"] = "2026_jan_sep"
    z = wide(w, ["zone_id", "period"])
    nw = w.groupby("period")["week_start"].nunique()
    z["mean_weekly_pickups"] = z["total"] / z["period"].map(nw)
    z.to_csv(res / "channel_zone_share.csv", index=False, lineterminator="\n",
             float_format="%.6g")
    d = pd.DataFrame(rows)
    LOG.info("D1: %s", d[(d["comparison"] == "2023_to_2025")][
        ["zone_group", "with_cmt_block", "change", "app_change", "street_change"]].to_string())


if __name__ == "__main__":
    main()
