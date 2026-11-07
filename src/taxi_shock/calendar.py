"""New York holiday calendar for the feature table (PLAN Phase 1: `holidays.US(state='NY')`).

The dates are written to the dbt seed `dbt/seeds/holidays_ny.csv` so that dbt can join them;
`tests/test_holidays_seed.py` fails if the committed seed drifts from the library output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import holidays
import pandas as pd

from taxi_shock.config import load_config, path


def seed_years(cfg: dict[str, Any]) -> list[int]:
    lo, hi = cfg["data"]["yellow_months"]
    return list(range(int(lo[:4]), int(hi[:4]) + 1))


def ny_holidays(years: list[int]) -> pd.DataFrame:
    """One row per (date, name); observed dates are included as the library reports them."""
    cal = holidays.US(subdiv="NY", years=years)  # = PLAN's state="NY" (deprecated alias)
    rows = [{"date": d.isoformat(), "name": n} for d, names in sorted(cal.items())
            for n in names.split("; ")]
    return pd.DataFrame(rows, columns=["date", "name"])


def write_holiday_seed(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    out = path("holidays_seed", cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    ny_holidays(seed_years(cfg)).to_csv(out, index=False, lineterminator="\n")
    return out


if __name__ == "__main__":
    print(write_holiday_seed())
