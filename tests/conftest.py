from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi_shock.config import load_config, path


@pytest.fixture
def synthetic_panel() -> pd.DataFrame:
    """3 zones x 6 weeks of hourly Poisson counts with a daily + weekly pattern."""
    rng = np.random.default_rng(0)
    hours = pd.date_range("2024-01-01", periods=24 * 7 * 6, freq="h")
    frames = []
    for z, base in [(1, 2.0), (2, 20.0), (3, 80.0)]:
        daily = 1.5 + np.sin(2 * np.pi * hours.hour / 24)
        lam = base * daily * (1 + 0.3 * (hours.day_of_week < 5))
        frames.append(pd.DataFrame({"zone_id": z, "hour_ts": hours,
                                    "pickups": rng.poisson(lam).astype("float32")}))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def smoke_db():
    db = path("smoke_warehouse", load_config())
    if not db.exists():
        pytest.skip("smoke warehouse not built (run `make smoke`)")
    return db
