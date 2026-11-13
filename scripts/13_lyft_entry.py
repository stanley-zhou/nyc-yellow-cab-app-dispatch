"""Amendment 4 D3 (with Amendment 4a timing): Lyft's entry into yellow-cab dispatch. PRELIMINARY.

Lyft trips (request_source HV0005) occur only on Curb-equipped cabs (VendorID 2), first on
2026-08-10 (D0). Design: vendor-level difference-in-differences on pickup zone x vendor x day —
treated = Curb cabs (gain Lyft access), control = CMT cabs (VendorID 1) — with zone x vendor and
zone x day fixed effects and SEs clustered by pickup zone; CBD and Manhattan non-CBD zones only
(Amendment 4a). Outcomes per zone x vendor x day: total, app and street-hail pickups (levels),
Uber-dispatched pickups (2026-06 onward only). Covariate: the same zone x vendor's pickups 364
days earlier (prior-year same weekday).

Windows (Amendment 4a). Primary, clean: pre = days <= lyft.pre_end, post = days >= lyft.post_start,
the weeks between excluded; total / app / street use the long pre-period from lyft.long_pre_start,
Uber-dispatched from lyft.uber_pre_start. Secondary (hypothesis-based): treatment from
lyft.secondary_start, with Lyft trips = HV0005 + Curb code-A pickups above their mean per zone-day
over lyft.code_a_baseline.

Incrementality of Lyft trips = (DiD effect on Curb total pickups per zone-day) / (mean Lyft
pickups per Curb zone-day in the post-period); displacement of Uber-dispatched trips = the DiD
effect on Uber pickups / the same mean. Pre-trends: weekly event study over the pre-period
(reference = the last pre week), joint Wald test (pre-registered F and Hotelling F*).

Writes results/lyft_entry.json, results/lyft_entry_daily.csv (Curb vs CMT daily series).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pyfixest as pf

from taxi_shock.causal.did import Z95
from taxi_shock.causal.event_study import wald
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("lyft")


def load(cfg: dict) -> pd.DataFrame:
    lc = cfg["lyft"]
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        d = con.execute(f"""
            select zone_id, day, vendor_id,
                   sum(pickups) as total,
                   sum(pickups) filter (where channel = 'app') as app,
                   sum(pickups) filter (where channel = 'street') as street,
                   sum(pickups) filter (where platform = 'uber') as uber,
                   sum(pickups) filter (where platform = 'lyft') as lyft,
                   sum(pickups) filter (where platform = 'code_a') as code_a
            from fct_daily_zone_channel
            where zone_group in ('cbd', 'manhattan_non_cbd') and vendor_id in (1, 2)
              and day >= date '{lc['long_pre_start']}' - interval 371 day
            group by all""").df()
    d["day"] = pd.to_datetime(d["day"])
    zones = d["zone_id"].unique()
    days = pd.date_range(d["day"].min(), d["day"].max(), freq="D")
    idx = pd.MultiIndex.from_product([zones, [1, 2], days], names=["zone_id", "vendor_id", "day"])
    d = d.set_index(["zone_id", "vendor_id", "day"]).reindex(idx).fillna(0).reset_index()
    prior = d.assign(day=d["day"] + pd.Timedelta(days=364))[["zone_id", "vendor_id", "day",
                                                             "total"]]
    d = d.merge(prior.rename(columns={"total": "total_py"}), on=["zone_id", "vendor_id", "day"],
                how="left")
    d["curb"] = (d["vendor_id"] == 2).astype(int)
    d["zv"] = d["zone_id"].astype(str) + "_" + d["vendor_id"].astype(str)
    d["zd"] = d["zone_id"].astype(str) + "_" + d["day"].dt.strftime("%Y%m%d")
    return d[d["day"] >= pd.Timestamp(lc["long_pre_start"])].reset_index(drop=True)


def did(d: pd.DataFrame, y: str, covariate: bool = True, cov: str = "total_py") -> dict:
    x = d.assign(treat=d["curb"] * d["post"])
    fml = f"{y} ~ treat{' + ' + cov if covariate else ''} | zv + zd"
    m = pf.feols(fml, data=x.dropna(subset=[cov]) if covariate else x,
                 vcov={"CRV1": "zone_id"})
    b, s = float(m.coef()["treat"]), float(m.se()["treat"])
    return {"coef": b, "se": s, "ci": [b - Z95 * s, b + Z95 * s],
            "pvalue": float(m.pvalue()["treat"]), "n_obs": int(m._N), "formula": fml}


def pretrend(d: pd.DataFrame, y: str) -> dict:
    """Weekly event study over the pre-period: Curb x week dummies, last pre week omitted."""
    x = d[d["post"] == 0].copy()
    wk = ((x["day"] - x["day"].min()).dt.days // 7).astype(int)
    last = int(wk.max())
    terms = []
    for k in sorted(wk.unique()):
        if k == last:
            continue
        t = f"w{k:03d}"
        x[t] = ((wk == k) & (x["curb"] == 1)).astype(float)
        terms.append(t)
    m = pf.feols(f"{y} ~ {' + '.join(terms)} | zv + zd", data=x, vcov={"CRV1": "zone_id"})
    res = wald(m, terms, int(x["zone_id"].nunique()))
    res["n_weeks"] = len(terms)
    return res


def window(d: pd.DataFrame, pre_from: str, pre_end: str, post_start: str) -> pd.DataFrame:
    keep = ((d["day"] >= pd.Timestamp(pre_from)) & (d["day"] <= pd.Timestamp(pre_end))) | (
        d["day"] >= pd.Timestamp(post_start))
    return d[keep].assign(post=(d["day"] >= pd.Timestamp(post_start)).astype(int))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    lc, res = cfg["lyft"], path("results", cfg)
    d = load(cfg)
    daily = d.groupby(["day", "vendor_id"])[["total", "app", "street", "uber", "lyft",
                                              "code_a"]].sum().reset_index()
    daily.to_csv(res / "lyft_entry_daily.csv", index=False, lineterminator="\n")
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "label": "PRELIMINARY: two post-launch months; rerun with `make lyft-refresh`",
           "specification": "PLAN.md Amendment 4 D3, Amendment 4a (timing); DECISIONS.md",
           "design": "Curb (VendorID 2) vs CMT (VendorID 1) cabs, zone x vendor and zone x day "
                     "FE, prior-year same-weekday pickups as covariate, CRV1 by pickup zone; "
                     "CBD + Manhattan non-CBD", "windows": lc,
           "n_zones": int(d["zone_id"].nunique())}

    def block(d_w: pd.DataFrame, lyft_per_cell: float, outcomes: list[str]) -> dict:
        r = {}
        for y in outcomes:
            r[y] = did(d_w, y)
            r[y]["without_covariate"] = did(d_w, y, covariate=False)
        r["lyft_per_curb_zone_day_post"] = lyft_per_cell
        r["incrementality"] = r["total"]["coef"] / lyft_per_cell if "total" in r else None
        if "total" in r:
            s = r["total"]["se"] / lyft_per_cell
            r["incrementality_ci"] = [r["incrementality"] - Z95 * s,
                                      r["incrementality"] + Z95 * s]
        if "uber" in r:
            r["uber_displacement_per_lyft_trip"] = r["uber"]["coef"] / lyft_per_cell
        return r

    # primary: clean windows
    post_curb = d[(d["day"] >= pd.Timestamp(lc["post_start"])) & (d["curb"] == 1)]
    lyft_cell = float(post_curb["lyft"].mean())
    long_w = window(d, lc["long_pre_start"], lc["pre_end"], lc["post_start"])
    uber_w = window(d, lc["uber_pre_start"], lc["pre_end"], lc["post_start"])
    prim = block(long_w, lyft_cell, ["total", "app", "street"])
    prim.update({k: v for k, v in block(uber_w, lyft_cell, ["uber"]).items()
                 if k in ("uber", "uber_displacement_per_lyft_trip")})
    prim["pretrend"] = {y: pretrend(long_w, y) for y in ("total", "app", "street")}
    prim["pretrend"]["uber"] = pretrend(uber_w, "uber")
    out["primary_clean_windows"] = prim

    # post hoc (labelled): pre-period ends before the request_source files, because the Curb/CMT
    # ratio shifts at 2026-05-31 and reverts at 2026-07-12 inside the primary pre-window
    ph_w = window(d, lc["long_pre_start"], lc["post_hoc_pre_end"], lc["post_start"])
    ph = block(ph_w, lyft_cell, ["total", "app", "street"])
    ph["note"] = ("POST HOC, after the primary result: pre-period ends "
                  f"{lc['post_hoc_pre_end']} (before the request_source files)")
    out["post_hoc_pre_before_request_source_files"] = ph

    # log specification (added after the levels result; DECISIONS): Curb carries ~4x CMT's
    # volume and both move proportionally, so a levels DiD turns common percentage swings into
    # Curb - CMT level changes; in logs the effect is a percentage, converted to trips with the
    # Curb post-period mean: delta = actual * (1 - exp(-b))
    lg = {}
    for name, dw in (("clean_windows", long_w), ("pre_before_request_source_files", ph_w)):
        dl = dw.assign(**{f"log1p_{c}": np.log1p(dw[c]) for c in ("total", "app", "street",
                                                                   "uber", "total_py")})
        r_ = {y: did(dl, f"log1p_{y}", cov="log1p_total_py") for y in ("total", "app", "street")}
        mean_post = float(post_curb["total"].mean())
        b_, lo_, hi_ = r_["total"]["coef"], *r_["total"]["ci"]
        conv = [mean_post * (1 - np.exp(-v)) / lyft_cell for v in (b_, lo_, hi_)]
        r_.update({"curb_total_per_zone_day_post": mean_post,
                   "incrementality": conv[0], "incrementality_ci": conv[1:]})
        if name == "clean_windows":
            du = uber_w.assign(log1p_uber=np.log1p(uber_w["uber"]),
                               log1p_total_py=np.log1p(uber_w["total_py"]))
            r_["uber"] = did(du, "log1p_uber", cov="log1p_total_py")
            r_["pretrend"] = {y: pretrend(dl, f"log1p_{y}") for y in ("total", "street")}
        lg[name] = r_
    lg["note"] = "added after the levels result (scale argument above); see DECISIONS, D3"
    out["log_specification"] = lg
    wk = d.assign(week=d["day"] - pd.to_timedelta((d["day"].dt.day_of_week + 1) % 7, unit="D"))
    r = wk.pivot_table(index="week", columns="vendor_id", values=["total", "street", "app"],
                       aggfunc="sum")
    ratio = r.xs(2, axis=1, level=1) / r.xs(1, axis=1, level=1)
    out["curb_cmt_weekly_ratio"] = {str(k.date()): {c: round(float(v), 4) for c, v in row.items()}
                                    for k, row in ratio.iterrows()}

    # secondary: treatment from the code-A surge (hypothesis)
    base = d[(d["day"] >= pd.Timestamp(lc["code_a_baseline"][0]))
             & (d["day"] <= pd.Timestamp(lc["code_a_baseline"][1])) & (d["curb"] == 1)]
    a0 = base.groupby("zone_id")["code_a"].mean()
    d2 = d.assign(lyft_h=d["lyft"] + np.where(
        d["curb"] == 1, np.maximum(d["code_a"] - d["zone_id"].map(a0).fillna(0), 0), 0))
    sec_post = d2[(d2["day"] >= pd.Timestamp(lc["secondary_start"])) & (d2["curb"] == 1)]
    sec_w = window(d2, lc["long_pre_start"], pd.Timestamp(lc["secondary_start"])
                   - pd.Timedelta(days=1), lc["secondary_start"])
    sec = block(sec_w, float(sec_post["lyft_h"].mean()), ["total", "app", "street"])
    sec["note"] = ("rests on the hypothesis that Curb's code-A surge from 2026-07-09 is Lyft "
                   "trips before the HV0005 code (DECISIONS, D0)")
    out["secondary_from_code_a_surge"] = sec
    (res / "lyft_entry.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    LOG.info("D3 primary: total %.2f [%.2f, %.2f]/zone-day, Lyft %.2f/zone-day, "
             "incrementality %.2f", prim["total"]["coef"], *prim["total"]["ci"], lyft_cell,
             prim["incrementality"])


if __name__ == "__main__":
    main()
