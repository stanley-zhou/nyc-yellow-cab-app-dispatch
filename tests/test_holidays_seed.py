"""The committed dbt seed must equal what `holidays.US(state='NY')` returns for the data years."""

import pandas as pd

from taxi_shock.calendar import ny_holidays, seed_years
from taxi_shock.config import load_config, path


def test_holiday_seed_in_sync():
    cfg = load_config()
    committed = pd.read_csv(path("holidays_seed", cfg), dtype=str)
    fresh = ny_holidays(seed_years(cfg)).astype(str)
    pd.testing.assert_frame_equal(committed.reset_index(drop=True), fresh.reset_index(drop=True))
