"""Size a designed experiment that could measure the incrementality of app dispatch.

The experiment-design section (PLAN Amendment 1, A4, given its subject by Amendment 5): how the
incrementality of app dispatch could be measured with a designed experiment, and the sample size
the observed variance implies. Design only; no new data.

Estimand (as in the incrementality estimate, D2): theta = 1 + d street / d app = the share of
app-dispatched trips that would not have happened otherwise. If app dispatch is switched off for
a unit, total pickups fall by theta x (the app trips it would have had); so the experiment
estimates theta = (total_on - total_off) / app_on.

Design 1, switchback (zone x time block). Units: pickup zone x `block_hours` block of the CBD and
Manhattan non-CBD zones; dispatch eligibility switched on/off at random per block. Noise: residual
sd of block totals after zone x day-of-week x block-of-day effects and date effects, estimated on
`period` (the most recent months before Lyft's entry). With n blocks, half switched off,
SE(total_on - total_off) = 2 sigma / sqrt(n); theta's SE = that / mean app trips per on-block;
MDE = (z_{1-a/2} + z_power) x SE. Reported: the n that gives theta an MDE of each
`target_theta_mde`, in zone-block counts and in calendar days over the design zones, with and
without a design effect for serial correlation of adjacent blocks of a zone (lag-1 autocorrelation
rho of the residuals; DEFF = 1 + rho, conservative for alternating assignments).

Design 2, staggered vendor rollout (dispatch enabled cab group by cab group). The observed analogue
is Lyft's entry (D3: Lyft on Curb vs CMT cabs): its SE per zone-day over its post-period scales
with 1 / sqrt(post days); reported: theta's MDE with that design's two post months and the
post-period length needed for each target MDE (log specification, results/lyft_entry.json).

Reads: warehouse tables int_trips_valid and dim_zones, results/lyft_entry.json; config keys
`experiment`, `quality.flex_fare_payment_type`, `data.event_study_window`.
Writes results/experiment_design.json.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from scipy import stats

from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("experiment")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    ec, res = cfg["experiment"], path("results", cfg)
    mult = float(stats.norm.ppf(1 - ec["size"] / 2) + stats.norm.ppf(ec["power"]))
    bh = int(ec["block_hours"])
    lo, hi = ec["period"]
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        d = con.execute(f"""
            with z as (select zone_id from dim_zones
                       where zone_group in ('cbd', 'manhattan_non_cbd'))
            select v.pu_zone_id as zone_id, cast(v.pu_hour as date) as day,
                   hour(v.pu_hour) // {bh} as block, count(*) as total,
                   count(*) filter (where v.payment_type = {int(cfg['quality']
                                                               ['flex_fare_payment_type'])})
                       as app
            from int_trips_valid v join z on z.zone_id = v.pu_zone_id
            where v.pu_hour >= timestamp '{lo}' and v.pu_hour < timestamp '{hi}' + interval 1 day
            group by all""").df()
    d["day"] = pd.to_datetime(d["day"])
    zones = d["zone_id"].unique()
    days = pd.date_range(lo, hi, freq="D")
    idx = pd.MultiIndex.from_product([zones, days, range(24 // bh)],
                                     names=["zone_id", "day", "block"])
    d = d.set_index(["zone_id", "day", "block"]).reindex(idx, fill_value=0).reset_index()
    d["dow"] = d["day"].dt.day_of_week
    # residual of block totals after zone x dow x block and date effects (two-way demeaning)
    cell = d.groupby(["zone_id", "dow", "block"])["total"].transform("mean")
    r = d["total"] - cell
    r = r - r.groupby(d["day"]).transform("mean")
    sigma = float(r.std(ddof=1))
    d["r"] = r
    rho = float(d.sort_values(["zone_id", "day", "block"]).groupby("zone_id")["r"].apply(
        lambda s: s.autocorr(1)).mean())
    app_mean = float(d["app"].mean())
    n_zones, blocks_per_day = len(zones), 24 // bh

    def n_for(target: float, deff: float) -> int:
        # MDE_theta = mult * 2 sigma sqrt(deff) / (sqrt(n) * app_mean)  ->  solve for n
        return int(np.ceil((mult * 2 * sigma * np.sqrt(deff) / (target * app_mean)) ** 2))

    sw = {"units": f"pickup zone x {bh}-hour block, CBD + Manhattan non-CBD",
          "variance_period": [lo, hi], "n_zones": int(n_zones),
          "residual_sd_block_total": sigma, "lag1_autocorrelation_residuals": rho,
          "mean_app_trips_per_block": app_mean,
          "mean_total_trips_per_block": float(d["total"].mean()),
          "mde_multiplier": mult, "size": ec["size"], "power": ec["power"], "targets": {}}
    for t in ec["target_theta_mde"]:
        row = {}
        for name, deff in (("no_design_effect", 1.0), ("design_effect_1_plus_rho",
                                                       1.0 + max(rho, 0.0))):
            n = n_for(float(t), deff)
            row[name] = {"zone_blocks": n,
                         "days_over_all_design_zones": float(n / (n_zones * blocks_per_day))}
        sw["targets"][str(t)] = row

    ly = json.loads((res / "lyft_entry.json").read_text())["log_specification"]["clean_windows"]
    lw = json.loads((res / "lyft_entry.json").read_text())["windows"]
    post_days = int((pd.Timestamp(cfg["data"]["event_study_window"][1])
                     - pd.Timestamp(lw["post_start"])).days + 1)
    lo_i, hi_i = ly["incrementality_ci"]
    se_now = (hi_i - lo_i) / (2 * 1.959963984540054)
    mde_now = mult * se_now
    st = {"observed_analogue": "D3, Lyft on Curb vs CMT cabs (log specification, clean windows)",
          "post_days": post_days, "theta_se": se_now, "theta_mde": mde_now,
          "post_days_needed": {str(t): int(np.ceil(post_days * (mde_now / float(t)) ** 2))
                               for t in ec["target_theta_mde"]},
          "assumption": "SE falls with 1/sqrt(post days); the pre-trend failure of the "
                        "observational version is what randomisation of the rollout removes"}
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "specification": "PLAN Amendment 1 A4 and Amendment 5; design only, no new data",
           "estimand": "theta = (total_on - total_off) / app_on",
           "switchback": sw, "staggered_vendor_rollout": st}
    (res / "experiment_design.json").write_text(json.dumps(out, indent=2) + "\n")
    LOG.info("switchback sigma %.1f, app/block %.1f, rho %.2f; n for MDE 0.1: %s", sigma,
             app_mean, rho, sw["targets"].get("0.1"))


if __name__ == "__main__":
    main()
