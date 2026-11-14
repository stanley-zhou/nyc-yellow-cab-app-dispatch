"""Daily weather at the one Open-Meteo point, local days, over the Phase-3 calibration and
monitoring window -> results/weather_daily.csv.

Read from the warehouse view `int_weather_selected` (hourly, de-duplicated across the overlapping
download files) so that later steps (the 2026 alarm / storm check of
`scripts/23_presentation_numbers.py`, run by `make figures`) read results/ only.
"""

from __future__ import annotations

import logging

from taxi_shock.config import load_config, path
from taxi_shock.io import connect


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    lo, hi = cfg["shock"]["calibration_period"][0], cfg["shock"]["forecast_window"][1]
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        wx = con.execute(
            "select cast(timezone(?, to_timestamp(unix_time)) as date) as day, "
            # rounded: DuckDB's parallel float sums differ in the last bits between runs
            "round(sum(snowfall), 3) as snowfall_in, round(sum(precipitation), 3) as precip_in, "
            "min(temperature_2m) as temp_min_f, max(temperature_2m) as temp_max_f, "
            "count(*) as n_hours from int_weather_selected group by 1 "
            "having day between ? and ? order by 1", [cfg["timezone"], lo, hi]).df()
    out = path("results", cfg) / "weather_daily.csv"
    wx.to_csv(out, index=False, lineterminator="\n")
    logging.info("wrote %s (%d days)", out.name, len(wx))


if __name__ == "__main__":
    main()
