"""Amendment 4, D2: incrementality of the app channel by geography (observational).

Estimand: theta = change in total pickups per additional app pickup = 1 + beta, where beta is the
partial effect of app pickups on street-hail pickups in the same zone-week (theta = 1: fully
incremental; theta = 0: every app trip displaces a street hail).

Panel: zone x complete week, 2023-01 -> 2026-09, from fct_weekly_zone_channel (app = any e-hail
app, Amendment 4a), zeros filled (balanced); zones of each area with a mean of >= incr.min_weekly
pickups per week in 2023; the CMT outer-borough block is excluded (Amendment 4a: D2 primary).

Primary estimator: partially linear DML (DoubleML `DoubleMLPLR`, partialling-out score) with
LightGBM nuisance models, on two-way within-transformed outcome and treatment (zone fixed effects
and citywide week effects of the area removed; the panel is balanced, so the transform is exact):
    street~_it = beta * app~_it + g(X_it) + e,   app~_it = m(X_it) + v
X: weather (weekly mean temperature, precipitation), calendar (week of year, holidays in the
week), zone attributes (pickup-zone centroid, pre-period volume), lagged total pickups (1-4
weeks). Cross-fitting on incr.n_folds contiguous time blocks of weeks (DoubleML custom sample
splitting); standard errors clustered by zone from DoubleML's score elements
(var = sum_g (sum_{i in g} psi_i)^2 / (n J)^2, J = mean psi_deriv).

Robustness (each per area): TWFE (street ~ app | zone + week, pyfixest, CRV1 by zone); first
differences (d street ~ d app | week); a one-week lead of app pickups in the first-difference
regression (placebo, expected ~ 0); zone linear trends removed before DML; the D0 label (Flex Fare
throughout, also from 2026-06); the CMT block included as street hails, window ending 2026-05-24;
DoubleML's panel estimator (`DoubleMLPLPR`, within-group approximation, Clarke and Polselli 2025)
with its own unit-based folds.

Supply view: TLC monthly aggregate report (sources.tlc_monthly_report_url; downloaded to
data/raw/lookup with the manifest): yellow trips per active vehicle-day and hours per vehicle-day,
2022 -> latest month.

Writes results/incrementality_dml.json, results/incrementality_panel_summary.csv,
results/supply_monthly.csv.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import doubleml as dml
import numpy as np
import pandas as pd
import pyfixest as pf
from lightgbm import LGBMRegressor

from taxi_shock.causal.did import Z95
from taxi_shock.causal.panel import full_weeks
from taxi_shock.config import load_config, path
from taxi_shock.download import download_file, update_manifest
from taxi_shock.io import connect

LOG = logging.getLogger("incrementality")
AREAS = ["cbd", "manhattan_non_cbd", "other", "airports"]


def load_panel(cfg: dict, flex_label: bool = False, with_block: bool = False) -> pd.DataFrame:
    """Balanced zone x week panel: app, street (block excluded unless with_block), total."""
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        if flex_label:   # D0 sensitivity: Flex Fare as the app label for the whole window
            w = con.execute("""
                select v.zone_id, v.week_start, z.zone_group,
                       sum(v.pickups_flex) as app,
                       sum(v.pickups - v.pickups_flex) filter (where not (v.vendor_id = 1
                           and z.zone_group = 'other')) as street,
                       sum(v.pickups - v.pickups_flex) filter (where v.vendor_id = 1
                           and z.zone_group = 'other') as block
                from fct_weekly_zone_vendor v join dim_zones z using (zone_id)
                group by all""").df()
        else:
            w = con.execute("""
                select zone_id, week_start, zone_group,
                       sum(pickups) filter (where channel = 'app') as app,
                       sum(pickups) filter (where channel = 'street'
                                            and not is_cmt_outer_block) as street,
                       sum(pickups) filter (where is_cmt_outer_block) as block
                from fct_weekly_zone_channel group by all""").df()
        wx = con.execute("""
            select week_start, avg(mean_temp_f) as temp_f, avg(total_precip_in) as precip_in
            from fct_weekly_zone_panel group by all""").df()
        zs = con.execute("select zone_id, zone_group from dim_zones").df()
    w["week_start"] = pd.to_datetime(w["week_start"])
    wx["week_start"] = pd.to_datetime(wx["week_start"])
    hol = pd.to_datetime(pd.read_csv(path("holidays_seed", cfg))["date"])
    hw = (hol - pd.to_timedelta((hol.dt.dayofweek + 1) % 7, unit="D")).value_counts()
    wx["n_holidays"] = wx["week_start"].map(hw).fillna(0)
    w = full_weeks(w, cfg)
    weeks = sorted(w["week_start"].unique())
    idx = pd.MultiIndex.from_product([zs["zone_id"], weeks], names=["zone_id", "week_start"])
    p = (w.drop(columns="zone_group").set_index(["zone_id", "week_start"])
         .reindex(idx, fill_value=0).fillna(0).reset_index()
         .merge(zs, on="zone_id").merge(wx, on="week_start", how="left"))
    if with_block:
        p["street"] = p["street"] + p["block"]
    p["total"] = p["app"] + p["street"]
    return p


def features(p: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[str]]:
    zc = pd.read_csv(path("zones_cbd", cfg))[["zone_id", "centroid_lon", "centroid_lat"]]
    p = p.sort_values(["zone_id", "week_start"]).merge(zc, on="zone_id", how="left")
    pre = p[p["week_start"].dt.year == 2023].groupby("zone_id")["total"].mean()
    p["pre_volume"] = p["zone_id"].map(pre)
    wk = p["week_start"].dt.isocalendar().week.astype(float)
    p["woy_sin"], p["woy_cos"] = np.sin(2 * np.pi * wk / 52.18), np.cos(2 * np.pi * wk / 52.18)
    g = p.groupby("zone_id")["total"]
    for k in (1, 2, 3, 4):
        p[f"total_lag{k}"] = g.shift(k)
    x = ["temp_f", "precip_in", "n_holidays", "woy_sin", "woy_cos", "centroid_lon",
         "centroid_lat", "pre_volume", "total_lag1", "total_lag2", "total_lag3", "total_lag4"]
    return p.dropna(subset=["total_lag4"]).reset_index(drop=True), x


def two_way(p: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Exact two-way within transform on a balanced panel: x - x_i. - x_.t + x_.."""
    out = p.copy()
    for c in cols:
        out[c] = (p[c] - p.groupby("zone_id")[c].transform("mean")
                  - p.groupby("week_start")[c].transform("mean") + p[c].mean())
    return out


