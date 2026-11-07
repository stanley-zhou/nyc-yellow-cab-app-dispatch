"""`is_cbd` per TLC zone, derived in two documented steps (PLAN Phase 1).

(a) Geometric: a Manhattan zone is CBD if its centroid lies south of the straight line through the
    two endpoints of 60th Street (the westernmost and easternmost OpenStreetMap nodes of "West 60th
    Street" / "East 60th Street"). Geometry is handled in the shapefile's planar CRS (EPSG:2263,
    US feet), so "south of the line" is the right-hand side when walking from the west endpoint to
    the east endpoint.
(b) Validation from data: per pickup zone, the share of valid trips in `cbd.fee_window` that carry
    `cbd_congestion_fee > 0`; share > `fee_share_cbd_min` -> "cbd", < `fee_share_not_cbd_max` ->
    "not_cbd", otherwise "ambiguous"; fewer than `fee_min_trips` trips -> "insufficient".

Final rule: the geometric label, unless it disagrees with a decisive fee label; a disagreement
must be resolved by an explicit entry in `cbd.manual_overrides` (config), otherwise this module
raises. Non-Manhattan zones are never CBD (the zone lies outside Manhattan); a decisive "cbd" fee
label outside Manhattan is reported as a data surprise.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from pyproj import Transformer

PLANAR_CRS = "EPSG:2263"


def sixtieth_street_line(osm_json: Path, street_names: list[str]) -> dict[str, Any]:
    """Endpoints of 60th St from the raw Overpass response: westernmost and easternmost nodes."""
    payload = json.loads(osm_json.read_text(encoding="utf-8"))
    nodes = []
    for el in payload["elements"]:
        if el.get("type") != "way" or el.get("tags", {}).get("name") not in street_names:
            continue
        nodes += [(pt["lon"], pt["lat"], el["id"]) for pt in el["geometry"]]
    if not nodes:
        raise ValueError(f"no OSM ways named {street_names} in {osm_json}")
    west = min(nodes, key=lambda n: n[0])
    east = max(nodes, key=lambda n: n[0])
    return {
        "source": "OpenStreetMap via Overpass API (ODbL)",
        "retrieved": payload.get("retrieved"),
        "query": payload.get("query"),
        "n_ways": len({n[2] for n in nodes}),
        "west_endpoint": {"lon": west[0], "lat": west[1], "osm_way_id": west[2]},
        "east_endpoint": {"lon": east[0], "lat": east[1], "osm_way_id": east[2]},
    }


def south_of_line(points: gpd.GeoSeries, line: dict[str, Any]) -> pd.Series:
    """True where a point (in PLANAR_CRS) lies strictly south of the west->east 60th St line."""
    to_planar = Transformer.from_crs("EPSG:4326", PLANAR_CRS, always_xy=True)
    wx, wy = to_planar.transform(line["west_endpoint"]["lon"], line["west_endpoint"]["lat"])
    ex, ey = to_planar.transform(line["east_endpoint"]["lon"], line["east_endpoint"]["lat"])
    dx, dy = ex - wx, ey - wy
    # cross((E - W), (P - W)) < 0  <=>  P is right of the west->east direction, i.e. south
    cross = dx * (points.y - wy) - dy * (points.x - wx)
    return pd.Series(cross < 0, index=points.index)


def geometric_labels(shapefile: Path, line: dict[str, Any]) -> pd.DataFrame:
    """zone_id, borough, centroid (lon/lat), geometric_is_cbd (Manhattan only), geometry flag."""
    zones = gpd.read_file(shapefile).to_crs(PLANAR_CRS)
    zones = zones.dissolve(by="LocationID", as_index=False, aggfunc="first")
    cent = zones.geometry.centroid
    cent_ll = gpd.GeoSeries(cent, crs=PLANAR_CRS).to_crs("EPSG:4326")
    south = south_of_line(cent, line)
    manhattan = zones["borough"].eq("Manhattan")
    return pd.DataFrame({
        "zone_id": zones["LocationID"].astype(int),
        "shape_borough": zones["borough"],
        "centroid_lon": cent_ll.x.round(6),
        "centroid_lat": cent_ll.y.round(6),
        "geometric_is_cbd": (south & manhattan).to_numpy(),
        "geometry_available": ~zones.geometry.is_empty & zones.geometry.notna(),
    })


def fee_labels(fee: pd.DataFrame, cbd_cfg: dict[str, Any]) -> pd.DataFrame:
    """Add fee_share, fee_label and intra-zone share to the per-zone fee counts."""
    out = fee.copy()
    out["fee_share"] = out["n_fee_pos"] / out["n_trips"]
    out["intra_fee_share"] = (out["n_intra_fee_pos"] / out["n_intra"]).where(out["n_intra"] > 0)
    hi, lo, n_min = (float(cbd_cfg["fee_share_cbd_min"]), float(cbd_cfg["fee_share_not_cbd_max"]),
                     int(cbd_cfg["fee_min_trips"]))
    label = pd.Series("ambiguous", index=out.index)
    label[out["fee_share"] > hi] = "cbd"
    label[out["fee_share"] < lo] = "not_cbd"
    label[out["n_trips"] < n_min] = "insufficient"
    out["fee_label"] = label
    # supplementary signal: the same thresholds on intra-zone trips (pickup zone = dropoff zone)
    intra = pd.Series("ambiguous", index=out.index)
    intra[out["intra_fee_share"] > hi] = "cbd"
    intra[out["intra_fee_share"] < lo] = "not_cbd"
    intra[out["n_intra"] < n_min] = "insufficient"
    out["intra_fee_label"] = intra
    return out


def resolve(zones: pd.DataFrame, geo: pd.DataFrame, fee: pd.DataFrame,
            cbd_cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Combine lookup zones, geometric and fee labels into the final mapping + a summary."""
    df = zones.merge(geo, on="zone_id", how="left").merge(
        fee_labels(fee, cbd_cfg), on="zone_id", how="left")
    df["fee_label"] = df["fee_label"].fillna("insufficient")
    df["intra_fee_label"] = df["intra_fee_label"].fillna("insufficient")
    for c in ("n_trips", "n_fee_pos", "n_intra", "n_intra_fee_pos"):
        df[c] = df[c].fillna(0).astype(int)
    df["geometry_available"] = df["geometry_available"].fillna(False).astype(bool)
    overrides = {int(k): v for k, v in (cbd_cfg.get("manual_overrides") or {}).items()}

    is_cbd, source = [], []
    for r in df.itertuples():
        if r.borough != "Manhattan":
            is_cbd.append(False)
            source.append("not Manhattan")
            continue
        geo_cbd = bool(r.geometric_is_cbd)
        decisive = r.fee_label in ("cbd", "not_cbd")
        agree = (r.fee_label == "cbd") == geo_cbd
        if r.zone_id in overrides:
            is_cbd.append(bool(overrides[r.zone_id]["is_cbd"]))
            source.append("manual override: " + overrides[r.zone_id]["reason"])
        elif decisive and not agree:
            raise ValueError(
                f"zone {r.zone_id} ({r.zone_name}): geometric={geo_cbd} but fee label "
                f"{r.fee_label} (share {r.fee_share:.3f}); add cbd.manual_overrides in config")
        elif decisive:
            is_cbd.append(geo_cbd)
            source.append(f"geometric, confirmed by fee share {r.fee_share:.3f}")
        else:
            is_cbd.append(geo_cbd)
            share = "n/a" if pd.isna(r.fee_share) else f"{r.fee_share:.3f}"
            source.append(f"geometric; fee label {r.fee_label} (share {share}, "
                          f"{r.n_trips} trips)")
    df["is_cbd"] = is_cbd
    df["source"] = source

    man = df[df["borough"] == "Manhattan"]
    dec = man[man["fee_label"].isin(["cbd", "not_cbd"])]
    agree_mask = (dec["fee_label"] == "cbd") == dec["geometric_is_cbd"].astype(bool)
    # agreement of the geometric rule with the intra-zone signal (supplementary)
    idec = man[man["intra_fee_label"].isin(["cbd", "not_cbd"])]
    iagree = (idec["intra_fee_label"] == "cbd") == idec["geometric_is_cbd"].astype(bool)
    # agreement of the FINAL mapping (after manual overrides) with each decisive signal
    final_agree = ((dec["fee_label"] == "cbd") == dec["is_cbd"]).all()
    surprises = df[(df["borough"] != "Manhattan") & (df["fee_label"] == "cbd")]
    cbd_rows = df[df["is_cbd"]]
    lowest = cbd_rows.loc[cbd_rows["fee_share"].idxmin()] if cbd_rows["fee_share"].notna().any() \
        else None
    summary = {
        "n_zones": int(len(df)),
        # every final CBD zone, including those along the FDR Drive and the West Side Highway
        # (which the Congestion Relief Zone excludes as through-routes), and its fee share
        "cbd_zones_min_fee_share": (None if lowest is None else
                                    {"zone_id": int(lowest["zone_id"]),
                                     "zone_name": lowest["zone_name"],
                                     "fee_share": round(float(lowest["fee_share"]), 4)}),
        "cbd_zones_fee_labels": {k: int(v) for k, v in
                                 cbd_rows["fee_label"].value_counts().items()},
        "n_manhattan": int(len(man)),
        "n_cbd_final": int(df["is_cbd"].sum()),
        "n_cbd_geometric": int(man["geometric_is_cbd"].astype(bool).sum()),
        "manhattan_fee_labels": {k: int(v) for k, v in man["fee_label"].value_counts().items()},
        "n_manhattan_decisive": int(len(dec)),
        "n_manhattan_decisive_agree": int(agree_mask.sum()),
        "agreement_share_of_decisive": (round(float(agree_mask.mean()), 4) if len(dec) else None),
        "agreement_share_of_all_manhattan": round(float(agree_mask.sum()) / len(man), 4),
        "disagreements": dec.loc[~agree_mask, ["zone_id", "zone_name", "fee_share",
                                                "geometric_is_cbd"]].to_dict("records"),
        "final_mapping_agrees_with_every_decisive_fee_label": bool(final_agree),
        "intra_zone_signal": {
            "manhattan_labels": {k: int(v) for k, v in
                                 man["intra_fee_label"].value_counts().items()},
            "n_decisive": int(len(idec)),
            "n_decisive_agree": int(iagree.sum()),
            "agreement_share_of_decisive": (round(float(iagree.mean()), 4)
                                            if len(idec) else None),
            "disagreements": idec.loc[~iagree, ["zone_id", "zone_name", "intra_fee_share",
                                                "geometric_is_cbd"]].to_dict("records"),
        },
        "manual_overrides_applied": sorted(z for z in overrides if z in set(man["zone_id"])),
        "non_manhattan_with_cbd_fee_label": surprises[["zone_id", "zone_name", "borough",
                                                       "fee_share"]].to_dict("records"),
        "cbd_zones": df.loc[df["is_cbd"], ["zone_id", "zone_name"]].to_dict("records"),
        "ambiguous_or_insufficient_manhattan": man.loc[
            ~man["fee_label"].isin(["cbd", "not_cbd"]),
            ["zone_id", "zone_name", "fee_label", "fee_share", "intra_fee_label",
             "intra_fee_share", "n_trips", "geometric_is_cbd"]].to_dict("records"),
    }
    return df, summary
