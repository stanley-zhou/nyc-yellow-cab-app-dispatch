"""Export the Chronos-2 input bundle (PLAN Phase 2: "reads the small panel Parquet").

Writes data/processed/chronos/ (committed: small) and the zip Stanley uploads to Google Drive:
    pickups.parquet      zone_id, hour_ts, pickups for the modeled zones
                         (results/modeled_zones.json) over every grid hour from
                         context_hours before the first origin to the end of the panel
    covariates.parquet   hour_ts + city-wide calendar and observed weather covariates, same hours
    manifest.json        sha256 of each file and of the Colab script, and every setting the Colab
                         script uses (from config/project.yaml -> chronos, forecast)
    chronos_bundle.zip   the three files + scripts/05_chronos_colab.py

Usage:
    python scripts/05a_chronos_export.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect

COLAB_SCRIPT = "scripts/05_chronos_colab.py"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    ch = cfg["chronos"]
    zones = json.loads((path("results", cfg) / "modeled_zones.json").read_text())["zone_ids"]
    first_origin = pd.Timestamp(ch["origins"][0])
    out = path("processed", cfg) / "chronos"
    out.mkdir(parents=True, exist_ok=True)

    with connect(path("warehouse", cfg), cfg=cfg) as con:
        hours = con.execute("select hour_ts from int_hours order by 1").df()["hour_ts"]
        pos = int(hours.searchsorted(first_origin))
        if pos < int(ch["context_hours"]):
            raise ValueError("the panel starts less than context_hours before the first origin")
        start = hours.iloc[pos - int(ch["context_hours"])]
        con.execute("create temp table z as select unnest(?::integer[]) as zone_id", [zones])
        pk = con.execute("""
            select f.zone_id::smallint as zone_id, f.hour_ts, f.pickups::float as pickups
            from fct_hourly_zone_demand f join z using (zone_id)
            where f.hour_ts >= ? order by zone_id, hour_ts""", [start]).df()
        wx = ", ".join(f"w.{c}" for c in ch["weather_covariates"])
        cov = con.execute(f"""
            select h.hour_ts, hour(h.hour_ts) as hour, isodow(h.hour_ts) - 1 as dow,
                   isodow(h.hour_ts) >= 6 as is_weekend,
                   hol.date is not null as is_holiday, {wx}
            from int_hours h
            left join stg_weather w using (hour_ts)
            left join (select distinct date from holidays_ny) hol
                   on hol.date = cast(h.hour_ts as date)
            where h.hour_ts >= ? order by 1""", [start]).df()
    cov["hour_sin"] = np.sin(2 * np.pi * cov["hour"] / 24)
    cov["hour_cos"] = np.cos(2 * np.pi * cov["hour"] / 24)
    cov["dow_sin"] = np.sin(2 * np.pi * cov["dow"] / 7)
    cov["dow_cos"] = np.cos(2 * np.pi * cov["dow"] / 7)
    cov[["is_weekend", "is_holiday"]] = cov[["is_weekend", "is_holiday"]].astype("float32")
    names = ch["calendar_covariates"] + ch["weather_covariates"]
    cov = cov[["hour_ts", *names]].astype({c: "float32" for c in names})
    if cov[names].isna().any().any():
        raise ValueError("NaN in Chronos covariates: " +
                         str(cov[names].isna().sum()[lambda s: s > 0].to_dict()))
    n_h = cov["hour_ts"].nunique()
    if len(pk) != len(zones) * n_h:
        raise ValueError(f"pickups: {len(pk)} rows, expected {len(zones)} x {n_h}")

    files = {"pickups.parquet": pk, "covariates.parquet": cov}
    for name, df in files.items():
        df.to_parquet(out / name, index=False, compression="zstd")
    script = repo_root() / COLAB_SCRIPT
    manifest = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "data/warehouse.duckdb (fct_hourly_zone_demand, int_hours, stg_weather, "
                  "holidays_ny); zones from results/modeled_zones.json",
        "model_id": ch["model_id"],
        "package": ch["package"],
        "context_hours": int(ch["context_hours"]),
        "origins": ch["origins"],
        "test_period": cfg["forecast"]["backtest"]["pre_shock_test"],
        "quantiles": cfg["forecast"]["quantiles"],
        "calendar_covariates": ch["calendar_covariates"],
        "weather_covariates": ch["weather_covariates"],
        "variants": ch["variants"],
        "batch_size": int(ch["batch_size"]),
        "n_zones": len(zones),
        "first_hour": str(cov["hour_ts"].min()), "last_hour": str(cov["hour_ts"].max()),
        "n_hours": int(n_h),
        "files": {n: {"sha256": _sha(out / n), "rows": len(df)} for n, df in files.items()},
        "colab_script_sha256": _sha(script),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    bundle = repo_root() / ch["bundle"]
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as zf:
        for n in [*files, "manifest.json"]:
            zf.write(out / n, arcname=n)
        zf.write(script, arcname=script.name)
    logging.info("chronos bundle: %d zones x %d hours (%s..%s) -> %s (%.1f MB)", len(zones), n_h,
                 manifest["first_hour"], manifest["last_hour"], bundle,
                 bundle.stat().st_size / 1e6)


if __name__ == "__main__":
    main()
