"""Amendment 6 (Checkpoint 7 review): descriptive numbers the report and README quote.

Every number here is read or derived from an existing results file or the warehouse; nothing is
re-estimated. Writes
  results/presentation_numbers.json   citywide growth accounting (A1), the January-2025 app step
                                      by area (A2), the 2026 alarm / weather check (A3), supply
                                      (A11), outer-borough levels (A12), scale (B3b), forecast skill
                                      vs the seasonal naive (B3c), bias by area (B3e), the CBD ride
                                      market (B3g), the pre-registered checks (B2), repository
                                      counts (B5), the external 2024 app-share check (C)
  results/alarm_weather_check.csv     daily weather and actual vs frozen forecast, 2026-Q1
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime

import pandas as pd

from taxi_shock.config import load_config, path, repo_root
from taxi_shock.io import connect

AREAS = {"cbd": "congestion zone (CBD)", "manhattan_non_cbd": "Manhattan outside the CBD",
         "other": "outer boroughs", "airports": "airports", "all": "all zones"}


def _json(name: str) -> dict:
    return json.loads((path("results") / name).read_text())


def accounting(cfg: dict) -> dict:
    d = pd.read_csv(path("results", cfg) / "channel_decomposition.csv")
    d = d[(d["comparison"] == cfg["presentation"]["accounting_comparison"]) & ~d["with_cmt_block"]]
    out = {}
    for g in ("all", "cbd", "manhattan_non_cbd", "other"):
        r = d[d["zone_group"] == g].iloc[0]
        out[g] = {"base_mean_weekly": float(r["base_mean_weekly"]),
                  "end_mean_weekly": float(r["end_mean_weekly"]),
                  "change": float(r["change"]), "change_pct": float(r["change_pct"]),
                  "ratio_end_to_base": float(r["end_mean_weekly"] / r["base_mean_weekly"]),
                  "app_change": float(r["app_change"]),
                  "app_contribution": float(r["app_contribution"]),
                  "street_base": float(r["street_base"]),
                  "street_change": float(r["street_change"]),
                  "street_change_pct": float(r["street_change"] / r["street_base"])}
    return {"source": "results/channel_decomposition.csv (with_cmt_block = False)",
            "comparison": cfg["presentation"]["accounting_comparison"], "by_area": out}


def january_step(cfg: dict) -> dict:
    pc = cfg["presentation"]
    w = pd.read_csv(path("results", cfg) / "channel_weekly.csv")
    b, a = pc["step_weeks"]
    rows = {}
    for g in pc["step_areas"]:
        x = w[w["zone_group"] == g].set_index("week_start")
        rows[g] = {"app_before": int(x.loc[b, "app"]), "app_after": int(x.loc[a, "app"]),
                   "app_ratio": float(x.loc[a, "app"] / x.loc[b, "app"]),
                   "street_before": int(x.loc[b, "street"]),
                   "street_after": int(x.loc[a, "street"]),
                   "street_change_pct": float(x.loc[a, "street"] / x.loc[b, "street"] - 1)}
    steps = _json("channel_label_validation.json")["flex_share_steps"]
    return {"source": "results/channel_weekly.csv (street excludes the contracted programme); "
                      "results/channel_label_validation.json -> flex_share_steps",
            "weeks": [b, a], "by_area": rows,
            "steps_all_zones": steps["steps"]["all"], "steps_cbd": steps["steps"]["cbd"],
            "step_method": steps["method"],
            "same_step_for_trips_not_touching_the_zone":
                "results/app_share_policy_step.json (D5b)"}


def alarm_check(cfg: dict) -> tuple[dict, pd.DataFrame]:
    ac = cfg["presentation"]["alarm_check"]
    lo, hi = ac["first_day"], ac["last_day"]
    with connect(path("warehouse", cfg), cfg=cfg) as con:
        wx = con.execute(
            "select cast(timezone(?, to_timestamp(unix_time)) as date) as day, "
            # rounded: DuckDB's parallel float sums differ in the last bits between runs
            "round(sum(snowfall), 3) as snowfall_in, round(sum(precipitation), 3) as precip_in, "
            "min(temperature_2m) as temp_min_f, max(temperature_2m) as temp_max_f, "
            "count(*) as n_hours from int_weather_selected group by 1 "
            "having day between ? and ? order by 1", [cfg["timezone"], lo, hi]).df()
    wx["day"] = pd.to_datetime(wx["day"])
    daily = pd.read_csv(path("results", cfg) / "adaptation_daily.csv", parse_dates=["day"])
    daily = daily[(daily["day"] >= lo) & (daily["day"] <= hi)]
    s0 = daily[daily["strategy"] == "s0"].pivot_table(index="day", columns="zone_group",
                                                       values=["y", "err"], aggfunc="sum")
    # monitor groups: cbd and non_cbd (= every modeled zone outside the CBD = all - cbd);
    # err = forecast - actual
    tab = wx.set_index("day")
    for g, y, e in (("cbd", s0[("y", "cbd")], s0[("err", "cbd")]),
                    ("non_cbd", s0[("y", "all")] - s0[("y", "cbd")],
                     s0[("err", "all")] - s0[("err", "cbd")])):
        tab[f"{g}_actual"] = y
        tab[f"{g}_frozen_forecast"] = y + e
        tab[f"{g}_actual_vs_forecast_pct"] = 100 * (y / (y + e) - 1)
    tab["storm_day"] = tab["snowfall_in"] >= ac["storm_snowfall_in"]
    tab = tab.reset_index()

    drift = _json("drift_detection.json")["primary"]["groups"]
    alarms = []
    for g in ("cbd", "non_cbd"):
        for al in drift[g]["cusum"]["alarms"]:
            d = pd.Timestamp(al["date"])
            if not (pd.Timestamp(lo) <= d <= pd.Timestamp(hi)):
                continue
            win = tab[(tab["day"] >= d - pd.Timedelta(days=ac["days_before_alarm"]))
                      & (tab["day"] <= d)]
            alarms.append({
                "group": g, "date": al["date"], "side": al["side"],
                "max_snowfall_in_window": float(win["snowfall_in"].max()),
                "snowiest_day": str(win.loc[win["snowfall_in"].idxmax(), "day"].date()),
                "storm_days_in_window": [str(x.date()) for x in win.loc[win["storm_day"], "day"]],
                "min_actual_vs_forecast_pct": float(win[f"{g}_actual_vs_forecast_pct"].min()),
                "day_of_min": str(win.loc[win[f"{g}_actual_vs_forecast_pct"].idxmin(),
                                          "day"].date())})
    storm = set(tab.loc[tab["storm_day"], "day"])
    wape = {}
    for s, x in daily[daily["zone_group"] == "all"].groupby("strategy"):
        keep = ~x["day"].isin(storm)
        wape[s] = {"wape_quarter": float(x["abs_err"].sum() / x["y"].sum()),
                   "wape_excluding_storm_days": float(x.loc[keep, "abs_err"].sum()
                                                      / x.loc[keep, "y"].sum()),
                   "share_of_abs_error_on_storm_days": float(x.loc[~keep, "abs_err"].sum()
                                                             / x["abs_err"].sum())}
    adapt = pd.read_csv(path("results", cfg) / "adaptation.csv")
    q = adapt[(adapt["metric"] == "wape") & (adapt["zone_group"] == "all")
              & (adapt["calibration"] == "raw") & (adapt["horizon_bucket"] == "all")
              & (adapt["subset"] == "all")]
    for s in wape:
        r = q[q["strategy"] == s].set_index("period")["value"]
        wape[s]["wape_2025q1"] = float(r["2025Q1"])
        wape[s]["wape_2026q1_adaptation_csv"] = float(r["2026Q1"])
    return ({"window": [lo, hi], "storm_rule": f"daily snowfall >= {ac['storm_snowfall_in']} in "
             "(Open-Meteo, one city-wide point, local days)",
             "storm_days": sorted(str(d.date()) for d in storm),
             "alarms_2026": alarms, "wape_by_strategy_all_zones": wape,
             "daily_file": "results/alarm_weather_check.csv"}, tab)


def supply(cfg: dict) -> dict:
    y = _json("incrementality_dml.json")["supply"]["yearly_means_of_monthly_values"]
    a, b = cfg["presentation"]["supply_years"]
    tpv = {k: v["trips_per_vehicle_day"] for k, v in y.items()}
    return {"source": "results/incrementality_dml.json -> supply (TLC monthly reports)",
            "vehicles_per_day_rounded_10": {k: int(round(v["vehicles_per_day"], -1))
                                            for k, v in y.items()},
            "trips_per_vehicle_day": tpv,
            "trips_per_vehicle_day_range_2023_on": [min(v for k, v in tpv.items() if k >= a),
                                                    max(v for k, v in tpv.items() if k >= a)],
            "trips_per_day_change_pct": 100 * (y[b]["trips_per_day"] / y[a]["trips_per_day"] - 1),
            "vehicles_per_day_change_pct": 100 * (y[b]["vehicles_per_day"]
                                                  / y[a]["vehicles_per_day"] - 1),
            "years": [a, b], "last_month": _json("incrementality_dml.json")["supply"]["last_month"]}


def ride_market(cfg: dict) -> dict:
    pc = cfg["presentation"]
    cp = pd.read_csv(path("results", cfg) / "cross_platform_monthly.csv")
    cb = cp[cp["zone_group"] == "cbd"].assign(year=lambda d: d["month"].str[:4])
    g = cb.groupby("year")[["app", "street", "fhv_uber", "fhv_lyft", "n_weeks"]].sum()
    out = {}
    for yr in pc["ride_market_years"]:
        r = g.loc[yr]
        yellow = (r["app"] + r["street"]) / r["n_weeks"]
        fhv = (r["fhv_uber"] + r["fhv_lyft"]) / r["n_weeks"]
        out[yr] = {"yellow_weekly": float(yellow), "uber_lyft_fhv_weekly": float(fhv),
                   "total_weekly": float(yellow + fhv),
                   "yellow_share": float(yellow / (yellow + fhv)),
                   "n_weeks": int(r["n_weeks"])}
    a, b = pc["ride_market_years"]
    plat = cb[cb["month"].isin(pc["ride_market_platform_months"])].set_index("month")
    return {"source": "results/cross_platform_monthly.csv (zone_group cbd; yearly means of weekly "
                      "pickups = yearly sums / panel weeks)",
            "by_year": out,
            "total_change_pct": 100 * (out[b]["total_weekly"] / out[a]["total_weekly"] - 1),
            "uber_share_served_by_yellow": {m: float(v) for m, v in
                                            plat["uber_yellow_share_of_uber"].dropna().items()},
            "lyft_share_served_by_yellow": {m: float(v) for m, v in
                                            plat["lyft_yellow_share_of_lyft"].dropna().items()}}


def _p(x: dict) -> float:
    return float(x["p_F_hotelling"])


def checks() -> dict:
    """The pre-registered designs with an expected direction and a pass/fail check (B2)."""
    pl, sp, so = _json("placebo.json"), _json("speed_did.json"), _json("speed_did_outer.json")
    ch, fh, ly = _json("did_by_channel.json"), _json("fhv_did.json"), _json("lyft_entry.json")
    st, sc, inc = _json("app_share_policy_step.json"), _json("synth_control.json"), \
        _json("incrementality_dml.json")
    lead = {a: inc["areas"][a]["first_difference_lead_placebo"]["lead"]["pvalue"]
            for a in ("cbd", "manhattan_non_cbd", "other")}
    rows = [
        ("Yellow demand, DiD, equal zone weights", "pre-trend test",
         _p(pl["pretrend_tests"]["event_study_month"]["pretrend"]), "placebo.json"),
        ("Yellow demand, DiD, zones weighted by volume", "pre-trend test",
         _p(pl["pretrend_tests"]["event_study_month_pre_volume_weighted_not_preregistered"]
            ["pretrend"]), "placebo.json"),
        ("Yellow demand, synthetic control", "fake-date gap within pre-period fit",
         None if sc["pre_fit"]["gate_in_time_mean_gap_within_cbd_pre_rmspe"] else 0.0,
         "synth_control.json"),
        ("Trip speed, DiD against Manhattan outside the CBD", "pre-trend test",
         _p(sp["outcomes"]["log_mean_speed_mph"]["event_study_month"]["pretrend"]),
         "speed_did.json"),
        ("Trip speed, DiD against Brooklyn and Queens", "pre-trend test",
         _p(so["outcomes"]["log_mean_speed_mph"]["event_study_month"]["pretrend"]),
         "speed_did_outer.json"),
        ("Uber + Lyft demand, DiD", "pre-trend test",
         _p(fh["series"]["fhv_all"]["pre_volume_weighted"]["pretrend"]), "fhv_did.json"),
        ("Street hails, DiD", "pre-trend test", _p(ch["channels"]["street"]["pretrend"]),
         "did_by_channel.json"),
        ("App trips, DiD", "pre-trend test", _p(ch["channels"]["app"]["pretrend"]),
         "did_by_channel.json"),
        ("App share, DiD at the policy date", "pre-trend test",
         _p(st["yellow"]["pretrend"]["app_share"]), "app_share_policy_step.json"),
        ("Lyft entry on Curb cabs, DiD (log)", "pre-trend test",
         _p(ly["log_specification"]["clean_windows"]["pretrend"]["total"]), "lyft_entry.json"),
        ("Incrementality of app trips (DML)", "lead placebo in every area",
         min(lead.values()), "incrementality_dml.json"),
    ]
    out = [{"design": d, "check": c, "p_value": p, "passed": (p is None or p >= 0.05),
            "file": f"results/{f}"} for d, c, p, f in rows]
    return {"rows": out, "n_designs": len(out), "n_passed": sum(r["passed"] for r in out),
            "n_stopped": sum(not r["passed"] for r in out),
            "incrementality_lead_placebo_p": lead,
            "note": "synthetic control: p_value 0.0 stands for the failed boolean gate "
                    "gate_in_time_mean_gap_within_cbd_pre_rmspe; check = p >= 0.05"}


def repo_counts() -> dict:
    root = repo_root()
    decisions = sum(1 for line in (root / "DECISIONS.md").read_text().splitlines()
                    if re.match(r"^- \[\d{4}-\d{2}-\d{2}\]", line))
    reviews = sorted(p.name for p in (root / "reviews").glob("*.md"))
    phases = sorted({m.group(1) for n in reviews if (m := re.match(r"phase_(\d+)", n))})
    col = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=root,
                         capture_output=True, text=True).stdout
    # the project's pytest options already pass -q, so the listing is "file: n" per test file
    n_tests = sum(int(n) for n in re.findall(r"^tests/\S+: (\d+)$", col, flags=re.M))
    if not n_tests:
        raise SystemExit("pytest collection listed no tests")
    return {"decisions_entries": decisions, "review_files": len(reviews),
            "phases_reviewed": phases, "tests_collected": n_tests}


def external_app_share(cfg: dict) -> dict:
    ex = cfg["presentation"]["external_app_share"]
    cm = pd.read_csv(path("results", cfg) / "channel_monthly.csv")
    m = cm[cm["month"].str.startswith(ex["year"])].groupby("month")[["app", "total"]].sum()
    share = (m["app"] / m["total"]).round(4)
    lo, hi = ex["range"]
    inside = share[(share >= lo) & (share <= hi)]
    return {"source": ex["source"], "external_range": ex["range"],
            "monthly_app_share_all_yellow": share.to_dict(),
            "min": float(share.min()), "max": float(share.max()),
            "months_inside_range": len(inside), "months": len(share),
            "months_above_range": int((share > hi).sum()),
            "months_below_range": int((share < lo).sum()),
            "agree": bool(len(inside) == len(share))}


def main() -> None:
    cfg = load_config()
    res = path("results", cfg)
    fs = _json("forecast_summary.json")["wape_relative_to_seasonal_naive_expanding"]
    alarm, tab = alarm_check(cfg)
    tab.to_csv(res / "alarm_weather_check.csv", index=False, lineterminator="\n",
               float_format="%.4f")
    dq = pd.read_csv(res / "data_quality_monthly.csv")
    yellow, hv = int(dq["raw_rows"].sum()), int(_json("hvfhv_summary.json")["trips_total"])
    out = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "citywide_accounting": accounting(cfg),
        "january_2025_step": january_step(cfg),
        "alarm_weather_check": alarm,
        "supply": supply(cfg),
        "scale": {"yellow_raw_records": yellow, "hvfhv_trips": hv, "total": yellow + hv,
                  "source": "results/data_quality_monthly.csv, results/hvfhv_summary.json"},
        "forecast_vs_seasonal_naive_2024": {
            k: {"wape_ratio": fs[k]["all"], "error_reduction_pct": 100 * (1 - fs[k]["all"])}
            for k in ("chronos2_weather_past|zero_shot", "lgbm_quantile|expanding")},
        "bias_pct_by_area": {k: v for k, v in
                             _json("adaptation_summary.json")["bias_pct_of_pickups"].items()},
        "cbd_ride_market": ride_market(cfg),
        "preregistered_checks": checks(),
        "repository": repo_counts(),
        "external_app_share_2024": external_app_share(cfg),
    }
    (res / "presentation_numbers.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("scale", "repository")}, indent=1))


if __name__ == "__main__":
    main()
