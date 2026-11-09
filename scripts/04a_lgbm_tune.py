"""LightGBM grid on the 2023 validation year (PLAN Phase 2: modest tuning, no Optuna).

Each grid point trains one booster per quantile on [model_start, validation start) and is scored
on every hour of the validation year with early stopping (pinball loss at that quantile). Day-ahead
features of a target on day D use only days <= D-1, so scoring the whole year with one frozen
model equals daily-origin forecasting without refits. Selection: lowest mean pinball loss over the
quantiles at each quantile's best iteration. The chosen point's best iterations become the fixed
round counts of every backtest refit.

Writes results/lgbm_tuning.csv (every grid point x quantile) and results/lgbm_params.json.

Usage:
    python scripts/04a_lgbm_tune.py
"""

from __future__ import annotations

import itertools
import json
import logging
import time
from datetime import UTC, datetime

import lightgbm as lgb
import numpy as np
import pandas as pd

from taxi_shock.config import load_config, path
from taxi_shock.io import read_exog, read_modeled_panel
from taxi_shock.metrics import pinball
from taxi_shock.models.lgbm_quantile import GlobalLGBMQuantile, training_frame


def select(res: pd.DataFrame, keys: list[str], lc: dict, ms: pd.Timestamp, v0: pd.Timestamp,
           v1: pd.Timestamp) -> dict:
    """Pick the grid point with the lowest mean validation pinball; JSON-ready summary."""
    score = res.groupby(keys)["pinball_validation"].mean().rename("mean_pinball")
    best = score.idxmin()
    best = {k: v.item() if hasattr(v, "item") else v
            for k, v in zip(keys, best if isinstance(best, tuple) else (best,), strict=True)}
    sel = res.loc[(res[keys] == pd.Series(best)).all(axis=1)]
    def plain(d: dict) -> dict:
        return {k: v.item() if hasattr(v, "item") else v for k, v in d.items()}

    out = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "results/lgbm_tuning.csv",
        "train": [str(ms.date()), str((v0 - pd.Timedelta(days=1)).date())],
        "validation": [str(v0.date()), str(v1.date())],
        "selection": "lowest mean validation pinball loss over the quantiles",
        "params": {**lc["fixed"], **best},
        "rounds": {str(r["quantile"]): int(r["best_iteration"]) for _, r in sel.iterrows()},
        "early_stopping": {"rounds": lc["early_stopping_rounds"],
                           "min_delta": lc["early_stopping_min_delta"],
                           "max_rounds": lc["max_rounds"]},
        "chosen_hit_max_rounds": bool(sel["hit_max_rounds"].any()),
        "mean_pinball_by_grid_point": [{**plain(dict(zip(keys, k if isinstance(k, tuple) else (k,),
                                                         strict=True))),
                                        "mean_pinball": float(v)} for k, v in score.items()],
    }
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    mc, lc = cfg["models"], cfg["models"]["lgbm"]
    zones = json.loads((path("results", cfg) / "modeled_zones.json").read_text())["zone_ids"]
    ms = pd.Timestamp(cfg["data"]["model_start"])
    v0, v1 = (pd.Timestamp(x) for x in mc["validation_year"])
    load0 = (ms - pd.Timedelta(days=mc["feature_history_days"])).date().isoformat()
    end = (v1 + pd.Timedelta(days=1)).date().isoformat()
    db = path("warehouse", cfg)
    panel = read_modeled_panel(db, zones, load0, end, cfg)
    exog = read_exog(db, load0, end, cfg)
    qs = sorted(cfg["forecast"]["quantiles"])

    hist_tr = panel[panel["hour_ts"] < v0]
    x_tr, y_tr = training_frame(hist_tr, exog, ms)
    x_va, y_va = training_frame(panel, exog, v0)
    proto = GlobalLGBMQuantile(exog, qs, {}, {}, seed=cfg["seed"], threads=mc["threads"],
                               predict_history_days=mc["lgbm"]["predict_history_days"])
    proto.zones_ = sorted(int(z) for z in x_tr["zone_id"].unique())
    d_tr = lgb.Dataset(proto._matrix(x_tr), y_tr, categorical_feature=["zone_id"],
                       free_raw_data=False)
    d_va = lgb.Dataset(proto._matrix(x_va), y_va, categorical_feature=["zone_id"],
                       reference=d_tr, free_raw_data=False)
    m_va = proto._matrix(x_va)
    logging.info("train %d rows (%s..%s), validation %d rows", len(y_tr), ms.date(),
                 (v0 - pd.Timedelta(hours=1)), len(y_va))

    grid = lc["grid"]
    keys = sorted(grid)
    rows = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = {**lc["fixed"], **dict(zip(keys, combo, strict=True))}
        for q in qs:
            t0 = time.perf_counter()
            bp = {**proto.booster_params(q), **params, "metric": "quantile"}
            b = lgb.train(bp, d_tr, num_boost_round=lc["max_rounds"], valid_sets=[d_va],
                          callbacks=[lgb.early_stopping(lc["early_stopping_rounds"],
                                                        verbose=False,
                                                        min_delta=lc["early_stopping_min_delta"])])
            pred = np.clip(b.predict(m_va, num_iteration=b.best_iteration), 0, None)
            rows.append({**dict(zip(keys, combo, strict=True)), "quantile": q,
                         "best_iteration": int(b.best_iteration),
                         "pinball_validation": pinball(y_va, pred, q),
                         "hit_max_rounds": b.best_iteration >= lc["max_rounds"],
                         "seconds": round(time.perf_counter() - t0, 1)})
            logging.info("%s q=%s: %d rounds, pinball %.4f (%.0fs)", params, q,
                         rows[-1]["best_iteration"], rows[-1]["pinball_validation"],
                         rows[-1]["seconds"])
    res = pd.DataFrame(rows)
    res.to_csv(path("results", cfg) / "lgbm_tuning.csv", index=False, lineterminator="\n")
    out = select(res, keys, lc, ms, v0, v1)
    (path("results", cfg) / "lgbm_params.json").write_text(json.dumps(out, indent=2) + "\n")
    logging.info("chosen %s, rounds %s", out["params"], out["rounds"])


if __name__ == "__main__":
    main()
