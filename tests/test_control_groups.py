"""Control-group definitions (PLAN Amendments, human-approved 2026-11-07)."""

import pandas as pd

from taxi_shock.causal.panel import control_zone_ids
from taxi_shock.config import load_config, path

CFG = load_config()
DONUT_OUT = {43, 140, 141, 142, 143, 237}


def _zones() -> pd.DataFrame:
    return pd.read_csv(path("results", CFG) / "zone_summary.csv")


def test_primary_control_is_the_donut():
    z = _zones()
    full = set(control_zone_ids(z, CFG, "manhattan_non_cbd"))
    donut = set(control_zone_ids(z, CFG))
    assert CFG["causal"]["control"] == "manhattan_non_cbd_donut"
    assert full - donut == DONUT_OUT
    assert 202 in donut                      # Roosevelt Island stays (straight-line artefact)
    assert full == set(z.loc[z["zone_group"] == "manhattan_non_cbd", "zone_id"])


def test_controls_never_contain_cbd_or_airports():
    z = _zones()
    cbd = set(z.loc[z["is_cbd"], "zone_id"])
    for name in CFG["causal"]["control_groups"]:
        ids = set(control_zone_ids(z, CFG, name))
        assert ids and not ids & cbd, name
    outer = control_zone_ids(z, CFG, "outer_boroughs")
    sub = z[z["zone_id"].isin(outer)]
    assert set(sub["borough"]) == {"Brooklyn", "Queens"} and not sub["is_airport"].any()


def test_robustness_controls_are_defined():
    for name in [CFG["causal"]["control"], *CFG["causal"]["control_robustness"]]:
        assert name in CFG["causal"]["control_groups"]
