"""Amendment 4a D5b (pre-specified): did congestion pricing move trips into the app channel?

D0 dated a +10.9 pp step in the Flex (app) share to the week of 2025-01-19, two weeks after the
policy began; the fee is $0.75 per taxi trip and $1.50 per high-volume FHV trip. Test: is the step
larger for trips touching the CBD (within / into / out of) than for trips touching neither end?

Yellow (fct_weekly_zone_channel): cells = pickup zone x trip type x week in
channel_did.step_window. Static DiD: y = a_{zone,type} + l_week + d * touch * post, post = weeks
from the policy week, weighted by the cell's trips (shares) or unweighted (log counts), CRV1 by
pickup zone; outcomes: app share, log1p app trips, log1p street-hail trips (log counts both
unweighted and weighted by the cell's pre-policy mean weekly trips — the unweighted version is
dominated by the many small outer-borough cells; both reported, DECISIONS). Each CBD-touching type
separately against `neither`, and pooled. Event study: touch x week dummies, reference = the week
before the policy. Plus the citywide weekly app share by trip type (descriptive).

HVFHV (data/processed/hvfhv zone_hour aggregates): Uber + Lyft trips per pickup zone x trip type x
week, log1p trips, same DiD (touch x post), and by platform.

Reading (Amendment 4a): if the fee differential is the cause, d > 0 for CBD-touching trips; if the
step is the same across trip types, it is not attributable to the fee differential.

Writes results/app_share_policy_step.json, results/app_share_by_trip_type_weekly.csv,
results/app_share_step_event_study.csv.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import duckdb
import numpy as np
import pandas as pd
import pyfixest as pf

from taxi_shock.causal.did import Z95
from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect

LOG = logging.getLogger("d5b")
TOUCH = ["within", "into", "out_of"]


def did(d: pd.DataFrame, y: str, weights: str | None) -> dict:
    m = pf.feols(f"{y} ~ touch_post | cell + week_start", data=d, weights=weights,
                 vcov={"CRV1": "zone_id"})
    b, s = float(m.coef()["touch_post"]), float(m.se()["touch_post"])
    return {"coef": b, "se": s, "ci": [b - Z95 * s, b + Z95 * s],
            "pvalue": float(m.pvalue()["touch_post"]), "n_obs": int(m._N),
            "n_zones": int(d["zone_id"].nunique())}


def prep(c: pd.DataFrame, types: list[str], policy: pd.Timestamp) -> pd.DataFrame:
    d = c[c["trip_type"].isin([*types, "neither"])].copy()
    d["touch"] = (d["trip_type"] != "neither").astype(int)
    d["post"] = (d["week_start"] >= policy).astype(int)
    d["touch_post"] = (d["touch"] * d["post"]).astype(float)
    d["cell"] = d["zone_id"].astype(str) + "_" + d["trip_type"]
    vol = "trips" if "trips" in d else None
    if vol:   # cell weight = the cell's mean weekly trips before the policy (fixed per cell)
        pre = d[d["week_start"] < policy].groupby("cell")[vol].mean()
        d["w_cell"] = d["cell"].map(pre).fillna(0.0)
        d = d[d["w_cell"] > 0]
    return d


def event_study(d: pd.DataFrame, y: str, weights: str | None, policy: pd.Timestamp
                ) -> pd.DataFrame:
    k = ((d["week_start"] - policy).dt.days // 7).astype(int)
    terms, x = [], d.copy()
    for e in sorted(k.unique()):
        if e == -1:
            continue
        t = f"e{'m' if e < 0 else 'p'}{abs(e):02d}"
        x[t] = ((k == e) & (x["touch"] == 1)).astype(float)
        terms.append((e, t))
    m = pf.feols(f"{y} ~ {' + '.join(t for _, t in terms)} | cell + week_start", data=x,
                 weights=weights, vcov={"CRV1": "zone_id"})
    return pd.DataFrame([{"event_week": e, "coef": float(m.coef()[t]), "se": float(m.se()[t])}
                         for e, t in terms])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    lo, hi = (pd.Timestamp(x) for x in cfg["channel_did"]["step_window"])
    policy = pd.Timestamp(cfg["data"]["policy_date"])
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        c = con.execute("""
            select zone_id, week_start, trip_type,
                   sum(pickups) filter (where channel = 'app') as app,
                   sum(pickups) filter (where channel = 'street'
                                        and not is_cmt_outer_block) as street
            from fct_weekly_zone_channel group by all""").df()
    c["week_start"] = pd.to_datetime(c["week_start"])
    c = c[(c["week_start"] >= lo) & (c["week_start"] + pd.Timedelta(days=6) <= hi)].fillna(0)
    c["trips"] = c["app"] + c["street"]
    c = c[c["trips"] > 0].copy()
    c["app_share"] = c["app"] / c["trips"]
    c["log1p_app"] = np.log1p(c["app"])
    c["log1p_street"] = np.log1p(c["street"])
    wk = c.groupby(["week_start", "trip_type"])[["app", "trips"]].sum().reset_index()
    wk["app_share"] = wk["app"] / wk["trips"]
    wk.to_csv(res / "app_share_by_trip_type_weekly.csv", index=False, lineterminator="\n",
              float_format="%.6g")
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "specification": "PLAN.md Amendment 4a D5b; DECISIONS.md",
           "window": [str(lo.date()), str(hi.date())], "policy_week": str(policy.date()),
           "yellow": {}, "hvfhv": {}}
    es_rows = []
    for name, types in [("pooled", TOUCH), *[(t, [t]) for t in TOUCH]]:
        d = prep(c, types, policy)
        out["yellow"][name] = {"app_share": did(d, "app_share", "trips"),
                               "log1p_app": did(d, "log1p_app", None),
                               "log1p_street": did(d, "log1p_street", None),
                               "log1p_app_cell_weighted": did(d, "log1p_app", "w_cell"),
                               "log1p_street_cell_weighted": did(d, "log1p_street", "w_cell")}
        if name == "pooled":
            for y, wgt in (("app_share", "trips"), ("log1p_app", None), ("log1p_street", None)):
                es_rows.append(event_study(d, y, wgt, policy).assign(source="yellow",
                                                                     outcome=y))
    # pre/post mean share by type (descriptive): 4 weeks either side of the D0 step week
    step = pd.Timestamp(cfg["channel_did"]["d0_step_week"])
    desc = {}
    for t, x in wk.groupby("trip_type"):
        b = x[(x["week_start"] < step) & (x["week_start"] >= step - pd.Timedelta(weeks=4))]
        a = x[(x["week_start"] >= step) & (x["week_start"] < step + pd.Timedelta(weeks=4))]
        desc[t] = {"share_before": float(b["app"].sum() / b["trips"].sum()),
                   "share_after": float(a["app"].sum() / a["trips"].sum())}
        desc[t]["step_pp"] = (desc[t]["share_after"] - desc[t]["share_before"]) * 100
    out["yellow"]["d0_step_by_trip_type"] = {"step_week": str(step.date()), "weeks_each_side": 4,
                                             "by_type": desc}

    agg = repo_root() / cfg["hvfhv"]["out_dir"]
    files = sorted(agg.glob("zone_hour_*.parquet"))
    if files:
        lst = ", ".join(f"'{f.as_posix()}'" for f in files)
        h = duckdb.sql(f"""
            select zone_id, (pu_hour::date - cast(dayofweek(pu_hour::date) as integer))::date
                       as week_start, trip_type, platform, sum(trips) as trips
            from read_parquet([{lst}]) group by all""").df()
        h["week_start"] = pd.to_datetime(h["week_start"])
        h = h[(h["week_start"] >= lo) & (h["week_start"] + pd.Timedelta(days=6) <= hi)]
        plat = cfg["channel"]["hv_platform_names"]
        for p_name, sel in [("uber_lyft", list(plat)), *[(plat[k], [k]) for k in plat]]:
            x = h[h["platform"].isin(sel)].groupby(["zone_id", "week_start", "trip_type"])[
                "trips"].sum().reset_index()
            x["log1p_trips"] = np.log1p(x["trips"])
            d = prep(x, TOUCH, policy)
            out["hvfhv"][p_name] = {"log1p_trips": did(d, "log1p_trips", None),
                                    "log1p_trips_cell_weighted": did(d, "log1p_trips", "w_cell")}
            if p_name == "uber_lyft":
                es_rows.append(event_study(d, "log1p_trips", None, policy).assign(
                    source="hvfhv", outcome="log1p_trips"))
    else:
        out["hvfhv"] = {"note": "HVFHV aggregates not present"}
    (res / "app_share_policy_step.json").write_text(json.dumps(out, indent=2) + "\n")
    pd.concat(es_rows).to_csv(res / "app_share_step_event_study.csv", index=False,
                              lineterminator="\n", float_format="%.6g")
    p = out["yellow"]["pooled"]["app_share"]
    LOG.info("D5b yellow pooled app share: %.4f [%.4f, %.4f]", p["coef"], *p["ci"])


if __name__ == "__main__":
    main()
