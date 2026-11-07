"""Build figures from files under results/ only (never from the warehouse directly).

Usage:
    python scripts/09_figures.py --smoke     # Phase-0 placeholder figure
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from taxi_shock.config import load_config, path
from taxi_shock.viz.figures import smoke_placeholder


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--smoke", action="store_true", required=True)
    ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    fc = pd.read_parquet(path("smoke.results_dir", cfg) / "forecasts_smoke.parquet")
    paths = smoke_placeholder(fc, path("smoke.figures_dir", cfg) / "F0_smoke_placeholder")
    logging.info("wrote %s", ", ".join(str(p) for p in paths))


if __name__ == "__main__":
    main()
