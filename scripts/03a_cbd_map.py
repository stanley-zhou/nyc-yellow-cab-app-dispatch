"""Derive `is_cbd` per zone (geometric rule + fee-based validation) and write the mapping.

Reads the full warehouse (int_zone_cbd_fee_share, stg_zones), the zone shapefile and the raw OSM
60th Street geometry. Writes config/zones_cbd.csv and results/cbd_validation.json. Run between the
two dbt stages of `make dbt` (dim_zones and everything downstream read the CSV).

Usage:
    python scripts/03a_cbd_map.py
"""

from __future__ import annotations

import json
import logging

from taxi_shock.cbd import geometric_labels, resolve, sixtieth_street_line
from taxi_shock.config import load_config, path
from taxi_shock.download import OSM_60TH_FILE
from taxi_shock.io import connect

COLUMNS = ["zone_id", "zone_name", "borough", "is_cbd", "source", "geometric_is_cbd", "fee_label",
           "fee_share", "intra_fee_label", "intra_fee_share", "n_trips", "n_intra",
           "centroid_lon", "centroid_lat", "geometry_available"]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    lookup = path("raw_lookup", cfg)
    line = sixtieth_street_line(lookup / OSM_60TH_FILE, cfg["cbd"]["street_names"])
    geo = geometric_labels(lookup / "taxi_zones.shp", line)
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        zones = con.execute("select zone_id, zone_name, borough from stg_zones").df()
        fee = con.execute("select * from int_zone_cbd_fee_share").df()
    if fee.empty:
        raise SystemExit("int_zone_cbd_fee_share is empty: the fee window has no trips on disk")
    df, summary = resolve(zones, geo, fee, cfg["cbd"])

    out_csv = path("zones_cbd", cfg)
    df = df.sort_values("zone_id")[COLUMNS]
    df.to_csv(out_csv, index=False, float_format="%.4f", lineterminator="\n")
    summary = {"sixtieth_street_line": line, "fee_window": cfg["cbd"]["fee_window"],
               "thresholds": {k: cfg["cbd"][k] for k in ("fee_share_cbd_min",
                              "fee_share_not_cbd_max", "fee_min_trips", "agreement_min")},
               **summary}
    out_json = path("results", cfg) / "cbd_validation.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    logging.info("wrote %s (%d CBD zones) and %s", out_csv, summary["n_cbd_final"], out_json)


if __name__ == "__main__":
    main()
