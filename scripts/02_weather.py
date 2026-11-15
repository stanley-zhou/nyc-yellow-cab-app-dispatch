"""Download Open-Meteo archive hourly weather for one city-wide point, in yearly chunks.

Reads config `sources.weather_url` / `sources.weather_point` and, with --all,
`data.yellow_months`. Writes one CSV per chunk to data/raw/weather/ and updates
data/raw/manifest.csv.

Usage:
    python scripts/02_weather.py --start 2024-10-01 --end 2024-10-31
    python scripts/02_weather.py --all     # first..last day of data.yellow_months
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from taxi_shock.config import load_config
from taxi_shock.download import download_weather


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config()
    if args.all:
        lo, hi = cfg["data"]["yellow_months"]
        start = pd.Period(lo, "M").start_time.date().isoformat()
        end = pd.Period(hi, "M").end_time.date().isoformat()
    elif args.start and args.end:
        start, end = args.start, args.end
    else:
        ap.error("give --start and --end, or --all")
    download_weather(start, end, cfg)


if __name__ == "__main__":
    main()
