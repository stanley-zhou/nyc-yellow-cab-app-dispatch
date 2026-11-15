"""Zone choropleths (Phase 1; Phase 4 adds the diverging effect map).

`load_zones` reads the TLC zone shapefile; the other helpers draw on a matplotlib Axes or return
map bounds."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from taxi_shock.viz.style import PALETTE, SEQUENTIAL_CMAP

NO_DATA_COLOR = "#B9BDC4"   # mid grey + hatch: never confused with the lightest blue


def load_zones(shapefile: Path) -> gpd.GeoDataFrame:
    """TLC zone polygons (one row per LocationID) in their planar CRS (EPSG:2263)."""
    z = gpd.read_file(shapefile).dissolve(by="LocationID", as_index=False, aggfunc="first")
    return z.rename(columns={"LocationID": "zone_id"})[["zone_id", "geometry"]]


def log_choropleth(ax: Axes, zones: gpd.GeoDataFrame, values: pd.Series,
                   label: str) -> mpl.colorbar.Colorbar:
    """Sequential single-hue choropleth on a log10 colour scale; zeros drawn as 'no pickups'."""
    gdf = zones.merge(values.rename("v"), left_on="zone_id", right_index=True, how="left")
    pos = gdf[gdf["v"] > 0]
    vmin, vmax = float(pos["v"].min()), float(pos["v"].max())
    norm = mpl.colors.LogNorm(vmin=vmin, vmax=vmax)
    gdf[~(gdf["v"] > 0)].plot(ax=ax, facecolor=NO_DATA_COLOR, edgecolor="white", hatch="////",
                              linewidth=0.25)
    pos.plot(ax=ax, column="v", cmap=SEQUENTIAL_CMAP, norm=norm, edgecolor="white",
             linewidth=0.25)
    sm = mpl.cm.ScalarMappable(norm=norm, cmap=SEQUENTIAL_CMAP)
    cb = ax.figure.colorbar(sm, ax=ax, fraction=0.035, pad=0.01, shrink=0.6)
    cb.set_label(label)
    cb.outline.set_visible(False)
    ax.set_axis_off()
    ax.set_aspect("equal")
    return cb


def draw_boundary(ax: Axes, zones: gpd.GeoDataFrame, zone_ids: list[int],
                  color: str = PALETTE["cbd"], close_gaps_ft: float = 60.0) -> None:
    """Exterior outline of the union of `zone_ids` (e.g. the CBD zones).

    TLC polygons leave hairline slivers between neighbours; a buffer out and back in by
    `close_gaps_ft` (CRS units, feet in EPSG:2263) closes them, and only exterior rings are drawn,
    so the outline shows the area's edge rather than internal sliver boundaries."""
    union = zones[zones["zone_id"].isin(zone_ids)].union_all()
    union = union.buffer(close_gaps_ft).buffer(-close_gaps_ft)
    polys = getattr(union, "geoms", [union])
    rings = [p.exterior for p in polys if p.area > 0]
    gpd.GeoSeries(rings, crs=zones.crs).plot(ax=ax, color=color, linewidth=1.6)


def bounds_of(zones: gpd.GeoDataFrame, zone_ids: list[int], pad: float = 0.05) -> np.ndarray:
    b = zones[zones["zone_id"].isin(zone_ids)].total_bounds
    dx, dy = b[2] - b[0], b[3] - b[1]
    return np.array([b[0] - pad * dx, b[1] - pad * dy, b[2] + pad * dx, b[3] + pad * dy])
