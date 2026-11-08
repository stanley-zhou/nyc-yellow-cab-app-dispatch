"""Weekly / daily zone panels for the DiD design (Phase 4).

`control_zone_ids` resolves a named control group from `causal.control_groups` in config. The
primary control (`causal.control`) is the "donut": Manhattan non-CBD zones without the six zones
that straddle the 60th St line (Stanley, 2026-11-07; evidence: results/cbd_validation_trips.json).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def control_zone_ids(
    zones: pd.DataFrame, cfg: dict[str, Any], name: str | None = None
) -> list[int]:
    """Zone ids of control group `name` (default: the primary `causal.control`).

    `zones` needs columns zone_id, borough, zone_group, is_airport (dim_zones /
    results/zone_summary.csv). A definition selects by `zone_groups` or by `boroughs`
    (optionally `exclude_airports`), then removes `exclude_zones`. CBD zones are never controls.
    """
    name = name or cfg["causal"]["control"]
    spec = cfg["causal"]["control_groups"][name]
    keep = pd.Series(True, index=zones.index)
    if "zone_groups" in spec:
        keep &= zones["zone_group"].isin(spec["zone_groups"])
    if "boroughs" in spec:
        keep &= zones["borough"].isin(spec["boroughs"])
    if spec.get("exclude_airports"):
        keep &= ~zones["is_airport"].astype(bool)
    keep &= ~zones["zone_id"].isin(spec.get("exclude_zones", []))
    keep &= zones["zone_group"] != "cbd"
    return sorted(int(z) for z in zones.loc[keep, "zone_id"])
