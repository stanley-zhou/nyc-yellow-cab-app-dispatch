"""Negative / zero fare_amount rows per month, split by Flex Fare (payment_type 0) vs the rest, and
whether each negative row has a positive "reversal twin" (a row of the same file with the same
pickup/dropoff timestamps and zones and fare_amount > 0).

Evidence for the Flex Fare rule in int_trips_flagged (DECISIONS.md, Phase 1). Reads every raw
file in data/raw/tlc/yellow/ and config `quality.flex_fare_payment_type`. Writes
results/negative_fare_probe.json and prints per-month counts and the totals.

Usage:
    python scripts/probe_negative_fares.py
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from taxi_shock.config import load_config, path
from taxi_shock.io import connect


def main() -> None:
    cfg = load_config()
    flex = int(cfg["quality"]["flex_fare_payment_type"])
    t0 = time.perf_counter()
    con = connect(":memory:", read_only=False, cfg=cfg)
    rows = []
    for f in sorted(path("raw_yellow", cfg).glob("yellow_tripdata_*.parquet")):
        month = f.stem.removeprefix("yellow_tripdata_")
        con.execute(f"CREATE OR REPLACE TEMP TABLE t AS SELECT * FROM read_parquet('{f}')")
        r = con.execute(f"""
            WITH neg AS (
                SELECT n.*, EXISTS (
                    SELECT 1 FROM t p
                    WHERE p.fare_amount > 0
                      AND p.tpep_pickup_datetime = n.tpep_pickup_datetime
                      AND p.tpep_dropoff_datetime = n.tpep_dropoff_datetime
                      AND p.PULocationID = n.PULocationID
                      AND p.DOLocationID = n.DOLocationID) AS has_twin
                FROM t n WHERE n.fare_amount < 0)
            SELECT
                (SELECT count(*) FROM t),
                count(*) FILTER (WHERE payment_type = {flex}),
                count(*) FILTER (WHERE payment_type = {flex} AND has_twin),
                count(*) FILTER (WHERE payment_type IS DISTINCT FROM {flex}),
                count(*) FILTER (WHERE payment_type IS DISTINCT FROM {flex} AND has_twin),
                (SELECT count(*) FROM t WHERE payment_type = {flex}),
                (SELECT count(*) FROM t WHERE fare_amount = 0)
            FROM neg""").fetchone()
        keys = ["rows", "flex_neg", "flex_neg_with_twin", "other_neg", "other_neg_with_twin",
                "flex_all", "fare_zero"]
        rows.append({"month": month, **{k: int(v) for k, v in zip(keys, r, strict=True)}})
        print(rows[-1], flush=True)
    tot = {k: sum(r[k] for r in rows) for k in rows[0] if k != "month"}
    result = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "flex_fare_payment_type": flex,
        "twin_definition": ("same file, same pickup and dropoff timestamps, same PU/DO zones, "
                            "fare_amount > 0"),
        "totals": tot,
        "share_flex_neg_with_twin": round(tot["flex_neg_with_twin"] / tot["flex_neg"], 6)
        if tot["flex_neg"] else None,
        "share_other_neg_with_twin": round(tot["other_neg_with_twin"] / tot["other_neg"], 6)
        if tot["other_neg"] else None,
        "per_month": rows,
        "runtime_seconds": round(time.perf_counter() - t0, 1),
    }
    out = path("results", cfg) / "negative_fare_probe.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_month"}, indent=2))


if __name__ == "__main__":
    main()
