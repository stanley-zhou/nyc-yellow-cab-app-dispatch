"""Figure builders, one function per figure (F1-F7 are added in their phases).

Titles state a finding only once the results support it; placeholder titles say what is shown.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from taxi_shock.viz.style import (
    DIVERGING_CMAP,
    PALETTE,
    SEQUENTIAL_CMAP,
    SIZES,
    direct_labels,
    policy_line,
    save,
    tint,
    use_style,
)


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


# Fixed categorical order for VendorID (first slots of the dataviz reference palette, documented
# there as validated for colour-vision deficiency); colour follows the vendor, never its rank.
VENDOR_COLORS: dict[str, str] = {
    "1": "#2a78d6", "2": "#eb6834", "6": "#1baf7a", "7": "#eda100", "null": "#e87ba4",
}


def f1c_vendor_weekly(series: pd.DataFrame, title: str, out_base: Path) -> list[Path]:
    """F1c (Checkpoint 1 check): weekly valid pickups by VendorID, CBD vs non-CBD pickup zones,
    complete weeks only, all vendors as a thin near-black line, log y-scale (Helix and Myle are
    orders of magnitude smaller than Curb). Two panels with their own y-scale (small multiples,
    not a dual axis).

    `series` = results/vendor_series.csv.
    """
    use_style()
    s = series[series["complete_week"]].copy()
    s["week_start"] = pd.to_datetime(s["week_start"])
    s["vendor_key"] = s["vendor_id"].astype("string").fillna("null")
    fig, axes = plt.subplots(2, 1, figsize=SIZES["small_multiples"], sharex=True)
    x_end = s["week_start"].max()
    for ax, area, label in zip(axes, ["cbd", "non_cbd"],
                               ["Pickups in CBD zones", "Pickups in all other zones"],
                               strict=True):
        a = s[s["area"] == area]
        wide = a.pivot_table(index="week_start", columns="vendor_key", values="pickups",
                             aggfunc="sum", fill_value=0)
        total = wide.sum(axis=1)
        ax.plot(total.index, total / 1e3, color=PALETTE["actual"], linewidth=1.0)
        ends = [(total.iloc[-1] / 1e3, "all vendors", PALETTE["actual"])]
        for key in sorted(wide.columns, key=lambda k: (k == "null", k.zfill(3))):
            name = a.loc[a["vendor_key"] == key, "vendor_name"].iloc[0]
            col = VENDOR_COLORS.get(key, PALETTE["muted_text"])
            ax.plot(wide.index, wide[key] / 1e3, color=col, linewidth=1.4,
                    label=f"{key}: {name}" if key != "null" else name)
            ends.append((wide[key].iloc[-1] / 1e3, name.split()[0], col))
        ax.set_yscale("log")   # vendors differ by >3 orders of magnitude; log keeps all visible
        ax.set_ylim(5e-3, total.max() / 1e3 * 40)   # headroom for the legend and policy label
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.set_xlim(s["week_start"].min(), x_end)
        ax.set_ylabel(f"{label}\n(thousands per week, log scale)")
        policy_line(ax, label=ax is axes[0])
        _log_end_labels(ax, x_end + pd.Timedelta(days=10), ends)
    axes[0].legend(loc="upper left", fontsize=8, frameon=False, ncol=4,
                   title="VendorID (TLC data dictionary 2025-03-18)", title_fontsize=8,
                   alignment="left")
    axes[1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[1].set_xlabel("Week (starting Sunday); complete weeks only")
    axes[0].set_title(title)
    return save(fig, out_base)


def _log_end_labels(ax, x, items: list[tuple[float, str, str]], min_gap_dec: float = 0.32) -> None:
    """End-of-line labels on a log axis, pushed apart by `min_gap_dec` decades; text in ink."""
    import numpy as np

    placed: list[float] = []
    for y, text, _ in sorted(items, key=lambda t: t[0]):
        ly = np.log10(max(y, 1e-9))
        ly = max(ly, placed[-1] + min_gap_dec) if placed else ly
        placed.append(ly)
        ax.annotate(text, xy=(x, 10 ** ly), va="center", ha="left", fontsize=9,
                    color=PALETTE["text"], annotation_clip=False)


# F2 colours: baselines in greys (PALETTE baseline, muted), the trained ML model in the project's
# model accent, Chronos-2 in the next categorical hue (orange) with a lighter tint for the variant
# that also sees observed weather over the target day.
MODEL_STYLE: dict[str, tuple[str, str]] = {
    "seasonal_naive": ("Seasonal naive (lag 168 h)", PALETTE["baseline"]),
    "stat_ets_profile": ("AutoETS daily x hourly profile", PALETTE["muted_text"]),
    "lgbm_quantile": ("Global LightGBM quantile", PALETTE["model"]),
    "chronos2_weather_past": ("Chronos-2 zero-shot (weather as past covariate)",
                              PALETTE["foundation"]),
    "chronos2_weather_future": ("Chronos-2 zero-shot (weather also over target day)",
                                tint(PALETTE["foundation"], 0.45)),
}
GROUP_LABELS: dict[str, str] = {"all": "All modeled\nzones", "cbd": "CBD",
                                "manhattan_non_cbd": "Manhattan\nnon-CBD",
                                "airports": "Airports", "other": "Other\nzones"}


def f2_model_comparison(wape: pd.DataFrame, title: str, note: str, out_base: Path) -> list[Path]:
    """F2: WAPE (2024 test year, day-ahead) by model and zone group; one panel per group, each
    with its own x-scale (the comparison is between models within a group).

    `wape` columns: model, zone_group, value (raw forecasts, primary window; Chronos zero-shot).
    """
    use_style()
    groups = [g for g in GROUP_LABELS if g in set(wape["zone_group"])]
    models = [m for m in MODEL_STYLE if m in set(wape["model"])]
    fig, axes = plt.subplots(1, len(groups), figsize=SIZES["small_multiples"], sharey=True,
                             layout="constrained")
    for ax, g in zip(axes, groups, strict=True):
        d = wape[wape["zone_group"] == g].set_index("model")["value"]
        vmax = float(d.max()) * 1.45   # each panel compares models within one zone group
        ys = range(len(models))[::-1]
        for y, m in zip(ys, models, strict=True):
            if m not in d:
                continue
            ax.barh(y, d[m], color=MODEL_STYLE[m][1], height=0.7, edgecolor="white",
                    linewidth=2)
            ax.annotate(f"{d[m]:.4f}", xy=(d[m], y), xytext=(3, 0), textcoords="offset points",
                        va="center", fontsize=8, color=PALETTE["text"])
        ax.set_title(GROUP_LABELS[g], fontsize=10)
        ax.set_xlim(0, vmax)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("WAPE")
    axes[0].set_yticks(list(range(len(models)))[::-1])
    axes[0].set_yticklabels([MODEL_STYLE[m][0] for m in models], fontsize=8.5)
    # wrapped so the title never widens the canvas beyond the panels (tight bounding box);
    # constrained layout places the title right above the panel titles and the note below
    fig.suptitle(textwrap.fill(title, 95), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 150), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f2b_fan_chart(fan: pd.DataFrame, zone_name: str, title: str, out_base: Path) -> list[Path]:
    """F2b: one CBD zone, one week: actual vs LGBM q10/q50/q90 (raw band shaded, conformal
    band as dashed edges). `fan` = results/fan_chart_f2b.csv rows of one model/window."""
    use_style()
    raw = fan[fan["calibration"] == "raw"].sort_values("target_ts")
    cal = fan[fan["calibration"] != "raw"].sort_values("target_ts")
    fig, ax = plt.subplots(figsize=SIZES["single"])
    ax.fill_between(raw["target_ts"], raw["q10"], raw["q90"], color=tint(PALETTE["model"], 0.7),
                    linewidth=0, label="80% interval (raw q10-q90)")
    if len(cal):
        for c in ("q10", "q90"):
            ax.plot(cal["target_ts"], cal[c], color=PALETTE["model"], linewidth=0.8,
                    linestyle="--", label="80% interval, rolling 12-week conformal" if c == "q10"
                    else None)
    ax.plot(raw["target_ts"], raw["q50"], color=PALETTE["model"], linewidth=1.6,
            label="LightGBM median (q50)")
    ax.plot(raw["target_ts"], raw["y"], color=PALETTE["actual"], linewidth=1.1,
            label="Actual pickups")
    ax.set_ylabel(f"Pickups per hour, {zone_name}")
    ax.set_xlabel("Local time (forecast issued 00:00 the same day)")
    top = float(pd.concat([raw[["q90", "y"]], cal[["q90"]]]).max().max())
    ax.set_ylim(0, top * 1.22)   # headroom so the legend never covers the data
    ax.set_xlim(raw["target_ts"].min(), raw["target_ts"].max())
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b"))
    ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    ax.set_title(textwrap.fill(title, 68), loc="left")
    return save(fig, out_base)


F3_GROUPS: dict[str, tuple[str, str]] = {"cbd": ("CBD", PALETTE["cbd"]),
                                         "non_cbd": ("Non-CBD", PALETTE["non_cbd"])}


def f3_error_over_time(errors: pd.DataFrame, policy_date: str, markers: list[tuple[str, str]],
                       title: str, note: str, out_base: Path) -> list[Path]:
    """F3: rolling 4-week WAPE (top) and actual vs forecast in % (bottom), CBD vs non-CBD.

    `errors`: rows of results/shock_errors.csv for one model/series and the rolling window
    (both panels are rolling 4-week values),
    columns date, zone_group, wape, log_actual_over_forecast. Pre-policy segments are drawn in
    a lighter tint of the series colour. `markers`: (date, label) of monitor alarms, drawn as
    dotted vertical lines. Two panels with their own y-axis (small multiples, not a dual axis).
    """
    use_style()
    fig, axes = plt.subplots(2, 1, figsize=SIZES["small_multiples"], sharex=True,
                             layout="constrained")
    p = pd.Timestamp(policy_date)
    panels = [("wape", "Rolling 4-week WAPE"),
              ("log_actual_over_forecast", "Actual vs forecast (%)")]
    for ax, (col, ylabel) in zip(axes, panels, strict=True):
        ends = []
        for g, (label, color) in F3_GROUPS.items():
            d = errors[errors["zone_group"] == g].sort_values("date")
            y = d[col] if col == "wape" else (np.exp(d[col]) - 1) * 100
            post = (d["date"] >= p).to_numpy()
            pre = ~post | (d["date"] == d["date"][post].min()).to_numpy()   # joins the segments
            ax.plot(d["date"][pre], y[pre], color=tint(color), linewidth=1.4)
            ax.plot(d["date"][post], y[post], color=color, linewidth=1.6)
            ends.append((float(y.iloc[-1]), label, color))
        if col != "wape":
            ax.axhline(0, color=PALETTE["muted_text"], linewidth=0.8)
        ax.set_ylabel(ylabel)
        ax.set_xlim(errors["date"].min(), errors["date"].max())
        direct_labels(ax, errors["date"].max(), ends)
        for date, mlabel in markers:
            x = mdates.date2num(pd.Timestamp(date))
            ax.axvline(x, color=PALETTE["cbd"], linestyle=":", linewidth=1.1, zorder=3)
            if ax is axes[0]:   # labels in the empty band above zero, clear of the lines
                ax.annotate(mlabel, xy=(x, 0.10), xycoords=("data", "axes fraction"),
                            xytext=(4, 0), textcoords="offset points", fontsize=8,
                            color=PALETTE["cbd"], va="center")
        policy_line(ax, label=ax is axes[0], label_y=0.24)
    axes[0].set_ylim(bottom=0)
    axes[1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    fig.suptitle(textwrap.fill(title, 95), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 150), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


# ------------------------------------------------------------------------------------ Phase 4
def _bin_dates(k: pd.Series, policy_date: str) -> pd.Series:
    """Mid-month date of monthly event-time bin k (0 = the policy month)."""
    p = pd.Timestamp(policy_date).to_period("M")
    return pd.Series([(p + int(x)).to_timestamp() + pd.Timedelta(days=14) for x in k],
                     index=k.index)


def _event_panel(ax, es: pd.DataFrame, policy_date: str, ylabel: str, color: str,
                 label_policy: bool = True, label_y: float = 1.0, shift_days: int = 0,
                 label: str | None = None, marker: str = "o") -> None:
    """Monthly coefficients as % effects (exp(b) - 1) with 95% CIs; pre bins tinted.
    `shift_days` offsets the points so two series in one panel do not overlap."""
    x = _bin_dates(es["k"], policy_date) + pd.Timedelta(days=shift_days)
    pct = {c: (np.exp(es[c]) - 1) * 100 for c in ("coef", "ci_lo", "ci_hi")}
    for pre, c in ((True, tint(color)), (False, color)):
        s = (es["k"] < 0) == pre
        ax.errorbar(x[s], pct["coef"][s],
                    yerr=[pct["coef"][s] - pct["ci_lo"][s], pct["ci_hi"][s] - pct["coef"][s]],
                    fmt=marker, ms=4, color=c, ecolor=c, elinewidth=1.0, capsize=0,
                    label=label if not pre else None)
    ax.axhline(0, color=PALETTE["muted_text"], linewidth=0.8)
    ax.set_ylabel(ylabel)
    ax.set_xlim(x.min() - pd.Timedelta(days=20), x.max() + pd.Timedelta(days=20))
    if label_policy is not None:
        policy_line(ax, label=label_policy, label_y=label_y)


def f4_event_study(es: pd.DataFrame, policy_date: str, title: str, note: str,
                   out_base: Path, ylabel: str) -> list[Path]:
    """F4: monthly event-study coefficients +- 95% CI, zero line, policy line, nothing else."""
    use_style()
    fig, ax = plt.subplots(figsize=SIZES["single"], layout="constrained")
    _event_panel(ax, es, policy_date, ylabel, PALETTE["cbd"])
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    fig.suptitle(textwrap.fill(title, 80), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 115), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f4f_speed_event_study(panels: list[tuple[str, list[tuple[str, pd.DataFrame, str]]]],
                          policy_date: str, title: str, note: str,
                          out_base: Path) -> list[Path]:
    """F4f (Amendment 2; C4): speed and duration event studies, one panel per outcome (own
    y-axis), one series per control group (offset by a few days, legend in the first panel).
    `panels`: (y label, [(series label, monthly event-study rows, colour), ...])."""
    use_style()
    fig, axes = plt.subplots(len(panels), 1, figsize=SIZES["small_multiples"], sharex=True,
                             layout="constrained")
    for i, (ax, (ylabel, series)) in enumerate(zip(axes, panels, strict=True)):
        for j, (label, es, color) in enumerate(series):
            _event_panel(ax, es, policy_date, ylabel, color, label_policy=i == 0 if j == 0
                         else None, label_y=0.12, shift_days=(j - (len(series) - 1) / 2) * 6,
                         label=label, marker="os^"[j % 3])
        if i == 0 and len(series) > 1:
            ax.legend(frameon=False, fontsize=8, loc="upper right")
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    fig.suptitle(textwrap.fill(title, 95), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 150), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f4b_effect_map(zones, effects: pd.DataFrame, title: str, note: str, out_base: Path,
                   min_pre_weekly: float, colour_quantile: float) -> list[Path]:
    """F4b: Manhattan zones, post/pre log change relative to the control aggregate (diverging,
    centred at 0); zones below `min_pre_weekly` pre-period pickups hatched; CBD outlined."""
    from taxi_shock.viz.maps import NO_DATA_COLOR, bounds_of, draw_boundary

    use_style()
    e = effects.set_index("zone_id")
    gdf = zones.merge(e, left_on="zone_id", right_index=True, how="inner")
    ok = gdf["pre_mean_weekly"] >= min_pre_weekly
    v = gdf.loc[ok, "relative_to_control_aggregate"]
    lim = float(np.nanquantile(np.abs(v), colour_quantile))
    norm = mpl.colors.TwoSlopeNorm(vcenter=0.0, vmin=-lim, vmax=lim)
    fig, ax = plt.subplots(figsize=SIZES["map"], layout="constrained")
    gdf[~ok].plot(ax=ax, facecolor=NO_DATA_COLOR, edgecolor="white", hatch="////",
                  linewidth=0.3)
    gdf[ok].plot(ax=ax, column="relative_to_control_aggregate", cmap=DIVERGING_CMAP, norm=norm,
                 edgecolor="white", linewidth=0.3)
    sm = mpl.cm.ScalarMappable(norm=norm, cmap=DIVERGING_CMAP)
    over, under = bool((v > lim).any()), bool((v < -lim).any())
    ext = {(True, True): "both", (True, False): "max", (False, True): "min"}.get(
        (over, under), "neither")
    cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.01, shrink=0.6, extend=ext)
    cb.set_label("Post/pre log change minus control aggregate (log points)")
    cb.outline.set_visible(False)
    draw_boundary(ax, zones, effects.loc[effects["is_cbd"], "zone_id"].tolist())
    b = bounds_of(zones, effects["zone_id"].tolist(), pad=0.02)
    ax.set_xlim(b[0], b[2])
    ax.set_ylim(b[1], b[3])
    ax.set_axis_off()
    ax.set_aspect("equal")
    fig.suptitle(textwrap.fill(title, 70), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 100), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f4b_effect_map_html(zones, effects: pd.DataFrame, title: str, out_file: Path,
                        min_pre_weekly: float, colour_quantile: float) -> Path:
    """Interactive F4b (Plotly): hover shows zone, pre and post mean weekly pickups, change."""
    import plotly.express as px

    gdf = zones.merge(effects, on="zone_id", how="inner").to_crs(4326)
    gdf["change_pct"] = (np.exp(gdf["log_change"]) - 1) * 100
    ok = gdf["pre_mean_weekly"] >= min_pre_weekly        # same zones as the PNG's limit
    lim = float(np.nanquantile(np.abs(gdf.loc[ok, "relative_to_control_aggregate"]),
                               colour_quantile))
    fig = px.choropleth(
        gdf, geojson=gdf.set_index("zone_id").geometry.__geo_interface__,
        locations="zone_id", color="relative_to_control_aggregate",
        color_continuous_scale="RdBu_r", range_color=(-lim, lim),
        hover_name="zone_name",
        hover_data={"zone_id": True, "pre_mean_weekly": ":.0f", "post_mean_weekly": ":.0f",
                    "change_pct": ":.1f", "relative_to_control_aggregate": ":.3f"},
        labels={"pre_mean_weekly": "pre mean weekly pickups",
                "post_mean_weekly": "post mean weekly pickups",
                "change_pct": "change (%)",
                "relative_to_control_aggregate": "vs control aggregate (log pts)"},
        title=title)
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"l": 0, "r": 0, "t": 60, "b": 0})
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_file, include_plotlyjs="cdn", full_html=True,
                   config={"displaylogo": False})
    return out_file


def f4c_heterogeneity(panels: list[tuple[str, pd.DataFrame]], title: str, note: str,
                      out_base: Path) -> list[Path]:
    """F4c: one small multiple per cut; horizontal point-ranges of the static DiD in %
    (exp(b) - 1), own x-scale per panel. `panels`: (panel title, rows with label/coef/ci)."""
    use_style()
    n = len(panels)
    ncol = 4
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(SIZES["small_multiples"][0], 2.6 * nrow),
                             layout="constrained")
    for ax, (name, d) in zip(axes.flat, panels, strict=False):
        y = np.arange(len(d))[::-1]
        pct = (np.exp(d["coef"]) - 1) * 100
        lo, hi = (np.exp(d["ci_lo"]) - 1) * 100, (np.exp(d["ci_hi"]) - 1) * 100
        ax.errorbar(pct, y, xerr=[pct - lo, hi - pct], fmt="o", ms=4, color=PALETTE["cbd"],
                    ecolor=PALETTE["cbd"], elinewidth=1.0, capsize=0)
        ax.axvline(0, color=PALETTE["muted_text"], linewidth=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(d["label"], fontsize=8)
        ax.set_title(textwrap.fill(name, 24), fontsize=9)
        ax.tick_params(axis="x", labelsize=8)
        ax.set_xlabel("Effect (%)", fontsize=8)
        ax.grid(axis="y", visible=False)
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    fig.supxlabel(textwrap.fill(note, 150), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    fig.suptitle(textwrap.fill(title, 95), fontsize=11, fontweight="bold", x=0.01, ha="left")
    return save(fig, out_base)


def f4d_counterfactual_vs_did(cf: pd.DataFrame, paths: list[tuple[str, pd.DataFrame, str]],
                              policy_date: str, title: str, note: str,
                              out_base: Path) -> list[Path]:
    """F4d: monthly implied effect from the frozen-forecast counterfactual vs event-study paths,
    all in % (one axis; same unit)."""
    use_style()
    fig, ax = plt.subplots(figsize=SIZES["single"], layout="constrained")
    x = pd.PeriodIndex(cf["month"], freq="M").to_timestamp() + pd.Timedelta(days=14)
    y = cf["mean_daily_rel"] * 100
    ins = cf["in_sample"].to_numpy()
    ax.plot(x[ins], y[ins], color=tint(PALETTE["model"]), linewidth=1.4, marker="o", ms=3)
    ax.plot(x[~ins], y[~ins], color=PALETTE["model"], linewidth=1.6, marker="o", ms=3)
    ends = [(float(y.iloc[-1]), "Forecast counterfactual", PALETTE["model"])]
    for label, es, color in paths:
        es = es[es["k"] >= int((x.min().to_period("M") - pd.Timestamp(policy_date)
                                .to_period("M")).n)]
        ex = _bin_dates(es["k"], policy_date)
        ey = (np.exp(es["coef"]) - 1) * 100
        ax.plot(ex, ey, color=color, linewidth=1.4, marker="s", ms=3)
        ends.append((float(ey.iloc[-1]), label, color))
    ax.axhline(0, color=PALETTE["muted_text"], linewidth=0.8)
    ax.set_ylabel("Effect on CBD pickups (%)")
    ax.set_xlim(x.min() - pd.Timedelta(days=20), x.max() + pd.Timedelta(days=20))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    direct_labels(ax, x.max() + pd.Timedelta(days=20), ends)
    policy_line(ax, label_y=0.07, side="right")   # below the lowest path: free there
    fig.suptitle(textwrap.fill(title, 80), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 115), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f4e_placebo_distribution(panels: list[tuple[str, pd.Series, float, float]], title: str,
                             note: str, out_base: Path) -> list[Path]:
    """F4e (A2): permutation-placebo estimates (histogram) with the real estimate (line) and
    +-MDE (shaded); one panel per outcome, own x-scale. `panels`: (name, draws, beta, mde)."""
    use_style()
    fig, axes = plt.subplots(1, len(panels), figsize=(SIZES["small_multiples"][0], 4.2),
                             layout="constrained")
    for ax, (name, draws, beta, mde) in zip(np.atleast_1d(axes), panels, strict=True):
        ax.axvspan(-mde, mde, color=tint(PALETTE["baseline"], 0.8), zorder=0)
        ax.hist(draws, bins=40, color=PALETTE["baseline"], edgecolor="white", linewidth=0.5)
        ax.axvline(beta, color=PALETTE["cbd"], linewidth=1.8)
        ax.annotate(f"real estimate {beta:+.3f}", xy=(beta, 0.95), xycoords=("data",
                    "axes fraction"), xytext=(4 if beta < 0 else -4, 0),
                    textcoords="offset points", ha="left" if beta < 0 else "right",
                    fontsize=8.5, color=PALETTE["cbd"], va="top")
        ax.set_title(name, fontsize=10)
        ax.set_xlabel("Placebo DiD estimate (log points)")
        ax.set_ylabel("Draws")
        lo = min(draws.min(), beta, -mde)
        hi = max(draws.max(), beta, mde)
        pad = (hi - lo) * 0.08
        ax.set_xlim(lo - pad, hi + pad)
    fig.suptitle(textwrap.fill(title, 95), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 150), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f4g_app_dispatch(zones, share: pd.DataFrame, title: str, note: str,
                     out_base: Path) -> list[Path]:
    """F4g (Amendment 3, C1): left, map of the app-dispatch share (Uber + Lyft) by pickup zone,
    zones without enough records hatched, CBD outlined; right, 2023->2025 growth of mean weekly
    pickups vs the app share (CBD accent, donut control grey, other zones light)."""
    from taxi_shock.viz.maps import NO_DATA_COLOR, draw_boundary

    use_style()
    fig, (ax, sx) = plt.subplots(1, 2, figsize=SIZES["small_multiples"], layout="constrained",
                                 gridspec_kw={"width_ratios": [1.0, 1.15]})
    gdf = zones.merge(share, on="zone_id", how="left")
    ok = gdf["share_app"].notna()
    norm = mpl.colors.Normalize(vmin=0, vmax=1)
    gdf[~ok].plot(ax=ax, facecolor=NO_DATA_COLOR, edgecolor="white", hatch="////",
                  linewidth=0.2)
    gdf[ok].plot(ax=ax, column="share_app", cmap=SEQUENTIAL_CMAP, norm=norm, edgecolor="white",
                 linewidth=0.2)
    cb = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=SEQUENTIAL_CMAP), ax=ax,
                      fraction=0.04, pad=0.01, shrink=0.6)
    cb.set_label("Uber + Lyft share")
    cb.outline.set_visible(False)
    draw_boundary(ax, zones, share.loc[share["is_cbd"], "zone_id"].tolist())
    ax.set_axis_off()
    ax.set_aspect("equal")
    d = share.dropna(subset=["share_app", "growth_log"])
    groups = [(~d["is_cbd"] & ~d["is_donut_control"], "Other zones", tint(PALETTE["non_cbd"], 0.6)),
              (d["is_donut_control"], "Donut control", PALETTE["non_cbd"]),
              (d["is_cbd"], "CBD", PALETTE["cbd"])]
    for sel, label, color in groups:
        sx.scatter(d.loc[sel, "share_app"] * 100, d.loc[sel, "growth_log"], s=18, color=color,
                   label=label, edgecolor="white", linewidth=0.4)
    sx.axhline(0, color=PALETTE["muted_text"], linewidth=0.8)
    sx.set_xlabel("Uber + Lyft share of yellow trips, Jun-Sep 2026 (%)")
    sx.set_ylabel("Growth of mean weekly pickups 2023 to 2025 (log)")
    sx.legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle(textwrap.fill(title, 95), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 150), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f3b_three_shocks(daily: pd.DataFrame, events: list[tuple[str, str, dict | None]],
                     title: str, note: str, out_base: Path) -> list[Path]:
    """F3b (Amendment 3, C5): one panel per event, x = days since the event, y = 7-day mean of
    the daily log(actual / forecast) in % for the CBD (accent) and non-CBD (grey); the
    calibration year left of 0 is lighter; the CBD's first CUSUM alarm is a dotted line.
    `events`: (event key, panel title, first CUSUM alarm of the CBD or None)."""
    use_style()
    fig, axes = plt.subplots(len(events), 1, figsize=SIZES["small_multiples"], sharex=True,
                             layout="constrained")
    for ax, (key, name, alarm) in zip(np.atleast_1d(axes), events, strict=True):
        d = daily[daily["event"] == key]
        t0 = pd.Timestamp(d.loc[d["stage"] == "monitoring", "day"].min())
        ends = []
        for g, (label, color) in F3_GROUPS.items():
            s = d[d["group"] == g].sort_values("day")
            x = (s["day"] - t0).dt.days
            y = (np.exp(s["log_ratio"].rolling(7, min_periods=4, center=True).mean()) - 1) * 100
            pre = (x < 0).to_numpy()
            ax.plot(x[pre], y[pre], color=tint(color), linewidth=1.2)
            ax.plot(x[~pre], y[~pre], color=color, linewidth=1.4)
            ends.append((float(y.dropna().iloc[-1]), label, color))
        ax.axhline(0, color=PALETTE["muted_text"], linewidth=0.8)
        ax.axvline(0, color=PALETTE["text"], linestyle="--", linewidth=1.0)
        if alarm:
            ax.axvline(alarm["delay_days"], color=PALETTE["cbd"], linestyle=":", linewidth=1.2)
            ax.annotate(f"CUSUM alarm (CBD), day {alarm['delay_days']}",
                        xy=(alarm["delay_days"], 0.08), xycoords=("data", "axes fraction"),
                        xytext=(4, 0), textcoords="offset points", fontsize=8,
                        color=PALETTE["cbd"])
        ax.set_title(name, fontsize=10, loc="left")
        ax.set_ylabel("Actual vs forecast (%)")
        direct_labels(ax, float(x.max()), ends)
    np.atleast_1d(axes)[-1].set_xlabel("Days since the event (left of 0: calibration year)")
    fig.suptitle(textwrap.fill(title, 95), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 150), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f4i_leave_one_out(loo: pd.DataFrame, full: dict[str, float], title: str, note: str,
                      out_base: Path) -> list[Path]:
    """F4i: the static DiD re-estimated dropping each zone in turn (one strip per
    specification, % effect), with the full-sample estimate as a vertical tick."""
    use_style()
    specs = list(full)
    fig, ax = plt.subplots(figsize=SIZES["single"], layout="constrained")
    for i, spec in enumerate(specs):
        d = loo[loo["spec"] == spec]
        y = np.full(len(d), i) + np.linspace(-0.15, 0.15, len(d))
        pct = (np.exp(d["coef"]) - 1) * 100
        ax.scatter(pct, y, s=12, color=tint(PALETTE["cbd"], 0.3), edgecolor="white",
                   linewidth=0.3)
        f = (np.exp(full[spec]) - 1) * 100
        ax.plot([f, f], [i - 0.3, i + 0.3], color=PALETTE["cbd"], linewidth=2.2)
    ax.axvline(0, color=PALETTE["muted_text"], linewidth=0.8)
    ax.set_yticks(range(len(specs)))
    ax.set_yticklabels([s.replace("_", " ") for s in specs])
    ax.set_ylim(-0.6, len(specs) - 0.4)
    ax.set_xlabel("Static DiD effect on CBD pickups, one zone dropped (%)")
    ax.grid(axis="y", visible=False)
    fig.suptitle(textwrap.fill(title, 80), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 115), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)


def f4h_synth_control(paths: pd.DataFrame, policy_date: str, title: str, note: str,
                      out_base: Path) -> list[Path]:
    """F4h (Amendment 3, C3): top, the CBD's demeaned log weekly pickups (actual) and its
    synthetic control; bottom, the gap (actual - synthetic) of the CBD (accent) against the
    in-space placebo gaps (thin grey). Gaps in % (exp(gap) - 1)."""
    use_style()
    fig, (a1, a2) = plt.subplots(2, 1, figsize=SIZES["small_multiples"], sharex=True,
                                 layout="constrained")
    c = paths[paths["unit"] == "CBD"].sort_values("week_start")
    a1.plot(c["week_start"], (np.exp(c["actual"]) - 1) * 100, color=PALETTE["actual"],
            linewidth=1.4)
    a1.plot(c["week_start"], (np.exp(c["synthetic"]) - 1) * 100, color=PALETTE["model"],
            linewidth=1.4, linestyle="--")
    direct_labels(a1, c["week_start"].max() + pd.Timedelta(days=7), [
        (float((np.exp(c["actual"].iloc[-1]) - 1) * 100), "CBD", PALETTE["actual"]),
        (float((np.exp(c["synthetic"].iloc[-1]) - 1) * 100), "Synthetic CBD", PALETTE["model"])])
    a1.set_ylabel("vs pre-period mean (%)")
    for _unit, d in paths[paths["unit"] != "CBD"].groupby("unit"):
        d = d.sort_values("week_start")
        a2.plot(d["week_start"], (np.exp(d["gap"]) - 1) * 100, color=PALETTE["baseline"],
                linewidth=0.6, alpha=0.6)
    a2.plot(c["week_start"], (np.exp(c["gap"]) - 1) * 100, color=PALETTE["cbd"], linewidth=1.6)
    a2.axhline(0, color=PALETTE["muted_text"], linewidth=0.8)
    a2.set_ylabel("Actual vs synthetic (%)")
    for ax in (a1, a2):
        ax.set_xlim(c["week_start"].min(), c["week_start"].max() + pd.Timedelta(days=100))
        policy_line(ax, label=ax is a1)
    a2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    fig.suptitle(textwrap.fill(title, 95), fontsize=11, fontweight="bold", x=0.01, ha="left")
    fig.supxlabel(textwrap.fill(note, 150), fontsize=8, color=PALETTE["muted_text"], x=0.01,
                  ha="left")
    return save(fig, out_base)
