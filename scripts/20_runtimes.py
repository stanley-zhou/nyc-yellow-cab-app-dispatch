"""Phase 7: collect measured runtimes into results/runtimes.json (README "Runtimes").

Two kinds of source, kept apart in the output:
  measured   compute times recorded by the pipeline itself in results/ files (refit seconds,
             Colab chunk seconds, smoke stage seconds, frozen-model fit seconds)
  log_span   first to last timestamp of a log in logs/ (git-ignored, machine-local) for runs that
             ran once from start to finish; logs of resumed or partial runs (the raw download,
             the HVFHV stream, which skip finished months) are not used, because their span is not
             the runtime of the step; nor are the Phase-5 refit logs, whose first timestamp
             follows the first fit (results/adaptation_refits.csv measures them)

On a machine without the logs the previous log_span entries are kept, so the file can be
regenerated from a fresh clone without losing them. Hardware from results/machine_resources.json
and results/chronos_run.json.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

import pandas as pd

from taxi_shock.config import load_config, path, repo_root

LOG = logging.getLogger("runtimes")
TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
# logs of runs that went from start to finish in one go (DECISIONS.md, Phase 7)
COMPLETE_LOGS = {
    "lgbm_tune_run2": "Phase 2: LightGBM grid on 2023 (04a_lgbm_tune.py)",
    "backtest_sn_stat": "Phase 2: seasonal-naive and statistical backtests (04_backtest.py)",
    "backtest_lgbm": "Phase 2: LightGBM rolling-origin backtests, both windows (04_backtest.py)",
    "evaluate": "Phase 2: conformal calibration and metrics (04b_evaluate.py)",
    "shock": "Phase 3: frozen model and monitors (06_shock.py)",
    "d2_r2": "Amendment 4 D2: incrementality DML, 25 repetitions (12_incrementality.py)",
    "adapt_eval": "Phase 5: evaluation and bootstrap (08_adapt.py --evaluate)",
}


def log_span(f) -> float | None:
    stamps = [m.group(1) for line in f.read_text(errors="replace").splitlines()
              if (m := TS.match(line))]
    if len(stamps) < 2:
        return None
    a, b = pd.Timestamp(stamps[0]), pd.Timestamp(stamps[-1])
    return float((b - a).total_seconds())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    res = path("results", cfg)
    out_f = res / "runtimes.json"
    old = json.loads(out_f.read_text()) if out_f.exists() else {}
    mach = json.loads((res / "machine_resources.json").read_text())
    measured: dict = {}

    sm = json.loads((res / "smoke" / "smoke_run.json").read_text())
    measured["smoke"] = {"seconds": sm["total_seconds"], "source": "results/smoke/smoke_run.json",
                         "what": "make smoke: one sample month end to end"}
    tune = pd.read_csv(res / "lgbm_tuning.csv")
    measured["lgbm_tuning"] = {"seconds": float(tune["seconds"].sum()), "fits": len(tune),
                               "source": "results/lgbm_tuning.csv",
                               "what": "Phase 2 LightGBM grid, sum of fit times"}
    rf = pd.read_csv(res / "lgbm_refits.csv")
    measured["lgbm_backtest_refits"] = {
        f"{w}_{p}": {"seconds": float(x["seconds"].sum()), "refits": len(x)}
        for (w, p), x in rf.groupby(["window", "period"])} | {
        "source": "results/lgbm_refits.csv", "what": "Phase 2 monthly refits, sum of fit times"}
    fm = json.loads((res / "frozen_model.json").read_text())
    fit = next((v for k, v in fm.items() if isinstance(v, dict) and "seconds" in v), None)
    if fit is not None:
        measured["frozen_model_fit"] = {"seconds": float(fit["seconds"]),
                                        "source": "results/frozen_model.json",
                                        "what": "Phase 3 frozen LightGBM, one fit"}
    for name, f in (("chronos_main", "chronos_run.json"),
                    ("chronos_calib_2023", "chronos_run_calib_2023.json")):
        if (res / f).exists():
            run = json.loads((res / f).read_text())
            sec = list(run.get("chunk_seconds_this_session", {}).values())
            measured[name] = {"seconds": float(sum(sec)), "chunks": len(sec),
                              "gpu": run.get("environment", {}).get("gpu", ""),
                              "source": f"results/{f}",
                              "what": "Chronos-2 inference on Colab, sum of chunk times "
                                      "(both covariate variants)"}
    ar = pd.read_csv(res / "adaptation_refits.csv")
    measured["adaptation_refits"] = {
        s: {"seconds": float(x["wall_seconds"].sum()), "refits": len(x)}
        for s, x in ar.groupby("strategy")} | {
        "source": "results/adaptation_refits.csv", "what": "Phase 5 monthly refits, wall time"}

    spans = dict(old.get("log_span", {}))
    logs = repo_root() / "logs"
    for name, what in COMPLETE_LOGS.items():
        f = logs / f"{name}.log"
        if f.exists() and (s := log_span(f)) is not None:
            spans[name] = {"seconds": s, "what": what, "source": f"logs/{name}.log (local)"}
    out = {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "hardware": {"local": f"WSL2, {mach['cpu_count']} cores, "
                                 f"{mach['mem_total_gib']} GiB RAM", "colab": "NVIDIA L4"},
           "note": "measured = compute time recorded by the pipeline; log_span = wall time of "
                   "runs that went start to finish once (resumed runs excluded)",
           "measured": measured, "log_span": spans}
    out_f.write_text(json.dumps(out, indent=2) + "\n")
    LOG.info("wrote %s", out_f)


if __name__ == "__main__":
    main()
