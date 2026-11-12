"""Size of the event-study pre-trend test under parallel trends (Phase 4 diagnostic).

Simulates zone-week panels shaped like the real designs (`causal.pretrend_size.designs`: 38
treated / 23 control zones = the demand DiD's clusters, and 20 / 20), weekly 2023-01 -> 2026-09,
zone effects, a common time path, AR(1) noise (`ar_rho`, `noise_sd`) and NO differential
pre-trend, then applies
taxi_shock.causal.event_study (monthly bins, zone + week FE, clustered by zone) and records how
often the pre-registered F(q, G - 1) and the Hotelling-type F*(q, G - q) reject at 5% and 1%.

Writes results/pretrend_test_size.json.

Usage:
    python scripts/07d_pretrend_size.py [--reps N]   (default: causal.pretrend_size.reps)
"""

from __future__ import annotations

import argparse
import json
import logging
import warnings
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from taxi_shock.causal.event_study import event_study
from taxi_shock.config import load_config, path


def simulated_panel(n_tr: int, n_ct: int, policy: str, rng: np.random.Generator,
                    rho: float, sd: float) -> pd.DataFrame:
    weeks = pd.date_range("2023-01-01", "2026-09-20", freq="7D")
    ev = ((weeks - pd.Timestamp(policy)).days // 7).to_numpy()
    rows = []
    for z in range(n_tr + n_ct):
        e = np.zeros(len(weeks))
        u = rng.normal(0, sd, len(weeks))
        for i in range(1, len(e)):
            e[i] = rho * e[i - 1] + u[i]
        y = rng.normal(5, 1) + 0.002 * ev + 0.1 * np.sin(ev / 8) + e
        rows.append(pd.DataFrame({"zone_id": z, "week_start": weeks, "event_week": ev,
                                  "treated": int(z < n_tr), "y": y}))
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warnings.filterwarnings("ignore")
    cfg = load_config()
    ps = cfg["causal"]["pretrend_size"]
    reps = args.reps or int(ps["reps"])
    policy = cfg["data"]["policy_date"]
    rng = np.random.default_rng(cfg["seed"])
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "reps": reps, "design": f"zone + common time path + AR(1) noise (rho {ps['ar_rho']}, "
           f"sd {ps['noise_sd']}), no differential trend; monthly-bin event study, zone + week "
           "FE, CRV1 by zone; 24 pre-period restrictions", "designs": []}
    for n_tr, n_ct in ps["designs"]:
        p, ph = [], []
        for _ in range(reps):
            panel = simulated_panel(n_tr, n_ct, policy, rng, ps["ar_rho"], ps["noise_sd"])
            _, info = event_study(panel, "y", "zone_id",
                                  ["zone_id"], policy, "month")
            p.append(info["pretrend"]["p_F"])
            ph.append(info["pretrend"]["p_F_hotelling"])
        p, ph = np.array(p), np.array(ph)
        row = {"treated_zones": n_tr, "control_zones": n_ct,
               "reject_5pct_F": float((p < 0.05).mean()),
               "reject_1pct_F": float((p < 0.01).mean()),
               "reject_5pct_F_hotelling": float((ph < 0.05).mean()),
               "reject_1pct_F_hotelling": float((ph < 0.01).mean()),
               "min_p_F": float(p.min()), "min_p_F_hotelling": float(ph.min())}
        out["designs"].append(row)
        logging.info("%s", row)
    (path("results", cfg) / "pretrend_test_size.json").write_text(json.dumps(out, indent=2)
                                                                  + "\n")


if __name__ == "__main__":
    main()
