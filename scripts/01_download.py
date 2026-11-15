"""Download TLC yellow-taxi Parquet files and the zone lookups.

Reads config `data.yellow_months` (with --all) and the `sources` URLs. Writes the monthly
Parquet files to data/raw/tlc/yellow/, the zone lookup CSV, zone shapefile and OSM 60th Street
geometry to data/raw/lookup/, and one row per file to data/raw/manifest.csv.

Usage:
    python scripts/01_download.py --months 2024-10            # one month
    python scripts/01_download.py --months 2019-01:2026-09    # inclusive range
    python scripts/01_download.py --all                       # config data.yellow_months
"""

from __future__ import annotations

import argparse
import logging

from taxi_shock.config import load_config
from taxi_shock.download import (
    download_lookups,
    download_osm_60th_street,
    download_yellow,
    month_range,
)


def parse_months(spec: str) -> list[str]:
    months: list[str] = []
    for part in spec.split(","):
        if ":" in part:
            lo, hi = part.split(":")
            months.extend(month_range(lo, hi))
        else:
            months.append(part)
    return months


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--months", help="YYYY-MM, comma list, or LO:HI range")
    g.add_argument("--all", action="store_true", help="every month in data.yellow_months")
    ap.add_argument("--skip-lookups", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config()
    months = month_range(*cfg["data"]["yellow_months"]) if args.all else parse_months(args.months)
    if not args.skip_lookups:
        download_lookups(cfg)
        download_osm_60th_street(cfg)
    files = download_yellow(months, cfg)
    logging.info("yellow files on disk: %d", len(files))


if __name__ == "__main__":
    main()
