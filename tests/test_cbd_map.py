"""CBD mapping: geometric rule unit tests + geometric-vs-fee agreement (PLAN Phase 1)."""

import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from taxi_shock.cbd import fee_labels, resolve, south_of_line
from taxi_shock.config import load_config, path

CFG = load_config()
# A synthetic west->east line (not the real one) so the unit tests do not depend on OSM data.
LINE = {"west_endpoint": {"lon": -73.99, "lat": 40.77}, "east_endpoint": {"lon": -73.96,
                                                                          "lat": 40.76}}


def _pts(lonlat):
    return gpd.GeoSeries([Point(x, y) for x, y in lonlat], crs="EPSG:4326").to_crs("EPSG:2263")


def test_south_of_line_sides():
    # Battery Park (far south), Central Park North (far north)
    s = south_of_line(_pts([(-74.0170, 40.7033), (-73.9550, 40.7990)]), LINE)
    assert s.tolist() == [True, False]


def _toy(geo_cbd, share, n=1000):
    zones = pd.DataFrame({"zone_id": [1], "zone_name": ["z"], "borough": ["Manhattan"]})
    geo = pd.DataFrame({"zone_id": [1], "geometric_is_cbd": [geo_cbd],
                        "geometry_available": [True]})
    fee = pd.DataFrame({"zone_id": [1], "n_trips": [n], "n_fee_pos": [int(share * n)],
                        "n_fee_null": [0], "n_intra": [10], "n_intra_fee_pos": [5]})
    return zones, geo, fee


def test_resolve_raises_on_unresolved_disagreement():
    with pytest.raises(ValueError, match="manual_overrides"):
        resolve(*_toy(False, 0.95), {**CFG["cbd"], "manual_overrides": {}})


def test_resolve_override_and_agreement():
    df, s = resolve(*_toy(False, 0.95), {**CFG["cbd"], "manual_overrides": {
        1: {"is_cbd": True, "reason": "test"}}})
    assert df["is_cbd"].tolist() == [True] and s["manual_overrides_applied"] == [1]
    df, s = resolve(*_toy(True, 0.99), {**CFG["cbd"], "manual_overrides": {}})
    assert df["is_cbd"].tolist() == [True] and s["n_manhattan_decisive_agree"] == 1


def test_fee_label_thresholds():
    fee = pd.DataFrame({"zone_id": [1, 2, 3, 4], "n_trips": [1000, 1000, 1000, 5],
                        "n_fee_pos": [900, 100, 500, 5], "n_fee_null": 0, "n_intra": 0,
                        "n_intra_fee_pos": 0})
    assert fee_labels(fee, CFG["cbd"])["fee_label"].tolist() == [
        "cbd", "not_cbd", "ambiguous", "insufficient"]


def test_committed_mapping_meets_agreement_threshold():
    """config/zones_cbd.csv + results/cbd_validation.json (written by scripts/03a_cbd_map.py)."""
    summary = json.loads((path("results", CFG) / "cbd_validation.json").read_text())
    mapping = pd.read_csv(path("zones_cbd", CFG))
    assert len(mapping) == summary["n_zones"] == 263
    man = mapping[mapping["borough"] == "Manhattan"]
    assert man["is_cbd"].notna().all()
    # PLAN: geometric vs fee-based agreement >= 95%, evaluated on the Manhattan zones to which the
    # fee rule assigns a label (> 0.8 cbd / < 0.2 not_cbd). Zones in the ambiguous band are not
    # disagreements; their count and the all-Manhattan share are reported in cbd_validation.json
    # (DECISIONS.md, Phase 1).
    assert summary["agreement_share_of_decisive"] >= CFG["cbd"]["agreement_min"]
    assert summary["disagreements"] == []
    # the supplementary intra-zone signal must not contradict the geometric rule either
    intra = summary["intra_zone_signal"]
    assert intra["agreement_share_of_decisive"] >= CFG["cbd"]["agreement_min"]
    assert summary["final_mapping_agrees_with_every_decisive_fee_label"]
    assert not mapping.loc[mapping["borough"] != "Manhattan", "is_cbd"].any()
    for z, ov in CFG["cbd"].get("manual_overrides", {}).items():
        row = mapping.loc[mapping["zone_id"] == int(z)].iloc[0]
        assert bool(row["is_cbd"]) == ov["is_cbd"] and row["source"].startswith("manual override")
