"""Amendment 4a: diagnose the CMT outer-borough block before applying the rule.

The block (D0): VendorID 1 street hails (non-Flex) picked up in the `other` zone group; it falls
from ~24k to ~5k pickups per week at 2026-05-31.

1. Who gained it? Weekly `other`-group pickups by every VendorID and channel around the break
   (results/flex_vendor_weekly.csv, written by 10a) and the change of the total.
2. What is it? Trip characteristics of the block in the three months before the break against the
   other outer-borough street hails of the same months (every other VendorID), from the raw files
   (all columns, including RatecodeID and store_and_fwd_flag that the warehouse does not carry):
   pickup / dropoff zones, hours, distance, fare, total, tip, payment type, passenger count, rate
   code, store-and-forward flag, duration, and the share with identical pickup/dropoff times.
   Records: valid pickup zone, pickup inside the file's month.

Writes results/cmt_block_diagnosis.json.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import duckdb
import pandas as pd

from taxi_shock.config import load_config, path

LOG = logging.getLogger("cmt_block")
BEFORE = ["2026-03", "2026-05"]          # months before the break
AFTER = ["2026-06", "2026-08"]           # months after it


def records(cfg: dict, months: list[str], other_zones: list[int]) -> str:
    lo, hi = cfg["zones"]["valid_ids"]
    flex = int(cfg["quality"]["flex_fare_payment_type"])
    files = ", ".join(f"'{(path('raw_yellow', cfg) / f'yellow_tripdata_{m}.parquet').as_posix()}'"
                      for m in pd.period_range(*months, freq="M").astype(str))
    zl = ", ".join(map(str, other_zones))
    return f"""
        select *, case when VendorID = 1 then 'cmt_block' else 'other_vendors' end as grp,
               extract(hour from tpep_pickup_datetime) as hr,
               date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0 as dur_min
        from read_parquet([{files}], union_by_name = true, filename = true)
        where PULocationID between {lo} and {hi} and PULocationID in ({zl})
          and coalesce(payment_type, -1) <> {flex}
          and tpep_pickup_datetime >= strptime(regexp_extract(filename,
                  'yellow_tripdata_(\\d{{4}}-\\d{{2}})', 1), '%Y-%m')
          and tpep_pickup_datetime < strptime(regexp_extract(filename,
                  'yellow_tripdata_(\\d{{4}}-\\d{{2}})', 1), '%Y-%m') + interval 1 month"""


def dist(con, q: str, col: str, top: int = 8) -> dict:
    d = con.execute(f"""select grp, coalesce(cast({col} as varchar), 'NULL') as v, count(*) as n
                        from ({q}) group by all""").df()
    out = {}
    for g, x in d.groupby("grp"):
        x = x.assign(share=x["n"] / x["n"].sum()).sort_values("share", ascending=False)
        out[g] = {str(r.v): round(float(r.share), 4) for r in x.head(top).itertuples()}
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    zs = pd.read_csv(res / "zone_summary.csv")
    other = sorted(zs.loc[zs["zone_group"] == "other", "zone_id"].astype(int))
    names = zs.set_index("zone_id")["zone_name"].to_dict()

    # 1. who gained it (warehouse-based weekly series from 10a)
    v = pd.read_csv(res / "flex_vendor_weekly.csv", parse_dates=["week_start"])
    v = v[(v["zone_group"] == "other") & v["week_start"].between("2026-04-26", "2026-06-28")]
    v = v.assign(street=v["pickups"] - v["pickups_flex"])
    wk = v.pivot_table(index="week_start", columns="vendor_id", values=["pickups", "street"],
                       aggfunc="sum").fillna(0)
    weekly = {str(d.date()): {f"{a}_vendor_{int(b)}": int(wk.loc[d, (a, b)])
                              for a, b in wk.columns} for d in wk.index}
    pre_w = [d for d in wk.index if d < pd.Timestamp("2026-05-31")][-4:]
    post_w = [d for d in wk.index if d >= pd.Timestamp("2026-05-31")][:4]

    def mean_by(kind):
        cols = [c for c in wk.columns if c[0] == kind]
        return {f"vendor_{int(c[1])}": [float(wk.loc[pre_w, c].mean()),
                                        float(wk.loc[post_w, c].mean())] for c in cols}

    gain = {"weeks_before": [str(d.date()) for d in pre_w],
            "weeks_after": [str(d.date()) for d in post_w],
            "mean_weekly_pickups_before_after": mean_by("pickups"),
            "mean_weekly_street_hails_before_after": mean_by("street"),
            "total_before_after": [float(wk["pickups"].loc[pre_w].sum(axis=1).mean()),
                                   float(wk["pickups"].loc[post_w].sum(axis=1).mean())]}

    # 2. what it is (raw files)
    con = duckdb.connect()
    q = records(cfg, BEFORE, other)
    n = con.execute(f"select grp, count(*) from ({q}) group by 1").fetchall()
    num = con.execute(f"""
        select grp,
               quantile_cont(trip_distance, [0.25, 0.5, 0.75]) as distance_q,
               quantile_cont(fare_amount, [0.25, 0.5, 0.75]) as fare_q,
               quantile_cont(total_amount, [0.25, 0.5, 0.75]) as total_q,
               quantile_cont(dur_min, [0.25, 0.5, 0.75]) as duration_min_q,
               avg((tip_amount > 0)::int) as share_tipped,
               avg((tpep_pickup_datetime = tpep_dropoff_datetime)::int) as share_same_ts,
               avg((PULocationID = DOLocationID)::int) as share_same_zone,
               avg((DOLocationID in (264, 265))::int) as share_unknown_dropoff
        from ({q}) group by 1""").df()
    chars = {r["grp"]: {k: ([round(float(x), 3) for x in r[k]] if isinstance(r[k], list | tuple)
                            or hasattr(r[k], "__len__") else round(float(r[k]), 4))
                        for k in num.columns if k != "grp"} for _, r in num.iterrows()}
    pu = dist(con, q, "PULocationID", 10)
    do = dist(con, q, "DOLocationID", 10)
    named = {k: {g: {f"{z} {names.get(int(z), '?') if z.isdigit() else ''}".strip(): s
                     for z, s in d.items()} for g, d in x.items()}
             for k, x in (("pickup_zones_top10", pu), ("dropoff_zones_top10", do))}
    out = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "specification": "PLAN.md Amendment 4a (CMT outer-borough block: diagnose first)",
        "block": "VendorID 1, pickup zone in zone group 'other', not Flex Fare",
        "who_gained_it": gain, "weekly_other_group_by_vendor": weekly,
        "characteristics_months": BEFORE,
        "comparison": "street hails (not Flex) of every other VendorID in the same zones/months",
        "records": {g: int(c) for g, c in n},
        "numeric": chars, **named,
        "hours": dist(con, q, "hr", 24),
        "payment_type": dist(con, q, "payment_type"),
        "passenger_count": dist(con, q, "passenger_count"),
        "rate_code": dist(con, q, "RatecodeID"),
        "store_and_fwd_flag": dist(con, q, "store_and_fwd_flag"),
    }
    qa = records(cfg, AFTER, other)
    out["records_after_months"] = AFTER
    out["records_after"] = {g: int(c) for g, c in con.execute(
        f"select grp, count(*) from ({qa}) group by 1").fetchall()}
    (res / "cmt_block_diagnosis.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    LOG.info("CMT block: %s before, %s after", out["records"], out["records_after"])


if __name__ == "__main__":
    main()
