"""Phase 4b, C3 (Amendment 3): synthetic control for CBD demand.

Treated unit: the CBD (weekly total pickups of the CBD zones). Donors: non-CBD zones with a 2024
mean of >= `synth.min_donor_weekly` pickups per week, the donut-excluded zones left out. Outcome:
log weekly pickups demeaned per unit over the pre-period (the CBD total is far larger than any
donor; demeaned logs match percentage paths). Weights: pysyncon `Synth` with every pre-period
week as predictor and custom_V = identity (minimises the pre-period MSPE). Specification fixed
in DECISIONS.md (Phase 4b, C3) before the run.

Writes results/synth_control.json (pre RMSPE, weights, post gaps, RMSPE ratio, in-space placebo
rank, in-time placebo) and results/synth_control_paths.csv (weekly gap of the CBD and of every
in-space placebo, plus the CBD's demeaned actual and synthetic series).

Usage:
    python scripts/07f_synth_control.py
"""

from __future__ import annotations

import json
import logging
import warnings
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from pysyncon import Synth

from taxi_shock.causal.panel import demand_panel
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("synth")


def outcome_matrix(cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Weeks x units of log weekly pickups (column 'CBD' = the CBD total)."""
    sc = cfg["synth"]
    zs = pd.read_csv(path("results", cfg) / "zone_summary.csv")
    donut_out = set(cfg["causal"]["control_groups"]["manhattan_non_cbd_donut"]["exclude_zones"])
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        w = demand_panel(con, cfg)
    cbd = set(zs.loc[zs["is_cbd"], "zone_id"])
    y24 = w[w["week_start"].dt.year == 2024].groupby("zone_id")["pickups"].mean()
    donors = sorted(z for z, v in y24.items() if v >= sc["min_donor_weekly"] and z not in cbd
                    and z not in donut_out)
    wide = w[w["zone_id"].isin(donors)].pivot_table(index="week_start", columns="zone_id",
                                                    values="pickups", aggfunc="sum")
    wide["CBD"] = w[w["zone_id"].isin(cbd)].groupby("week_start")["pickups"].sum()
    if (wide <= 0).any().any():
        raise ValueError("a donor has a zero week; log outcome undefined")
    info = {"donors": donors, "n_cbd_zones": len(cbd),
            "donor_rule": f"non-CBD zones with 2024 mean >= {sc['min_donor_weekly']} pickups/"
                          f"week, excluding {sorted(donut_out)}"}
    return np.log(wide), info


def fit_one(y: pd.DataFrame, treated, donors: list, pre: pd.Index
            ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Synthetic path of `treated` from `donors` on demeaned logs; (gap, weights, actual)."""
    d = y[[treated, *donors]] - y.loc[pre, [treated, *donors]].mean()
    x0, x1 = d.loc[pre, donors], d.loc[pre, treated]
    s = Synth()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s.fit(X0=x0, X1=x1, Z0=x0, Z1=x1, custom_V=np.ones(len(pre)))
    wts = pd.Series(np.asarray(s.W), index=donors)
    synth = d[donors] @ wts
    return d[treated] - synth, wts, d[treated]


def rmspe(g: pd.Series) -> float:
    return float(np.sqrt((g ** 2).mean()))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    sc, res = cfg["synth"], path("results", cfg)
    y, info = outcome_matrix(cfg)
    donors = info["donors"]
    weeks = y.index
    pre = weeks[(weeks >= pd.Timestamp(sc["pre_period"][0]))
                & (weeks <= pd.Timestamp(sc["pre_period"][1]))]
    post = weeks[(weeks >= pd.Timestamp(cfg["data"]["policy_date"]))
                 & (weeks <= pd.Timestamp(sc["post_end"]))]
    gap, wts, act = fit_one(y, "CBD", donors, pre)
    paths = [pd.DataFrame({"week_start": weeks, "unit": "CBD", "actual": act.to_numpy(),
                           "synthetic": (act - gap).to_numpy(), "gap": gap.to_numpy()})]
    ratios, pre_fit = {}, {}
    for z in donors:                                   # in-space placebos
        g, _, _ = fit_one(y, z, [d for d in donors if d != z], pre)
        ratios[z] = rmspe(g[post]) / rmspe(g[pre])
        pre_fit[z] = rmspe(g[pre])
        paths.append(pd.DataFrame({"week_start": weeks, "unit": str(z), "gap": g.to_numpy()}))
    cbd_ratio = rmspe(gap[post]) / rmspe(gap[pre])
    rank = 1 + sum(r >= cbd_ratio for r in ratios.values())
    pre_cbd = rmspe(gap[pre])

    def restricted(mult: float) -> dict:
        """Abadie et al. (2010): placebos whose pre-period MSPE is <= mult x the CBD's."""
        keep = [z for z in donors if pre_fit[z] ** 2 <= mult * pre_cbd ** 2]
        r = 1 + sum(ratios[z] >= cbd_ratio for z in keep)
        return {"mspe_multiple": mult, "n": len(keep), "cbd_rank": r,
                "p_value": r / (len(keep) + 1)}
    # in-time placebo: fake treatment week, pre = weeks before it (from the window start)
    fake = pd.Timestamp(sc["in_time_placebo_week"])
    pre_t = weeks[(weeks >= pd.Timestamp(sc["pre_period"][0])) & (weeks < fake)]
    post_t = weeks[(weeks >= fake) & (weeks <= pd.Timestamp(sc["pre_period"][1]))]
    gap_t, _, _ = fit_one(y, "CBD", donors, pre_t)
    splits = {k: (pd.Timestamp(a), pd.Timestamp(b)) for k, (a, b) in
              cfg["causal"]["post_splits"].items()}
    out = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "specification": "DECISIONS.md, Phase 4b (C3)", "library": "pysyncon 1.7.0",
        **{k: v for k, v in info.items() if k != "donors"}, "n_donors": len(donors),
        "pre_period": [str(pre.min().date()), str(pre.max().date())], "n_pre_weeks": len(pre),
        "post_period": [str(post.min().date()), str(post.max().date())],
        "n_post_weeks": len(post),
        "pre_rmspe": rmspe(gap[pre]), "post_rmspe": rmspe(gap[post]),
        "post_pre_rmspe_ratio": cbd_ratio,
        "post_gap_mean_log": float(gap[post].mean()),
        "post_gap_mean_pct": float(np.expm1(gap[post].mean())),
        "post_gap_by_period": {k: {"mean_log": float(gap[(weeks >= a) & (weeks <= b)].mean()),
                                   "pct": float(np.expm1(gap[(weeks >= a) & (weeks <= b)]
                                                         .mean()))}
                               for k, (a, b) in splits.items()},
        "weights": {str(k): round(float(v), 4) for k, v in wts.sort_values(ascending=False)
                    .items() if v > 0.001},
        "in_space_placebos": {"n": len(ratios), "cbd_rank": rank,
                              "p_value": rank / (len(ratios) + 1),
                              "ratio_quantiles": {q: float(np.quantile(list(ratios.values()), q))
                                                  for q in (0.5, 0.9, 0.95)}},
        "in_time_placebo": {"fake_week": str(fake.date()), "pre_rmspe": rmspe(gap_t[pre_t]),
                            "post_rmspe": rmspe(gap_t[post_t]),
                            "post_gap_mean_log": float(gap_t[post_t].mean()),
                            "post_gap_mean_pct": float(np.expm1(gap_t[post_t].mean()))},
        "decision_rule": "if p_value > 0.10 the method cannot resolve the question",
    }
    out["resolves"] = out["in_space_placebos"]["p_value"] <= 0.10
    # pre-fit gate (Stanley 2026-11-12: "its pre-fit quality decides whether it can speak at
    # all"; rule fixed in DECISIONS.md before the run)
    med_pre = float(np.median(list(pre_fit.values())))
    gate_fit = pre_cbd <= med_pre
    # the method must not invent a gap where there is no policy: the in-time placebo's mean
    # post gap (log points) must lie within the CBD's own pre-period fit error
    gate_time = abs(float(gap_t[post_t].mean())) <= pre_cbd
    out["pre_fit"] = {"cbd_pre_rmspe": pre_cbd, "donor_pre_rmspe_median": med_pre,
                      "cbd_pre_rmspe_rank_among_units": 1 + sum(v < pre_cbd
                                                               for v in pre_fit.values()),
                      "donor_pre_rmspe_quantiles": {q: float(np.quantile(
                          list(pre_fit.values()), q)) for q in (0.1, 0.5, 0.9)},
                      "restricted_placebos": [restricted(5.0), restricted(2.0)],
                      "gate_cbd_fit_at_most_donor_median": bool(gate_fit),
                      "gate_in_time_mean_gap_within_cbd_pre_rmspe": bool(gate_time),
                      "rule": "C3 speaks only if both gates hold; otherwise the method cannot "
                              "resolve the question"}
    out["can_speak"] = bool(gate_fit and gate_time)
    (res / "synth_control.json").write_text(json.dumps(out, indent=2) + "\n")
    pd.concat(paths, ignore_index=True).to_csv(res / "synth_control_paths.csv", index=False,
                                               lineterminator="\n", float_format="%.6g")
    LOG.info("C3: pre RMSPE %.4f (donor median %.4f), post gap %.4f (%.2f%%), ratio %.2f, "
             "rank %d of %d, p %.3f, in-time %.2f%%, can speak %s", pre_cbd, med_pre,
             out["post_gap_mean_log"], out["post_gap_mean_pct"] * 100, cbd_ratio, rank,
             len(ratios) + 1, out["in_space_placebos"]["p_value"],
             out["in_time_placebo"]["post_gap_mean_pct"] * 100, out["can_speak"])


if __name__ == "__main__":
    main()
