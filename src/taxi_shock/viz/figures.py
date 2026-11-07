"""Figure builders, one function per figure (F1-F7 are added in their phases).

Titles state a finding only once the results support it; placeholder titles say what is shown.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from taxi_shock.viz.style import PALETTE, SIZES, direct_labels, policy_line, save, use_style


def smoke_placeholder(fc: pd.DataFrame, out_base: Path) -> list[Path]:
    """Phase-0 placeholder: citywide hourly pickups vs the seasonal-naive forecast and 80% band.

    `fc` is the backtest forecast table (zone_id, target_ts, y, point, q10, q90).
    """
    use_style()
    city = fc.groupby("target_ts")[["y", "point", "q10", "q90"]].sum(min_count=1).reset_index()
    fig, ax = plt.subplots(figsize=SIZES["single"])
    ax.fill_between(city["target_ts"], city["q10"], city["q90"], color=PALETTE["baseline"],
                    alpha=0.35, linewidth=0, label="80% interval (sum of zone quantiles)")
    ax.plot(city["target_ts"], city["point"], color=PALETTE["muted_text"], linewidth=1.0)
    ax.plot(city["target_ts"], city["y"], color=PALETTE["actual"], linewidth=1.1)
    ax.set_ylabel("Yellow-taxi pickups per hour (all zones)")
    ax.set_xlabel("Local time (America/New_York)")
    ax.set_xlim(city["target_ts"].min(), city["target_ts"].max())
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.set_ylim(bottom=0)
    last = city.iloc[-1]
    x_lab = last["target_ts"] + pd.Timedelta(hours=3)
    direct_labels(ax, x_lab, [(last["y"], "actual", PALETTE["actual"]),
                              (last["point"], "seasonal naive", PALETTE["muted_text"])])
    lo, hi = city["target_ts"].min().date(), city["target_ts"].max().date()
    ax.set_title(f"Smoke test: day-ahead seasonal-naive forecast, {lo} to {hi}")
    ax.text(0.0, -0.2, "Placeholder figure from the one-month smoke pipeline; band = sum of "
            "per-zone q10/q90, not a calibrated citywide interval.",
            transform=ax.transAxes, fontsize=8, color=PALETTE["muted_text"])
    policy_line(ax)
    return save(fig, out_base)


def f1_demand_map(zones, summary: pd.DataFrame, title: str, out_base: Path) -> list[Path]:
    """F1: log pickups per zone in 2024, CBD boundary drawn; inset zooms on Manhattan.

    `zones` = maps.load_zones(...); `summary` = results/zone_summary.csv.
    """
    from taxi_shock.viz.maps import bounds_of, draw_boundary, log_choropleth

    use_style()
    values = summary.set_index("zone_id")["pickups_2024"]
    cbd_ids = summary.loc[summary["is_cbd"], "zone_id"].tolist()
    fig, ax = plt.subplots(figsize=SIZES["map"])
    log_choropleth(ax, zones, values, "Yellow-taxi pickups in 2024 (log scale)")
    draw_boundary(ax, zones, cbd_ids)
    ins = ax.inset_axes([0.0, 0.52, 0.42, 0.46])
    log_choropleth(ins, zones, values, "")
    ins.figure.axes[-1].remove()  # one colour bar is enough
    draw_boundary(ins, zones, cbd_ids)
    man = summary.loc[summary["borough"] == "Manhattan", "zone_id"].tolist()
    b = bounds_of(zones, man, pad=0.02)
    ins.set_xlim(b[0], b[2])
    ins.set_ylim(b[1], b[1] + (b[3] - b[1]) * 0.55)
    ins.set_axis_on()
    ins.set_xticks([])
    ins.set_yticks([])
    ins.set_xlabel("")
    ins.set_ylabel("")
    ins.grid(False)
    for sp in ins.spines.values():
        sp.set_visible(True)
        sp.set_color(PALETTE["muted_text"])
        sp.set_linewidth(0.6)
    ins.text(0.03, 0.03, "Inset: CBD and neighbours, enlarged",
             transform=ins.transAxes, fontsize=8,
             color=PALETTE["text"], va="bottom",
             bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})
    ax.set_title(title)
    ax.text(0.0, -0.02, "Red outline: the CBD zones (config/zones_cbd.csv). Hatched grey: no "
            "pickups in 2024. Zones: TLC taxi zones.", transform=ax.transAxes, fontsize=8,
            color=PALETTE["muted_text"], va="top")
    return save(fig, out_base)


def f1b_citywide_weekly(weekly: pd.DataFrame, covid_date: str, title: str,
                        out_base: Path) -> list[Path]:
    """F1b: citywide weekly yellow-taxi pickups (complete weeks only), COVID and policy marked.

    `weekly` = results/citywide_weekly.csv.
    """
    use_style()
    w = weekly[weekly["complete_week"]].copy()
    w["week_start"] = pd.to_datetime(w["week_start"])
    fig, ax = plt.subplots(figsize=SIZES["single"])
    ax.plot(w["week_start"], w["pickups"] / 1e6, color=PALETTE["actual"], linewidth=1.2)
    ax.set_ylabel("Pickups per week (millions)")
    ax.set_xlabel("Week (starting Sunday)")
    ax.set_ylim(bottom=0)
    ax.set_xlim(w["week_start"].min(), w["week_start"].max() + pd.Timedelta(days=7))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    c = mdates.date2num(pd.Timestamp(covid_date))
    ax.axvline(c, color=PALETTE["muted_text"], linestyle=":", linewidth=1.0)
    ax.annotate(f"NY PAUSE {covid_date}", xy=(c, 0.55), xycoords=("data", "axes fraction"),
                xytext=(4, 0), textcoords="offset points", fontsize=8.5,
                color=PALETTE["muted_text"], va="center")
    policy_line(ax)
    ax.set_title(title)
    return save(fig, out_base)
