"""Amendment 4 D5 (exploratory, gated): congestion pricing by channel.

The Phase 4 primary specification (C2: pre-volume-weighted static DiD of log1p weekly pickups per
zone, 38 CBD zones vs the donut control, zone and week FE, weather x treated, CRV1 by zone; the
design and weights of scripts/07b_demand.py, loaded from it so the specification is identical) is
re-run separately for street-hail and app pickups (app = any e-hail app, Amendment 4a). Weights =
each zone's mean weekly TOTAL pickups over the 52 pre weeks (the primary's weights, so the three
estimates weight zones alike). Gate: a channel is interpreted only if its monthly event-study
pre-trend test does not reject at 5% with the Hotelling-corrected F* (the pre-registered F is
oversized for this design: results/pretrend_test_size.json); otherwise its estimate is reported
and marked "not interpretable".

Writes results/did_by_channel.json, results/did_by_channel_event_study.csv.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from datetime import UTC, datetime

import pandas as pd

from taxi_shock.causal.event_study import event_study
from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect

LOG = logging.getLogger("did_by_channel")


def phase4():
    spec = importlib.util.spec_from_file_location("demand07b",
                                                  repo_root() / "scripts" / "07b_demand.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    cc, res = cfg["causal"], path("results", cfg)
    p4 = phase4()
    w, zs = p4.load(cfg)
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        ch = con.execute("""
            select zone_id, week_start,
                   sum(pickups) filter (where channel = 'app') as app,
                   sum(pickups) filter (where channel = 'street') as street
            from fct_weekly_zone_channel group by all""").df()
    ch["week_start"] = pd.to_datetime(ch["week_start"])
    w = w.merge(ch, on=["zone_id", "week_start"], how="left").fillna({"app": 0, "street": 0})
    if not (w["app"] + w["street"] == w["pickups"]).all():
        raise ValueError("channel split does not add up to the panel's pickups")
    d = p4.design(w, zs, cfg, y_cols=["pickups", "app", "street"])
    dw = p4.add_pre_volume_weight(d, cc["pre_weeks"])
    ctrl = [f"tr_{c}" for c in cc["weather_controls"]]
    alpha = float(cfg["channel_did"]["alpha"])
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "specification": "Phase 4 C2 primary (scripts/07b_demand.py design and weights) by "
                            "channel; Amendment 4 D5 (exploratory, gated)",
           "gate": f"interpret only if the monthly pre-trend Hotelling F* p >= {alpha}",
           "channels": {}}
    tables = []
    for y in ("pickups", "street", "app"):
        est = p4.did(dw, f"log1p_{y}", cfg, weights="w_pre")
        es, info = event_study(dw, f"log1p_{y}", "zone_id", ["zone_id"],
                               cfg["data"]["policy_date"], "month", weights="w_pre",
                               controls=ctrl)
        p_h = info["pretrend"]["p_F_hotelling"]
        out["channels"][y] = {"estimate": est, "pretrend": info["pretrend"],
                              "interpretable": bool(p_h >= alpha),
                              "pre_mean_weekly_treated": float(
                                  dw.loc[(dw["treated"] == 1) & dw["event_week"].between(
                                      -cc["pre_weeks"], -1), y].mean())}
        tables.append(es.assign(outcome=y))
        t = est["terms"]["treated_post"]
        LOG.info("%s: %.4f [%.4f, %.4f], pre-trend F* p %.3g", y, t["coef"], t["ci_lo"],
                 t["ci_hi"], p_h)
    out["channels"]["pickups"]["note"] = "all pickups: reproduces the Phase 4 primary estimate"
    (res / "did_by_channel.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    pd.concat(tables).to_csv(res / "did_by_channel_event_study.csv", index=False,
                             lineterminator="\n", float_format="%.6g")


if __name__ == "__main__":
    main()
