"""Measure cross-platform displacement between Uber/Lyft FHV trips and yellow app trips.

PLAN Amendment 4 (D4); exploratory and mainly descriptive.

Zone x week 2023-01 -> 2026-09. FHV = Uber + Lyft high-volume FHV trips (streamed HVFHV
aggregates); yellow app = yellow pickups in the app channel (any e-hail app, Amendment 4a; Uber /
Lyft-specific only from 2026-06).

Descriptive: yellow app trips as a share of each platform's total by zone group and month —
before 2026-06, yellow app / (yellow app + Uber + Lyft FHV); from 2026-06 also Uber's own
yellow-dispatched trips / (those + Uber FHV) and Lyft's (from 2026-08-10).

Estimate (same DML form as the incrementality estimate, D2; scripts/12_incrementality.py
functions): FHV trips on yellow app trips per zone-week, two-way within transform, LightGBM
nuisances, time-blocked cross-fitting, zone-clustered SEs; coefficient = change in FHV trips per
additional yellow app trip (negative = displacement from FHV), by area. Observational.

Reads: the HVFHV aggregates (via scripts/16_fhv_did.py), the yellow channel panel (via
scripts/12_incrementality.py) and warehouse mart fct_weekly_zone_channel; config keys `incr`,
`channel.request_source_from`, `lyft.post_start`.
Writes results/cross_platform.json, results/cross_platform_monthly.csv.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from datetime import UTC, datetime

import pandas as pd

from taxi_shock.config import load_config, path, repo_root

LOG = logging.getLogger("d4")


def load_mod(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, repo_root() / "scripts" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    d2 = load_mod("incr12", "12_incrementality.py")
    c6 = load_mod("fhv16", "16_fhv_did.py")
    h = c6.fhv_weekly(cfg)
    base = d2.load_panel(cfg)
    with d2.connect(path("warehouse", cfg), cfg=cfg) as con:
        pl = con.execute("""
            select zone_id, week_start,
                   sum(pickups) filter (where platform = 'uber') as yellow_uber,
                   sum(pickups) filter (where platform = 'lyft') as yellow_lyft
            from fct_weekly_zone_channel group by all""").df()
    pl["week_start"] = pd.to_datetime(pl["week_start"])
    p = (base.merge(h, on=["zone_id", "week_start"], how="left")
         .merge(pl, on=["zone_id", "week_start"], how="left"))
    for c in ("fhv_all", "fhv_uber", "fhv_lyft", "yellow_uber", "yellow_lyft"):
        p[c] = p[c].fillna(0)
    p["month"] = p["week_start"].dt.to_period("M").astype(str)
    rs_month = str(cfg["channel"]["request_source_from"])[:7]
    lyft_month = str(cfg["lyft"]["post_start"])[:7]
    m = p.groupby(["month", "zone_group"])[["app", "street", "fhv_all", "fhv_uber", "fhv_lyft",
                                            "yellow_uber", "yellow_lyft"]].sum().reset_index()
    nwk = p.groupby("month")["week_start"].nunique()
    m["n_weeks"] = m["month"].map(nwk)
    for c in ("app", "street", "fhv_all", "fhv_uber", "fhv_lyft"):
        m[f"{c}_per_week"] = m[c] / m["n_weeks"]
    m["yellow_app_share_of_app_market"] = m["app"] / (m["app"] + m["fhv_all"])
    m["uber_yellow_share_of_uber"] = (m["yellow_uber"] / (m["yellow_uber"] + m["fhv_uber"])
                                      ).where(m["month"] >= rs_month)
    m["lyft_yellow_share_of_lyft"] = (m["yellow_lyft"] / (m["yellow_lyft"] + m["fhv_lyft"])
                                      ).where(m["month"] >= lyft_month)
    m.to_csv(res / "cross_platform_monthly.csv", index=False, lineterminator="\n",
             float_format="%.6g")

    pf_, x = d2.features(p, cfg)
    pf_ = pf_.assign(street=pf_["fhv_all"])  # FHV as the outcome of the incrementality (D2) code
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "specification": "PLAN.md Amendment 4 D4 (exploratory); DML form of D2",
           "coefficient": "d FHV trips / d yellow app trips per zone-week (negative = "
                          "displacement from FHV); observational", "areas": {}}
    for a in d2.AREAS:
        pa = d2.area_panel(pf_, a, cfg["incr"]["min_weekly"])
        r = d2.dml_plr(d2.two_way(pa, ["street", "app"]), x, cfg)
        r = {k.replace("beta_street_on_app", "coef_fhv_on_yellow_app"): v for k, v in r.items()
             if not k.startswith("theta")}
        r["ci"] = [r["coef_fhv_on_yellow_app"] - 1.959963984540054 * r["se"],
                   r["coef_fhv_on_yellow_app"] + 1.959963984540054 * r["se"]]
        if pa["zone_id"].nunique() < cfg["incr"]["min_zones_inference"]:
            r["inference_note"] = (f"{pa['zone_id'].nunique()} zones: clustered SEs and CIs are "
                                   "not meaningful; no conclusion")
        r["mean_weekly_fhv"] = float(pa["fhv_all"].mean())
        r["mean_weekly_yellow_app"] = float(pa["app"].mean())
        out["areas"][a] = r
        LOG.info("%s: %.3f [%.3f, %.3f]", a, r["coef_fhv_on_yellow_app"], *r["ci"])
    (res / "cross_platform.json").write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
