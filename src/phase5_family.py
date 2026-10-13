"""Phase 5, part A: the H1 secondary family (plan 5.2 and D4 item 2), with Holm correction across the family.

Fifteen tests, each a two-sided p value from the plant-clustered Poisson model with plant-year and month-of-year
effects and the statewide event count (the primary model), primary window end 2021:
  O2, O3, O4 (outcomes); windows of 30, 180, 365 days; the lag profile (four bins in one model: days 8 to 91,
  92 to 183, 184 to 365, 366 to 730 before the day; each bin with its own statewide count); dose (top quarter of
  the plant's own 90-day count distribution vs the rest); pounds released (four families); recurrence; real time
  (report date); H1-M (process-control minus outside-or-planned coefficient).
The same models with the window ending 2023 are shown beside (not part of the Holm family).
Before any fit, windowed counts for 30 and 365 days are checked against a direct count on random plant-days.
Output: data/manifests/phase5_family.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_exposures as X  # noqa: E402
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_family.json"


def check_windows(cnt, raw_days):
    plants, ev, acc, acc_all, risk = P.tables("v2")
    pan = P.base_days(sorted(set(acc.plant_id.dropna()))[:60], risk, P.h1.STUDY_START, pd.Timestamp("2021-12-31"))
    rows = pan.sample(500, random_state=11).reset_index(drop=True)
    for w in (30, 365):
        got = P.windowed(cnt, rows, w, 7, w + 8)
        bad = 0
        for (p, d), g in zip(zip(rows.plant_id, rows.day), got):
            ds = raw_days.get(p, np.array([], dtype="datetime64[ns]"))
            lo, hi = np.datetime64(d - pd.Timedelta(days=w + 7)), np.datetime64(d - pd.Timedelta(days=8))
            bad += int(((ds >= lo) & (ds <= hi)).sum()) != g
        print(f"window {w}: {bad} mismatches of 500", flush=True)
        assert bad == 0


def summarize(r, term):
    t = r["terms"][term]
    return {"rr": round(t["rr_doubling"], 4), "ci": [round(t["ci"][0], 4), round(t["ci"][1], 4)], "p": t["p"],
            "beta": t["beta"], "se": t["se"], "n_accidents": r["n_accidents"], "n_plants": r["n_plants"],
            "n_days": r["n_days"], "log": r["log"]}


def main():
    plants, ev, acc, acc_all, risk = P.tables("v2")
    excl = P.exclusion("primary")
    cnt = P.event_counts(ev)
    e = ev[ev.event_type.eq("EMISSIONS EVENT") & ev.date_source.ne("none") & ~ev.incident.isin(excl) & ~ev.is_duplicate]
    raw_days = {p: g.event_datetime.dt.normalize().values for p, g in e.groupby("plant_id")}
    check_windows(cnt, raw_days)
    ee = ev[ev.event_type.eq("EMISSIONS EVENT")]
    four, voc, plog = X.pounds_by_occurrence(ee)
    lbs = P.event_counts(ev, weight=four)
    voc_s = P.event_counts(ev, weight=voc)
    rec, rlog = X.recurrence_flags(ev, excl)
    rec_s = P.event_counts(ev, weight=rec)
    grp = X.cause_groups(ev)
    by_grp = {g: P.event_counts(ev, weight=X.kept_indicator(ev, grp.values == g)) for g in ("process", "outside", "unknown")}

    def top_quarter(pan):
        q = pan.groupby("plant_id").E_x.transform(lambda v: v.quantile(0.75))
        pan["top"] = (pan.E_x > q).astype(float)
        return pan

    lag = {"l0_3": (cnt, 84, 7), "l3_6": (cnt, 92, 91), "l6_12": (cnt, 182, 183), "l12_24": (cnt, 365, 365)}
    specs = {
        "O2_fire_explosion": (dict(outcome="O2"), ["x"]),
        "O3_harm_to_people": (dict(outcome="O3"), ["x"]),
        "O4_harm_outside_fence": (dict(outcome="O4"), ["x"]),
        "window_30": (dict(window=30), ["x"]),
        "window_180": (dict(window=180), ["x"]),
        "window_365": (dict(window=365), ["x"]),
        "lag_profile": (dict(exposures=lag, statewide_each=True), list(lag)),
        "dose_top_quarter": (dict(extra_cols=top_quarter, terms=["top", "xs"]), ["top"]),
        "pounds_four_families": (dict(exposures={"lbs": lbs}, statewide_counts=cnt), ["lbs"]),
        "recurrence": (dict(exposures={"rec": rec_s}, statewide_counts=cnt), ["rec"]),
        "real_time_report_date": (dict(by="report"), ["x"]),
        "H1M_mechanism": (dict(exposures=by_grp, statewide_counts=cnt), ["process", "outside", "unknown"]),
    }
    out = {"exposure_logs": {"pounds": plog, "recurrence": rlog}, "results": {}, "end_2023": {}}
    tests = []
    for name, (kw, terms) in specs.items():
        for end, store in (("2021-12-31", out["results"]), ("2023-12-31", out["end_2023"])):
            r = P.h1_run(end=end, **kw)
            res = {t: summarize(r, t) for t in terms}
            if name == "H1M_mechanism":
                V = r["vcov"]
                d = r["terms"]["process"]["beta"] - r["terms"]["outside"]["beta"]
                sd = float(np.sqrt(V.loc["process", "process"] + V.loc["outside", "outside"]
                                   - 2 * V.loc["process", "outside"]))
                res["contrast_process_minus_outside"] = {
                    "ratio_of_rr": round(2 ** d, 4), "ci": [round(2 ** (d - 1.959964 * sd), 4),
                                                            round(2 ** (d + 1.959964 * sd), 4)],
                    "p": float(2 * norm.sf(abs(d / sd))), "beta_diff": d, "se": sd}
            if "top" in res:
                # yes/no term: its rate ratio is exp(beta), not 2^beta (found in the model review, plan D10)
                b, se = r["terms"]["top"]["beta"], r["terms"]["top"]["se"]
                res["top"]["rr_yes_vs_no"] = round(float(np.exp(b)), 4)
                res["top"]["ci_yes_vs_no"] = [round(float(np.exp(b - 1.959964 * se)), 4), round(float(np.exp(b + 1.959964 * se)), 4)]
            store[name] = res
            print(end, name, {t: (v["rr"] if "rr" in v else v["ratio_of_rr"], round(v["p"], 4)) for t, v in res.items()},
                  flush=True)
        r21 = out["results"][name]
        if name == "H1M_mechanism":
            tests.append((name + ":contrast", r21["contrast_process_minus_outside"]["p"]))
        else:
            tests += [(f"{name}:{t}" if len(terms) > 1 else name, r21[t]["p"]) for t in terms]
    # Holm across the family
    order = sorted(range(len(tests)), key=lambda i: tests[i][1])
    m = len(tests)
    adj, running = {}, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * tests[i][1]))
        adj[tests[i][0]] = running
    out["holm"] = {"family_size": m, "tests": [{"test": n, "p": p, "p_holm": adj[n], "significant": adj[n] < 0.05}
                                               for n, p in tests]}
    # VOC (total-VOC rows only), reported separately, not in the family
    r = P.h1_run(exposures={"voc": voc_s}, statewide_counts=cnt)
    out["voc_total_rows_only_separate"] = summarize(r, "voc")
    out["note_dose_scale"] = ("dose_top_quarter is a yes/no term: read rr_yes_vs_no (exp(beta)); its rr field is 2^beta "
                              "and is not the rate ratio (D10 addendum).")
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps(out["holm"], indent=1))


if __name__ == "__main__":
    main()
