"""Phase 5 diagnostic (D9, after the independent model review): the main test with the accident's own reports
removed from the exposure.

An accident is itself reported to TCEQ (on the accident day, events run about 20 times the plant's usual rate). Those
reports enter the look-back windows of the comparison days that follow, which pulls the estimate below 1. Here, at
each plant, events starting on an accident day or the K days after it (K = 0, 2, 7) are removed from the event count;
every day stays in. Only earlier accidents remove events from a day's window, so no future information is used. The
statewide count is the primary one. Windows 30, 90, 180, 365 days, gap 7, ending 2021, plus O4 and the lag profile
for K = 2. Calibration: the same removal around fake accident dates (each accident redrawn to a random at-risk day of
its plant-year; 60 draws; K = 2; windows 90 and 365) shows how much the removal itself moves the estimate.
(An earlier version, src/phase5_diag_clean.py, removed days 1 to K but kept the accident day; its estimates rose
steadily with K, the sign of a removal bias, and it was stopped and superseded by this one.)
Output: data/manifests/phase5_diag_own_reports.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_own_reports.json"


def term(r, t="x"):
    x = r["terms"][t]
    return {"rr": round(x["rr_doubling"], 3), "ci": [round(c, 3) for c in x["ci"]], "p": round(x["p"], 4),
            "n_accidents": r["n_accidents"]}


def remove_after(cnt, acc_days, k):
    """Remove counts on plant-days a .. a + k for every accident day a at the plant."""
    drop = {(p, a + pd.Timedelta(days=j)) for p, a in set(zip(acc_days.plant_id, acc_days.day)) for j in range(k + 1)}
    keep = np.array([(p, d) not in drop for p, d in cnt.index])
    return cnt[keep], int(cnt[~keep].sum())


def main():
    plants, ev, acc, *_ = P.tables("v2")
    cnt = P.event_counts(ev)
    linked = set(plants.loc[plants.linked, "plant_id"])
    a = acc[acc.plant_id.isin(linked)]
    acc_days = pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values})
    res = {"note": __doc__.split("Output:")[0].strip(), "events_total": int(cnt.sum())}
    for k in (0, 2, 7):
        cc, removed = remove_after(cnt, acc_days, k)
        res[f"remove_0_to_{k}"] = {"events_removed": removed}
        for w in (30, 90, 180, 365):
            r = P.h1_run(window=w, exposures={"x": cc}, statewide_counts=cnt)
            res[f"remove_0_to_{k}"][f"window_{w}"] = term(r)
            print(k, w, res[f"remove_0_to_{k}"][f"window_{w}"], flush=True)
        OUT.write_text(json.dumps(res, indent=1) + "\n")
    cc2, _ = remove_after(cnt, acc_days, 2)
    r = P.h1_run(outcome="O4", exposures={"x": cc2}, statewide_counts=cnt)
    res["remove_0_to_2"]["O4_window_90"] = term(r)
    lag = {f"l{i}": (cc2, w, g) for i, (w, g) in enumerate([(84, 7), (92, 91), (182, 183), (365, 365)])}
    r = P.h1_run(exposures=lag, statewide_each=True)
    res["remove_0_to_2"]["lag_profile"] = {"bins_days_before": ["8-91", "92-183", "184-365", "366-730"]} | {
        t: term(r, t) for t in lag}
    print("O4 and lags", res["remove_0_to_2"]["O4_window_90"], res["remove_0_to_2"]["lag_profile"], flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    # calibration on fake dates
    pan = P.h1_run(keep_panel=True)["panel"]
    days_by_py = pan.groupby("plant_year").day.apply(lambda s: s.values)
    ap = a.assign(day=a.date.dt.normalize())
    ap = ap[ap.day.between(P.h1.STUDY_START, "2021-12-31")]
    ap = ap.assign(plant_year=ap.plant_id + "_" + ap.day.dt.year.astype(str))
    ap = ap[ap.plant_year.isin(days_by_py.index)]
    rng = np.random.default_rng(17)
    fake = {90: [], 365: []}
    for i in range(60):
        fd = pd.to_datetime([days_by_py[py][rng.integers(len(days_by_py[py]))] for py in ap.plant_year])
        fa = ap.assign(date=fd)
        cc, _ = remove_after(cnt, pd.DataFrame({"plant_id": fa.plant_id.values, "day": fd}), 2)
        for w in fake:
            fake[w].append(P.h1_run(window=w, exposures={"x": cc}, statewide_counts=cnt, accidents=fa)["terms"]["x"]["rr_doubling"])
        if (i + 1) % 10 == 0:
            res["fake_dates_remove_0_to_2"] = {f"window_{w}": {"draws": len(v), "median_rr": round(float(np.median(v)), 3),
                                                              "p5_p95": [round(float(np.percentile(v, q)), 3) for q in (5, 95)]}
                                               for w, v in fake.items()}
            OUT.write_text(json.dumps(res, indent=1) + "\n")
            print(i + 1, res["fake_dates_remove_0_to_2"], flush=True)


if __name__ == "__main__":
    main()
