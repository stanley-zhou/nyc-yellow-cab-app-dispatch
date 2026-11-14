"""Amendment 6 (Checkpoint 7 review): descriptive numbers the report and README quote.

Every number here is read or derived from existing files under results/ (daily weather from
results/weather_daily.csv, written by scripts/06c_weather_daily.py in `make shock`); the
repository counts read DECISIONS.md, reviews/ and the pytest collection. Nothing is
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
    wx = pd.read_csv(path("results", cfg) / "weather_daily.csv")   # scripts/06c_weather_daily.py
    wx = wx[(wx["day"] >= lo) & (wx["day"] <= hi)].copy()
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


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def checks(cfg: dict) -> dict:
    """The causal designs and their pass/fail checks (B2; review round 1, fix 1).

    `preregistered`: True = expected direction and gate fixed before the run (PLAN and its
    amendments, written before the design was estimated); False = added after seeing an earlier
    result (labelled alternatives). `passed`: the gate's outcome (pre-trend tests at
    `presentation.gate_alpha`, or the design's own gate as named in `gate`)."""
    alpha = float(cfg["presentation"]["gate_alpha"])
    pl, sp, so = _json("placebo.json"), _json("speed_did.json"), _json("speed_did_outer.json")
    ch, fh, ly = _json("did_by_channel.json"), _json("fhv_did.json"), _json("lyft_entry.json")
    st, sc, inc = _json("app_share_policy_step.json"), _json("synth_control.json"), \
        _json("incrementality_dml.json")
    ds = _json("did_static.json")["estimates"]
    lead = {a: inc["areas"][a]["first_difference_lead_placebo"]["lead"]["pvalue"]
            for a in ("cbd", "manhattan_non_cbd", "other")}
    rows = []

    def add(question, design, pre, estimate, gate, passed, values, f, note=""):
        rows.append({"question": question, "design": design, "preregistered": pre,
                     "estimate": estimate, "gate": gate, "passed": passed,
                     "gate_values": values, "file": f"results/{f}", "note": note})

    def pretrend(question, design, pre, estimate, p, f, note=""):
        add(question, design, pre, estimate, f"pre-trend test p >= {alpha:g}", p >= alpha,
            {"p_value": p}, f, note)

    q = "Congestion pricing and yellow demand"
    pretrend(q, "DiD, equal zone weights", True,
             _pct(ds["main"]["terms"]["treated_post"]["pct"]),
             _p(pl["pretrend_tests"]["event_study_month"]["pretrend"]), "placebo.json")
    pretrend(q, "DiD, zones weighted by volume", False,
             _pct(ds["pre_volume_weighted_not_preregistered"]["terms"]["treated_post"]["pct"]),
             _p(pl["pretrend_tests"]["event_study_month_pre_volume_weighted_not_preregistered"]
                ["pretrend"]), "placebo.json",
             "added after the equal-weight result (PLAN Amendment 3, C2)")
    it = sc["in_time_placebo"]
    add(q, "Synthetic control", True,
        f"{_pct(sc['post_gap_mean_pct'])} (rank {sc['in_space_placebos']['cbd_rank']} of "
        f"{sc['in_space_placebos']['n'] + 1} units)",
        "fake-date (2024) mean gap within the CBD's pre-period fit (RMSPE)",
        bool(sc["pre_fit"]["gate_in_time_mean_gap_within_cbd_pre_rmspe"]),
        {"fake_date_mean_gap_log": it["post_gap_mean_log"], "cbd_pre_rmspe": sc["pre_rmspe"],
         "p_value": None}, "synth_control.json")
    q = "Congestion pricing and trip speed"
    pretrend(q, "DiD against Manhattan outside the CBD", True,
             _pct(sp["outcomes"]["log_mean_speed_mph"]["main"]["terms"]["treated_post"]["pct"]),
             _p(sp["outcomes"]["log_mean_speed_mph"]["event_study_month"]["pretrend"]),
             "speed_did.json")
    pretrend(q, "DiD against Brooklyn and Queens", True,
             _pct(so["outcomes"]["log_mean_speed_mph"]["main"]["terms"]["treated_post"]["pct"]),
             _p(so["outcomes"]["log_mean_speed_mph"]["event_study_month"]["pretrend"]),
             "speed_did_outer.json")
    pretrend("Congestion pricing and Uber + Lyft demand", "DiD", True, "not estimated",
             _p(fh["series"]["fhv_all"]["pre_volume_weighted"]["pretrend"]), "fhv_did.json")
    q = "Congestion pricing by channel"
    for c, name in (("street", "DiD, street hails"), ("app", "DiD, app trips")):
        pretrend(q, name, True, _pct(ch["channels"][c]["estimate"]["terms"]["treated_post"]
                                     ["pct"]), _p(ch["channels"][c]["pretrend"]),
                 "did_by_channel.json")
    bt = st["yellow"]["d0_step_by_trip_type"]["by_type"]
    touch = [bt[k]["step_pp"] for k in ("within", "into", "out_of")]
    add("Did the fee move trips into apps?", "App-share step by trip type", True,
        f"{min(touch):+.1f} to {max(touch):+.1f} points (touching the CBD) vs "
        f"{bt['neither']['step_pp']:+.1f} (touching neither end)",
        "pre-specified comparison of the step across trip types (no parallel-trend "
        "assumption)", True, {"p_value": None}, "app_share_policy_step.json",
        "answered: the step is as large for trips that never touch the zone")
    pretrend("Did the fee move trips into apps?", "DiD, app share (secondary)", False,
             f"{st['yellow']['pooled']['app_share']['coef'] * 100:+.1f} points",
             _p(st["yellow"]["pretrend"]["app_share"]), "app_share_policy_step.json",
             "secondary reading, not the pre-specified one")
    pr, lg = ly["primary_clean_windows"], ly["log_specification"]["clean_windows"]
    ptr = {k: _p(v) for k, v in pr["pretrend"].items()}
    add("Lyft's entry on Curb cabs (preliminary)", "DiD by vendor, levels", True,
        f"{pr['incrementality']:.2f} [{pr['incrementality_ci'][0]:.2f}, "
        f"{pr['incrementality_ci'][1]:.2f}]",
        f"pre-trend tests p >= {alpha:g} on total, app and street pickups",
        all(ptr[k] >= alpha for k in ("total", "app", "street")),
        {"p_value_by_outcome": ptr}, "lyft_entry.json",
        "passes, but not credible: levels are misspecified in scale (Curb cabs carry 4.3 "
        "times CMT's volume); the Uber outcome fails its pre-trend test")
    pretrend("Lyft's entry on Curb cabs (preliminary)", "DiD by vendor, logs (alternative)",
             False, f"{lg['incrementality']:.2f} [{lg['incrementality_ci'][0]:.2f}, "
             f"{lg['incrementality_ci'][1]:.2f}]", _p(lg["pretrend"]["total"]),
             "lyft_entry.json", "labelled alternative added after the levels result")
    d = inc["areas"]["cbd"]["dml_plr"]
    add("Are app trips additional?", "Double machine learning (DML)", True,
        f"{d['theta']:.2f} [{d['theta_ci'][0]:.2f}, {d['theta_ci'][1]:.2f}] (CBD)",
        f"lead placebo p >= {alpha:g} in every area", min(lead.values()) >= alpha,
        {"lead_placebo_p": lead}, "incrementality_dml.json",
        "the lead placebo fails in Manhattan outside the CBD")
    pre = [r for r in rows if r["preregistered"]]
    return {"rows": rows, "gate_alpha": alpha,
            "n_preregistered": len(pre),
            "n_preregistered_stopped": sum(not r["passed"] for r in pre),
            "n_preregistered_passed": sum(r["passed"] for r in pre),
            "n_not_preregistered": len(rows) - len(pre),
            "n_not_preregistered_stopped": sum(not r["passed"] for r in rows
                                               if not r["preregistered"]),
            "incrementality_lead_placebo_p": lead}


def repo_counts() -> dict:
    root = repo_root()
    decisions = sum(1 for line in (root / "DECISIONS.md").read_text().splitlines()
                    if re.match(r"^- \[\d{4}-\d{2}-\d{2}[\] ]", line))
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
        "preregistered_checks": checks(cfg),
        "repository": repo_counts(),
        "external_app_share_2024": external_app_share(cfg),
    }
    (res / "presentation_numbers.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("scale", "repository")}, indent=1))


if __name__ == "__main__":
    main()
