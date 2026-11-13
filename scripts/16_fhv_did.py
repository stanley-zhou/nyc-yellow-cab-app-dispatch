"""Amendment 3 C6 (Phase 6): congestion pricing and high-volume FHV demand.

Demand only. HVFHV pickups per zone x week from the streamed aggregates
(data/processed/hvfhv/zone_hour_*.parquet), on the Phase 4 design (scripts/07b_demand.py: 38 CBD
zones vs the donut control, zone and week FE, weather x treated, CRV1 by zone, log1p weekly
pickups; complete weeks of the event-study window 2023-01 -> 2026-09). Series: Uber + Lyft, Uber,
Lyft, shared-requested trips (shared_request_flag = 'Y'). Each series in two weightings: equal
zone weights and pre-volume weights (the series' own mean weekly pickups over the 52 pre weeks).

Order (C6): the monthly event-study pre-trend test FIRST (pre-registered F and Hotelling F*; the
decision uses F* at 5%, the pre-registered F being oversized for this design,
results/pretrend_test_size.json). A series whose test rejects gets no static estimate ("stop"):
only its pre-trend result and event-study path are reported. For series that pass, the static
DiD with persistence splits; Lyft additionally with January 2025 as its own post period (Lyft's
January 2025 rider credit is a known confounder).

Writes results/fhv_did.json, results/fhv_event_study.csv.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from datetime import UTC, datetime

import duckdb
import numpy as np
import pandas as pd

from taxi_shock.causal.did import static_did
from taxi_shock.causal.event_study import event_study
from taxi_shock.config import load_config, path, repo_root

LOG = logging.getLogger("fhv")


def phase4():
    spec = importlib.util.spec_from_file_location("demand07b",
                                                  repo_root() / "scripts" / "07b_demand.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fhv_weekly(cfg: dict) -> pd.DataFrame:
    files = sorted((repo_root() / cfg["hvfhv"]["out_dir"]).glob("zone_hour_*.parquet"))
    lst = ", ".join(f"'{f.as_posix()}'" for f in files)
    plat = cfg["channel"]["hv_platform_names"]
    cases = ", ".join(f"sum(trips) filter (where platform = '{k}') as fhv_{v}"
                      for k, v in plat.items())
    h = duckdb.sql(f"""
        select zone_id, (pu_hour::date - cast(dayofweek(pu_hour::date) as integer))::date
                   as week_start,
               sum(trips) filter (where platform in ({", ".join(f"'{k}'" for k in plat)}))
                   as fhv_all, {cases},
               sum(trips) filter (where shared_request = 'Y') as fhv_shared
        from read_parquet([{lst}]) group by all""").df()
    h["week_start"] = pd.to_datetime(h["week_start"])
    return h


def analyse(x: pd.DataFrame, s: str, wt: str | None, cfg: dict, p4,
            lyft_splits: dict | None = None) -> tuple[dict, pd.DataFrame]:
    """C6 for one series: the monthly event-study pre-trend test FIRST; the static DiD (and
    persistence, and the Lyft January split if `lyft_splits`) only if Hotelling F* p >= alpha."""
    cc = cfg["causal"]
    alpha = float(cfg["channel_did"]["alpha"])
    ctrl = [f"tr_{c}" for c in cc["weather_controls"]]
    es, info = event_study(x, f"log1p_{s}", "zone_id", ["zone_id"], cfg["data"]["policy_date"],
                           "month", weights=wt, controls=ctrl)
    pt = info["pretrend"]
    pct = np.expm1(es["coef"]) * 100

    def rng(sel):
        return {"min_pct": float(pct[sel].min()), "max_pct": float(pct[sel].max()),
                "mean_pct": float(pct[sel].mean()), "n_bins": int(sel.sum())}

    path_summary = {"pre": rng(es["k"] < 0), "post": rng(es["k"] >= 0),
                    "pre_2023": rng(es["k"].between(-24, -13)),
                    "pre_2024": rng(es["k"].between(-12, -1)),
                    "unit": "monthly event-study coefficients as exp(b) - 1, %, relative to "
                            "the week before the policy"}
    r = {"pretrend": pt, "passes": bool(pt["p_F_hotelling"] >= alpha),
         "event_study_path": path_summary,
         "pre_mean_weekly_treated": float(x.loc[(x["treated"] == 1) & x["event_week"].between(
             -cc["pre_weeks"], -1), s].mean())}
    if r["passes"]:
        r["estimate"] = p4.did(x, f"log1p_{s}", cfg, weights=wt)
        r["persistence"] = p4.did(x, f"log1p_{s}", cfg, weights=wt, splits=True)
        if lyft_splits:
            r["lyft_january_2025_separate"] = static_did(
                x, f"log1p_{s}", "zone_id", ["zone_id"], cc["pre_weeks"], weights=wt,
                controls=ctrl, post_splits=lyft_splits).to_dict()
    return r, es


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    cc, res = cfg["causal"], path("results", cfg)
    alpha = float(cfg["channel_did"]["alpha"])
    p4 = phase4()
    w, zs = p4.load(cfg)
    h = fhv_weekly(cfg)
    series = [c for c in h.columns if c.startswith("fhv_")]
    w = w.merge(h, on=["zone_id", "week_start"], how="left")
    w[series] = w[series].fillna(0)
    d = p4.design(w, zs, cfg, y_cols=series)

    last = str(d["week_start"].max().date())
    lyft_splits = {k: [a, b or last] for k, (a, b) in cfg["channel_did"]["lyft_splits"].items()}
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "specification": "Phase 4 design (07b) on HVFHV pickups; Amendment 3 C6",
           "rule": f"pre-trend test first; a series with Hotelling F* p < {alpha} gets no "
                   "static estimate", "series": {}}
    tables = []
    for s in series:
        for wname in ("equal_weight", "pre_volume_weighted"):
            x = (p4.add_pre_volume_weight(d, cc["pre_weeks"], col=s) if wname != "equal_weight"
                 else d)
            wt = "w_pre" if wname != "equal_weight" else None
            r, es = analyse(x, s, wt, cfg, p4, lyft_splits if s == "fhv_lyft" else None)
            tables.append(es.assign(series=s, weighting=wname))
            pt = r["pretrend"]
            out["series"].setdefault(s, {})[wname] = r
            LOG.info("%s %s: pre-trend F* p %.3g -> %s", s, wname, pt["p_F_hotelling"],
                     "estimate" if r["passes"] else "STOP (no estimate)")
    out["n_zones"] = {"treated": int(d.loc[d["treated"] == 1, "zone_id"].nunique()),
                      "control": int(d.loc[d["treated"] == 0, "zone_id"].nunique())}
    (res / "fhv_did.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    pd.concat(tables).to_csv(res / "fhv_event_study.csv", index=False, lineterminator="\n",
                             float_format="%.6g")


if __name__ == "__main__":
    main()