def detrend(p: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Remove a zone-specific linear trend in weeks (robustness: zone trends)."""
    out = p.copy()
    t = (p["week_start"] - p["week_start"].min()).dt.days / 7.0
    for c in cols:
        def res(g, c=c):
            tt = t.loc[g.index]
            b = np.polyfit(tt, g[c], 1) if g[c].std() > 0 else (0.0, g[c].mean())
            return g[c] - (b[0] * tt + b[1])
        out[c] = p.groupby("zone_id", group_keys=False).apply(res)
    return out


def time_blocks(weeks: pd.Series, k: int) -> list[tuple[np.ndarray, np.ndarray]]:
    u = np.sort(weeks.unique())
    blocks = np.array_split(u, k)
    return [(np.flatnonzero(~weeks.isin(b).to_numpy()), np.flatnonzero(weeks.isin(b).to_numpy()))
            for b in blocks]


def dml_plr(p: pd.DataFrame, x: list[str], cfg: dict) -> dict:
    ic = cfg["incr"]
    data = dml.DoubleMLData(p[["street", "app", *x]], y_col="street", d_cols="app", x_cols=x)

    def lgbm():
        return LGBMRegressor(**ic["lgbm"], random_state=cfg["seed"], verbose=-1)

    m = dml.DoubleMLPLR(data, ml_l=lgbm(), ml_m=lgbm(), n_folds=ic["n_folds"],
                        draw_sample_splitting=False)
    m.set_sample_splitting([time_blocks(p["week_start"], ic["n_folds"])])
    m.fit()
    beta = float(m.coef[0])
    psi = m.psi[:, 0, 0]
    j = float(m.psi_deriv[:, 0, 0].mean())
    n = len(psi)
    by = pd.Series(psi).groupby(p["zone_id"].to_numpy()).sum()
    se = float(np.sqrt((by ** 2).sum()) / (n * abs(j)))
    return summarise(beta, se, int(n), int(p["zone_id"].nunique()),
                     extra={"se_doubleml_default": float(m.se[0])})


def summarise(beta: float, se: float, n: int, g: int, extra: dict | None = None) -> dict:
    return {"beta_street_on_app": beta, "se": se, "theta": 1 + beta,
            "theta_ci": [1 + beta - Z95 * se, 1 + beta + Z95 * se], "n_obs": n, "n_zones": g,
            **(extra or {})}


def feols(fml: str, d: pd.DataFrame, term: str, lead: str | None = None) -> dict:
    m = pf.feols(fml, data=d, vcov={"CRV1": "zone_id"})
    b, s = float(m.coef()[term]), float(m.se()[term])
    out = summarise(b, s, int(m._N), int(d["zone_id"].nunique()), {"formula": fml})
    if lead:
        out["lead"] = {"coef": float(m.coef()[lead]), "se": float(m.se()[lead]),
                       "pvalue": float(m.pvalue()[lead])}
    return out


def plpr(p: pd.DataFrame, x: list[str], cfg: dict) -> dict:
    ic = cfg["incr"]
    d = p[["zone_id", "week_start", "street", "app", *x]].copy()
    d["t"] = (d["week_start"] - d["week_start"].min()).dt.days // 7
    data = dml.DoubleMLPanelData(d.drop(columns="week_start"), y_col="street", d_cols="app",
                                 t_col="t", id_col="zone_id", x_cols=x, static_panel=True)
    # DoubleML draws its unit-based folds with sklearn KFold(shuffle=True) and no random_state,
    # i.e. from numpy's global RNG: seed it so the folds (and theta) are reproducible
    np.random.seed(cfg["seed"])  # noqa: NPY002  (DoubleML reads the legacy global RNG)
    m = dml.DoubleMLPLPR(data, LGBMRegressor(**ic["lgbm"], random_state=cfg["seed"],
                                             verbose=-1),
                         LGBMRegressor(**ic["lgbm"], random_state=cfg["seed"], verbose=-1),
                         n_folds=ic["n_folds"], approach="wg_approx")
    m.fit()
    return summarise(float(m.coef[0]), float(m.se[0]), len(d), int(d["zone_id"].nunique()),
                     {"approach": "wg_approx (Clarke and Polselli 2025), DoubleML folds"})


def area_panel(p: pd.DataFrame, area: str, min_weekly: float) -> pd.DataFrame:
    a = p[p["zone_group"] == area]
    keep = a[a["week_start"].dt.year == 2023].groupby("zone_id")["total"].mean()
    return a[a["zone_id"].isin(keep[keep >= min_weekly].index)].reset_index(drop=True)


def estimate_area(p: pd.DataFrame, x: list[str], cfg: dict, full: bool = True) -> dict:
    tw = two_way(p, ["street", "app"])
    out = {"dml_plr": dml_plr(tw, x, cfg)}
    if not full:
        return out
    out["twfe"] = feols("street ~ app | zone_id + week_start", p, "app")
    fd = p.sort_values(["zone_id", "week_start"]).copy()
    g = fd.groupby("zone_id")
    fd["d_street"], fd["d_app"] = g["street"].diff(), g["app"].diff()
    fd["d_app_lead"] = fd.groupby("zone_id")["d_app"].shift(-1)
    out["first_difference"] = feols("d_street ~ d_app | week_start", fd.dropna(subset=[
        "d_street", "d_app"]), "d_app")
    out["first_difference_lead_placebo"] = feols(
        "d_street ~ d_app + d_app_lead | week_start", fd.dropna(), "d_app", lead="d_app_lead")
    out["dml_zone_trends"] = dml_plr(two_way(detrend(p, ["street", "app"]),
                                             ["street", "app"]), x, cfg)
    if p["zone_id"].nunique() >= cfg["incr"]["n_folds"]:     # unit-based folds need >= K zones
        out["dml_panel_plpr"] = plpr(p, x, cfg)
    return out


def supply(cfg: dict) -> pd.DataFrame:
    dest = path("raw_lookup", cfg) / "data_reports_monthly.csv"
    n = download_file(cfg["sources"]["tlc_monthly_report_url"], dest, cfg)
    update_manifest([(dest, n)], cfg)
    r = pd.read_csv(dest, thousands=",", na_values=["-"])
    y = r[r["License Class"] == "Yellow"].copy()
    y["month"] = pd.PeriodIndex(y["Month/Year"], freq="M").astype(str)
    y = y[y["month"] >= cfg["incr"]["supply_from"]].sort_values("month")
    out = pd.DataFrame({
        "month": y["month"], "trips_per_day": y["Trips Per Day"],
        "vehicles_per_day": y["Vehicles Per Day"], "unique_vehicles": y["Unique Vehicles"],
        "trips_per_vehicle_day": y["Trips Per Day"] / y["Vehicles Per Day"],
        "hours_per_vehicle_day": y["Avg Hours Per Day Per Vehicle"],
        "avg_minutes_per_trip": y["Avg Minutes Per Trip"]})
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    ic, res = cfg["incr"], path("results", cfg)
    base, x = features(load_panel(cfg), cfg)
    flex, _ = features(load_panel(cfg, flex_label=True), cfg)
    blk, _ = features(load_panel(cfg, with_block=True), cfg)
    blk = blk[blk["week_start"] <= pd.Timestamp(ic["block_sensitivity_end"])]
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "specification": "PLAN.md Amendment 4 D2, Amendment 4a; DECISIONS.md",
           "estimand": "theta = 1 + d street / d app (1 = fully incremental, 0 = fully "
                       "displacing); observational", "library": f"DoubleML {dml.__version__}",
           "controls": x, "n_folds_time_blocks": ic["n_folds"], "lgbm": ic["lgbm"],
           "min_weekly_2023": ic["min_weekly"], "areas": {}}
    rows = []
    for a in AREAS:
        pa = area_panel(base, a, ic["min_weekly"])
        LOG.info("%s: %d zones, %d zone-weeks", a, pa["zone_id"].nunique(), len(pa))
        r = estimate_area(pa, x, cfg)
        r["d0_label_flex_throughout"] = estimate_area(area_panel(flex, a, ic["min_weekly"]), x,
                                                      cfg, full=False)["dml_plr"]
        if a == "other":
            r["cmt_block_included_to_2026_05_24"] = estimate_area(
                area_panel(blk, a, ic["min_weekly"]), x, cfg, full=False)["dml_plr"]
        if pa["zone_id"].nunique() < ic["min_zones_inference"]:
            r["inference_note"] = (f"{pa['zone_id'].nunique()} zones: clustered SEs and CIs "
                                   "are not meaningful; no app-channel conclusion (Amendment 4a)")
        r["descriptive"] = {"mean_weekly_app": float(pa["app"].mean()),
                            "mean_weekly_street": float(pa["street"].mean()),
                            "app_share": float(pa["app"].sum() / pa["total"].sum())}
        out["areas"][a] = r
        for k, v in r.items():
            if "theta" in v:
                rows.append({"area": a, "estimate": k, "theta": v["theta"],
                             "ci_lo": v["theta_ci"][0], "ci_hi": v["theta_ci"][1],
                             "n_zones": v["n_zones"], "n_obs": v["n_obs"]})
        LOG.info("%s: theta %.3f [%.3f, %.3f]", a, r["dml_plr"]["theta"],
                 *r["dml_plr"]["theta_ci"])
    sup = supply(cfg)
    sup.to_csv(res / "supply_monthly.csv", index=False, lineterminator="\n", float_format="%.6g")
    out["supply"] = {"source": cfg["sources"]["tlc_monthly_report_url"],
                     "file": "results/supply_monthly.csv",
                     "first_month": sup["month"].iloc[0], "last_month": sup["month"].iloc[-1],
                     "yearly_means_of_monthly_values": {
                         y: {c: float(v) for c, v in g.drop(columns="month").mean().items()}
                         for y, g in sup.groupby(sup["month"].str[:4])}}
    (res / "incrementality_dml.json").write_text(json.dumps(out, indent=2) + "\n")
    pd.DataFrame(rows).to_csv(res / "incrementality_panel_summary.csv", index=False,
                              lineterminator="\n", float_format="%.6g")


if __name__ == "__main__":
    main()
