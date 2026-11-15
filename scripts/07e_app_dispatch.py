"""Phase 4b mechanism check (PLAN Amendment 3, C1): app-dispatch share by pickup zone, from
`request_source`.

TLC added a `request_source` column to the yellow trip files from 2026-06 on; it is not in the
yellow data dictionary (version of 2025-03-25). The codes HV0003 / HV0005 are the TLC licence
numbers of Uber / Lyft (HVFHS data dictionary); every other value (NULL, 'A', 'CC', 'EH0004',
'EH0010', ...) is undocumented and is counted as not app-dispatched (shares reported per code).

Records: the raw monthly files of `app_dispatch.months`, every record with a valid pickup zone
(zones.valid_ids) and a pickup inside its file's month — the column is not carried into the dbt
warehouse, and rebuilding the 157M-row trip table for one descriptive column was rejected
(DECISIONS.md). Growth per zone: log(mean weekly pickups in growth_years[1] / growth_years[0])
from the complete demand panel (Phase 4). Reads those raw files in data/raw/tlc/yellow/, the
weekly demand panel from data/warehouse.duckdb (taxi_shock.causal.panel.demand_panel) and
results/zone_summary.csv.

Writes
    results/app_dispatch_codes.csv   records per month and request_source code
    results/app_dispatch_share.csv   per zone: records, Uber / Lyft / app shares, zone group,
                                     donut-control flag, base and end-year mean weekly pickups,
                                     growth
    results/app_dispatch_summary.json  group means and correlations (Pearson, Spearman) of growth
                                     vs app share: all zones and Manhattan
Usage:
    python scripts/07e_app_dispatch.py
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from taxi_shock.causal.panel import control_zone_ids, demand_panel
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("app_dispatch")


def records(cfg: dict) -> pd.DataFrame:
    ad = cfg["app_dispatch"]
    months = pd.period_range(*ad["months"], freq="M")
    lo, hi = cfg["zones"]["valid_ids"]
    con = duckdb.connect()
    parts = []
    for m in months:
        f = path("raw_yellow", cfg) / f"yellow_tripdata_{m}.parquet"
        start = m.to_timestamp()
        parts.append(con.execute(f"""
            select '{m}' as month, PULocationID::integer as zone_id,
                   coalesce(request_source, 'NULL') as code, count(*) as n
            from read_parquet('{f.as_posix()}')
            where PULocationID between {lo} and {hi}
              and tpep_pickup_datetime >= ? and tpep_pickup_datetime < ?
            group by all""", [start, (m + 1).to_timestamp()]).df())
    return pd.concat(parts, ignore_index=True)


def growth(cfg: dict) -> pd.DataFrame:
    ad = cfg["app_dispatch"]
    y0, y1 = ad["growth_years"]
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        w = demand_panel(con, cfg)
    w = w.assign(year=w["week_start"].dt.year)
    g = w[w["year"].isin([y0, y1])].pivot_table(index="zone_id", columns="year",
                                               values="pickups", aggfunc="mean")
    g.columns = [f"mean_weekly_{c}" for c in g.columns]
    base = g[f"mean_weekly_{y0}"]
    g["growth_log"] = np.where(base >= ad["min_weekly_base"],
                               np.log(g[f"mean_weekly_{y1}"] / base.where(base > 0)), np.nan)
    return g.reset_index()


def corr(d: pd.DataFrame) -> dict:
    d = d.dropna(subset=["share_app", "growth_log"])
    if len(d) < 5:
        return {"n": len(d)}
    p = stats.pearsonr(d["share_app"], d["growth_log"])
    s = stats.spearmanr(d["share_app"], d["growth_log"])
    return {"n": len(d), "pearson_r": float(p.statistic), "pearson_p": float(p.pvalue),
            "spearman_rho": float(s.statistic), "spearman_p": float(s.pvalue)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    ad, res = cfg["app_dispatch"], path("results", cfg)
    r = records(cfg)
    codes = r.groupby(["month", "code"])["n"].sum().reset_index()
    codes["share"] = codes["n"] / codes.groupby("month")["n"].transform("sum")
    codes.to_csv(res / "app_dispatch_codes.csv", index=False, lineterminator="\n",
                 float_format="%.6g")
    z = r.pivot_table(index="zone_id", columns="code", values="n", aggfunc="sum", fill_value=0)
    out = pd.DataFrame({"records": z.sum(axis=1)})
    for code, name in ad["app_codes"].items():
        out[f"share_{name}"] = z.get(code, 0) / out["records"]
    out["share_app"] = out[[f"share_{n}" for n in ad["app_codes"].values()]].sum(axis=1)
    out.loc[out["records"] < ad["min_trips"], ["share_app", *[f"share_{n}" for n in
                                                              ad["app_codes"].values()]]] = np.nan
    zs = pd.read_csv(res / "zone_summary.csv")
    ctl = set(control_zone_ids(zs, cfg))
    out = out.reset_index().merge(zs[["zone_id", "zone_name", "borough", "zone_group",
                                      "is_cbd"]], on="zone_id", how="right")
    out["is_donut_control"] = out["zone_id"].isin(ctl)
    out = out.merge(growth(cfg), on="zone_id", how="left")
    out["records"] = out["records"].fillna(0).astype(int)
    out.to_csv(res / "app_dispatch_share.csv", index=False, lineterminator="\n",
               float_format="%.6g")

    def group_mean(d: pd.DataFrame) -> dict:
        d = d.dropna(subset=["share_app"])
        return {"zones": len(d), "records": int(d["records"].sum()),
                "share_app_pooled": float((d["share_app"] * d["records"]).sum()
                                          / d["records"].sum()) if len(d) else None,
                "share_app_median_zone": float(d["share_app"].median()) if len(d) else None}

    man = out[out["borough"] == "Manhattan"]
    summary = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "months": ad["months"], "app_codes": ad["app_codes"],
        "codes_note": "request_source is not in the yellow data dictionary (2025-03-25); "
                      "HV0003 = Uber, HV0005 = Lyft per the HVFHS dictionary; other codes "
                      "undocumented (results/app_dispatch_codes.csv)",
        "groups": {"cbd": group_mean(out[out["is_cbd"]]),
                   "donut_control": group_mean(out[out["is_donut_control"]]),
                   "manhattan_non_cbd_all": group_mean(man[~man["is_cbd"]]),
                   "outer_boroughs_brooklyn_queens": group_mean(
                       out[out["borough"].isin(["Brooklyn", "Queens"])
                           & (out["zone_group"] != "airports")]),
                   "airports": group_mean(out[out["zone_group"] == "airports"])},
        "correlation_growth_vs_app_share": {"all_zones": corr(out), "manhattan": corr(man)},
        "growth_years": ad["growth_years"], "min_trips": ad["min_trips"],
        "min_weekly_base": ad["min_weekly_base"]}
    (res / "app_dispatch_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    LOG.info("groups: %s", {k: v["share_app_pooled"] for k, v in summary["groups"].items()})
    LOG.info("correlations: %s", summary["correlation_growth_vs_app_share"])


if __name__ == "__main__":
    main()
