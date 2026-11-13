"""Amendment 4, D0: is Flex Fare (payment_type 0) a usable label for app-dispatched trips?

Validation window: the yellow files that carry `request_source` (channel.label_months). Records as
in C1 (07e_app_dispatch.py): every record with a valid pickup zone and a pickup inside its file's
month. For each month x zone group (and overall, and by VendorID):

    P(Flex | HV)   HV = request_source in channel.hv_codes (Uber, Lyft)
    P(HV | Flex)
    P(Flex | any)  any = request_source not NULL (every e-hail origin code)
    P(any | Flex)

Gate (Amendment 4): both HV rates >= channel.gate.min_rate overall and in every zone group with
>= channel.gate.min_group_share of the trips -> Flex is the app label for 2023-01 -> 2026-05;
otherwise channel analyses are restricted to 2026-06+.

Step dating: weekly Flex share by zone group from the warehouse mart fct_weekly_zone_vendor (the
valid in-grid trip set of the panel), 2023-01 -> last complete week; a step at week t is the mean
share of the `step_window_weeks` weeks from t minus the mean of the weeks before t; the largest
`step_top_n` local maxima of |step| per group (>= 2 windows apart) are listed. Causes are not
inferred here; candidate causes are recorded in DECISIONS.md as hypotheses.

Writes results/channel_label_validation.json, results/flex_share_weekly.csv,
results/flex_vendor_weekly.csv (zone group x VendorID x week), results/request_source_daily.csv
(day x VendorID x code, all records of the validation files).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import duckdb
import pandas as pd

from taxi_shock.causal.panel import full_weeks
from taxi_shock.config import load_config, path
from taxi_shock.io import connect

LOG = logging.getLogger("channel_label")


def label_records(cfg: dict) -> pd.DataFrame:
    """Counts per month x pickup zone x VendorID x request_source x Flex flag."""
    ch = cfg["channel"]
    lo, hi = cfg["zones"]["valid_ids"]
    flex = int(cfg["quality"]["flex_fare_payment_type"])
    con = duckdb.connect()
    parts = []
    for m in pd.period_range(*ch["label_months"], freq="M"):
        f = path("raw_yellow", cfg) / f"yellow_tripdata_{m}.parquet"
        parts.append(con.execute(f"""
            select '{m}' as month, PULocationID::integer as zone_id, VendorID::integer as vendor_id,
                   coalesce(request_source, 'NULL') as code, (payment_type = {flex}) as flex,
                   count(*) as n
            from read_parquet('{f.as_posix()}')
            where PULocationID between {lo} and {hi}
              and tpep_pickup_datetime >= ? and tpep_pickup_datetime < ?
            group by all""", [m.to_timestamp(), (m + 1).to_timestamp()]).df())
    return pd.concat(parts, ignore_index=True)


def rates(d: pd.DataFrame, hv: list[str]) -> dict:
    is_hv, is_any = d["code"].isin(hv), d["code"] != "NULL"
    fl = d["flex"].fillna(False).astype(bool)
    n = d["n"]

    def share(num, den):
        return float(n[num & den].sum() / n[den].sum()) if n[den].sum() else None

    return {"n": int(n.sum()), "n_flex": int(n[fl].sum()), "n_hv": int(n[is_hv].sum()),
            "n_any": int(n[is_any].sum()),
            "p_flex_given_hv": share(fl, is_hv), "p_hv_given_flex": share(is_hv, fl),
            "p_flex_given_any": share(fl, is_any), "p_any_given_flex": share(is_any, fl),
            "flex_share": float(n[fl].sum() / n.sum()), "hv_share": float(n[is_hv].sum() / n.sum())}


def steps(s: pd.Series, k: int, top: int) -> list[dict]:
    """Largest local maxima of |mean(next k) - mean(previous k)| (weeks >= 2k apart)."""
    v = s.to_numpy()
    out = []
    for i in range(k, len(v) - k + 1):
        out.append((s.index[i], float(v[i:i + k].mean() - v[i - k:i].mean())))
    st = pd.Series(dict(out))
    picked = []
    for wk in st.abs().sort_values(ascending=False).index:
        if all(abs((wk - p).days) >= 14 * k for p in picked):
            picked.append(wk)
        if len(picked) == top:
            break
    return [{"week_start": str(w.date()), "step": float(st[w]),
             "share_before": float(s[s.index < w].iloc[-k:].mean()),
             "share_after": float(s[s.index >= w].iloc[:k].mean())} for w in sorted(picked)]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    ch, res = cfg["channel"], path("results", cfg)
    zs = pd.read_csv(res / "zone_summary.csv")[["zone_id", "zone_group"]]
    d = label_records(cfg).merge(zs, on="zone_id", how="left")
    hv = list(ch["hv_codes"])
    total = d["n"].sum()
    groups = {g: {"trip_share": float(x["n"].sum() / total), **rates(x, hv)}
              for g, x in d.groupby("zone_group")}
    by_month = {m: {"overall": rates(x, hv),
                    **{g: rates(y, hv) for g, y in x.groupby("zone_group")}}
                for m, x in d.groupby("month")}
    by_vendor = {str(v): rates(x, hv) for v, x in d.groupby("vendor_id")}
    codes = (d.groupby(["code", "vendor_id"])
             .agg(n=("n", "sum"), n_flex=("n", lambda s: int(s[d.loc[s.index, "flex"]
                                                                 .fillna(False)].sum())))
             .reset_index())
    codes["p_flex"] = codes["n_flex"] / codes["n"]
    overall = rates(d, hv)
    g = ch["gate"]
    checked = {k: v for k, v in groups.items() if v["trip_share"] >= g["min_group_share"]}
    ok = {k: (v["p_flex_given_hv"] >= g["min_rate"] and v["p_hv_given_flex"] >= g["min_rate"])
          for k, v in {"overall": overall, **checked}.items()}
    passed = all(ok.values())

    # weekly Flex share by zone group (valid in-grid trips; complete weeks)
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        w = con.execute("""
            select v.week_start, z.zone_group, sum(v.pickups) as pickups,
                   sum(v.pickups_flex) as pickups_flex
            from fct_weekly_zone_vendor v join dim_zones z using (zone_id)
            group by all""").df()
    w["week_start"] = pd.to_datetime(w["week_start"])
    w = full_weeks(w, cfg)                         # complete weeks of the 2023-01 -> 2026-09 window
    allg = w.groupby("week_start")[["pickups", "pickups_flex"]].sum().assign(zone_group="all")
    w = pd.concat([w, allg.reset_index()], ignore_index=True)
    w["flex_share"] = w["pickups_flex"] / w["pickups"]
    w.sort_values(["zone_group", "week_start"]).to_csv(
        res / "flex_share_weekly.csv", index=False, lineterminator="\n", float_format="%.6g")
    # weekly pickups and Flex share by zone group x VendorID (composition checks)
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        wv = con.execute("""
            select v.week_start, z.zone_group, v.vendor_id, sum(v.pickups) as pickups,
                   sum(v.pickups_flex) as pickups_flex
            from fct_weekly_zone_vendor v join dim_zones z using (zone_id)
            group by all""").df()
    wv["week_start"] = pd.to_datetime(wv["week_start"])
    full_weeks(wv, cfg).sort_values(["zone_group", "vendor_id", "week_start"]).to_csv(
        res / "flex_vendor_weekly.csv", index=False, lineterminator="\n")
    # daily records by VendorID x request_source code (D3: first Lyft date, undocumented codes)
    days = []
    for m in pd.period_range(*ch["label_months"], freq="M"):
        f = path("raw_yellow", cfg) / f"yellow_tripdata_{m}.parquet"
        days.append(duckdb.sql(f"""
            select tpep_pickup_datetime::date as day, VendorID::integer as vendor_id,
                   coalesce(request_source, 'NULL') as code, count(*) as n
            from read_parquet('{f.as_posix()}')
            where tpep_pickup_datetime >= '{m.to_timestamp()}'
              and tpep_pickup_datetime < '{(m + 1).to_timestamp()}'
            group by all""").df())
    pd.concat(days).sort_values(["day", "vendor_id", "code"]).to_csv(
        res / "request_source_daily.csv", index=False, lineterminator="\n")
    k, top = int(ch["step_window_weeks"]), int(ch["step_top_n"])
    step_list = {gname: steps(x.set_index("week_start")["flex_share"].sort_index(), k, top)
                 for gname, x in w.groupby("zone_group")}

    out = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "specification": "PLAN.md Amendment 4, D0; DECISIONS.md",
        "validation_months": ch["label_months"],
        "records": "raw yellow files, valid pickup zone, pickup inside the file's month",
        "app_definition_gate": f"request_source in {hv}",
        "code_meanings": ch["code_meanings"],
        "codes_by_vendor": codes.to_dict(orient="records"),
        "overall": overall, "by_zone_group": groups, "by_month": by_month,
        "by_vendor": by_vendor,
        "gate": {"min_rate": g["min_rate"], "min_group_share": g["min_group_share"],
                 "groups_checked": sorted(checked), "pass_by_unit": ok, "passed": passed,
                 "consequence": ("Flex Fare is the app label for 2023-01 -> 2026-05, "
                                 "request_source from 2026-06" if passed else
                                 "channel analyses restricted to 2026-06+; the earlier Flex "
                                 "series is indicative only")},
        "flex_share_steps": {"method": f"mean of the {k} weeks from t minus the {k} weeks "
                                       "before t; largest local maxima", "steps": step_list,
                             "weekly_series": "results/flex_share_weekly.csv"},
    }
    (res / "channel_label_validation.json").write_text(json.dumps(out, indent=2) + "\n")
    LOG.info("D0: P(Flex|HV) %.3f, P(HV|Flex) %.3f; gate %s (%s)", overall["p_flex_given_hv"],
             overall["p_hv_given_flex"], "PASS" if passed else "FAIL", ok)


if __name__ == "__main__":
    main()
