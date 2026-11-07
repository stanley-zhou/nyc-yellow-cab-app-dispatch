"""Figure system: one mplstyle, one semantic palette, one policy-line helper (PLAN §7)."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from taxi_shock.config import load_config

STYLE_FILE = Path(__file__).with_name("taxi_shock.mplstyle")

# Semantic palette, fixed for the whole project.
PALETTE: dict[str, str] = {
    "cbd": "#B23A48",
    "non_cbd": "#8A8F98",
    "model": "#1F5F8B",
    "baseline": "#B0B4BA",
    "actual": "#1A1A1A",       # observed series (near-black, distinct from every model colour)
    "muted_text": "#6B7078",   # notes, secondary labels, baseline lines drawn over a baseline band
    "text": "#2B2B2B",
}
DIVERGING_CMAP = "RdBu_r"   # blue-white-red, centred at 0 with a TwoSlopeNorm
SEQUENTIAL_CMAP = "Blues"   # single-hue, used on a log scale

SIZES: dict[str, tuple[float, float]] = {
    "single": (7.0, 4.2),
    "map": (7.0, 7.0),
    "small_multiples": (10.0, 6.0),
}


def use_style() -> None:
    plt.style.use(STYLE_FILE)


def tint(hex_color: str, amount: float = 0.55) -> str:
    """Lighter tint of a colour (used for the pre-period version of a series)."""
    r, g, b = mpl.colors.to_rgb(hex_color)
    return mpl.colors.to_hex((r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount))


def policy_line(ax: Axes, label: bool = True) -> None:
    """Dashed vertical line at the policy date, drawn only if the date is inside the x-range."""
    date = pd.Timestamp(load_config()["data"]["policy_date"])
    x = mdates.date2num(date)
    lo, hi = ax.get_xlim()
    if not lo <= x <= hi:
        return
    ax.axvline(x, color=PALETTE["text"], linestyle="--", linewidth=1.0, zorder=3)
    if label:
        ax.annotate(f"Congestion pricing starts {date.date().isoformat()}", xy=(x, 1.0),
                    xycoords=("data", "axes fraction"), xytext=(4, -4),
                    textcoords="offset points", ha="left", va="top", fontsize=8.5,
                    color=PALETTE["text"])


def direct_label(ax: Axes, x: object, y: float, text: str, color: str) -> None:
    """Label a line at its end instead of using a legend."""
    ax.annotate(text, xy=(x, y), xytext=(4, 0), textcoords="offset points",
                va="center", ha="left", fontsize=9, color=color)


def direct_labels(
    ax: Axes, x: object, items: list[tuple[float, str, str]], min_gap_frac: float = 0.06
) -> None:
    """Label several line ends at `x`; items are (y, text, colour). Labels closer than
    `min_gap_frac` of the y-range are pushed apart so they never overlap."""
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * min_gap_frac
    placed: list[float] = []
    for y, text, color in sorted(items, key=lambda t: t[0]):
        y_lab = max(y, placed[-1] + gap) if placed else y
        placed.append(y_lab)
        ax.annotate(text, xy=(x, y), xytext=(x, y_lab), textcoords="data",
                    va="center", ha="left", fontsize=9, color=color,
                    annotation_clip=False)


def save(fig: Figure, out_base: Path) -> list[Path]:
    """Save PNG (200 dpi) and SVG next to each other; returns the paths."""
    out_base.parent.mkdir(parents=True, exist_ok=True)
    paths = [out_base.with_suffix(".png"), out_base.with_suffix(".svg")]
    for p in paths:
        fig.savefig(p)
    plt.close(fig)
    return paths
