"""Record-format evidence per (year, VendorID): rows with identical pickup/dropoff timestamps
(and with a positive distance / different PU and DO zones), Flex Fare rows with zero distance, and
non-Flex zero-distance rows between different zones. Evidence for the record-format exemptions in
int_trips_flagged (DECISIONS.md, Phase 1). Writes results/record_format_probe.csv.

Usage:
    python scripts/probe_record_formats.py
"""

from __future__ import annotations

from taxi_shock.config import load_config, path
from taxi_shock.io import connect


def main() -> None:
    cfg = load_config()
    flex = int(cfg["quality"]["flex_fare_payment_type"])
    glob = (path("raw_yellow", cfg) / "yellow_tripdata_*.parquet").as_posix()
    with connect(":memory:", read_only=False, cfg=cfg) as con:
        df = con.execute(f"""
            SELECT substr(regexp_extract(filename, 'yellow_tripdata_(\\d{{4}})-', 1), 1, 4)
                       AS year,
                   VendorID AS vendor_id,
                   count(*) AS rows,
                   count(*) FILTER (WHERE tpep_dropoff_datetime = tpep_pickup_datetime)
                       AS same_ts,
                   count(*) FILTER (WHERE tpep_dropoff_datetime = tpep_pickup_datetime
                                    AND trip_distance > 0) AS same_ts_pos_distance,
                   count(*) FILTER (WHERE tpep_dropoff_datetime = tpep_pickup_datetime
                                    AND trip_distance > 0 AND PULocationID <> DOLocationID)
                       AS same_ts_pos_distance_diff_zone,
                   count(*) FILTER (WHERE payment_type = {flex}) AS flex,
                   count(*) FILTER (WHERE payment_type = {flex}
                                    AND coalesce(trip_distance, 0) <= 0) AS flex_zero_distance,
                   count(*) FILTER (WHERE payment_type = {flex}
                                    AND coalesce(trip_distance, 0) <= 0
                                    AND PULocationID <> DOLocationID)
                       AS flex_zero_distance_diff_zone,
                   count(*) FILTER (WHERE payment_type IS DISTINCT FROM {flex}
                                    AND coalesce(trip_distance, 0) <= 0
                                    AND PULocationID <> DOLocationID)
                       AS nonflex_zero_distance_diff_zone
            FROM read_parquet('{glob}', filename = true, union_by_name = true)
            GROUP BY ALL ORDER BY 1, 2""").df()
    out = path("results", cfg) / "record_format_probe.csv"
    df.to_csv(out, index=False, lineterminator="\n")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
