"""Phase 5 diagnostic (D9, added after results were seen): the main test with accident aftermath removed from the
exposure instead of dropping days.

Dropping the days after accidents (R16, diagnostic 2) removes the aftermath but is known to push estimates up when a
real effect exists (plan section 5.2). Here every day stays in; instead, events at a plant that start in the K days
after any accident at that plant (K = 30, 60 or 90) are removed from that plant's event count. Only earlier accidents
are used to clean a day's window (an event can only be removed by an accident before it), so no future information
enters. The statewide count is the primary one (not cleaned). Windows 30, 90, 180 and 365 days, gap 7, ending 2021.
A fake-date version (accidents redrawn within plant-year, 50 draws, cleaning done with the fake dates) checks that the
cleaning itself does not bias the result.
Output: data/manifests/phase5_diag_clean.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_clean.json"


def term(r):
    x = r["terms"]["x"]
    return {"rr": round(x["rr_doubling"], 3), "ci": [round(c, 3) for c in x["ci"]], "p": round(x["p"], 4),
            "n_accidents": r["n_accidents"]}


def clean_counts(cnt, acc_days, k):
    """Remove counts on days d with a < d <= a + k for an accident day a at the same plant."""
    drop = set()
    for p, days in acc_days.groupby("plant_id").day:
        for a in days.unique():
            for j in range(1, k + 1):
                drop.add((p, a + pd.Timedelta(days=j)))
    keep = [(p, d) not in drop for p, d in cnt.index]
    return cnt[keep], int(cnt[[not x for x in keep]].sum())


def main():
    plants, ev, acc, *_ = P.tables("v2")
    cnt = P.event_counts(ev)
    linked = set(plants.loc[plants.linked, "plant_id"])
    a = acc[acc.plant_id.isin(linked)]
    acc_days = pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values})
    res = {"note": __doc__.split("Output:")[0].strip(), "events_total": int(cnt.sum())}
    for k in (30, 60, 90):
        cc, removed = clean_counts(cnt, acc_days, k)
        res[f"clean_{k}"] = {"events_removed": removed}
        for w in (30, 90, 180, 365):
            r = P.h1_run(window=w, exposures={"x": cc}, statewide_counts=cnt)
            res[f"clean_{k}"][f"window_{w}"] = term(r)
            print(k, w, res[f"clean_{k}"][f"window_{w}"], flush=True)
        OUT.write_text(json.dumps(res, indent=1) + "\n")
    # fake dates: redraw each accident to a random at-risk day of its plant-year, clean with the fake dates (K = 30)
    pan = P.h1_run(keep_panel=True)["panel"]
    days_by_py = pan.groupby("plant_year").day.apply(lambda s: s.values)
    acc_py = a.assign(day=a.date.dt.normalize())
    acc_py = acc_py[acc_py.day.between(P.h1.STUDY_START, "2021-12-31")]
    acc_py["plant_year"] = acc_py.plant_id + "_" + acc_py.day.dt.year.astype(str)
    acc_py = acc_py[acc_py.plant_year.isin(days_by_py.index)]
    rng = np.random.default_rng(5)
    fake = {w: [] for w in (90, 365)}
    for i in range(50):
        fd = [days_by_py[py][rng.integers(len(days_by_py[py]))] for py in acc_py.plant_year]
        fa = acc_py.assign(date=pd.to_datetime(fd))
        fdays = pd.DataFrame({"plant_id": fa.plant_id.values, "day": fa.date.values})
        cc, _ = clean_counts(cnt, fdays, 30)
        for w in fake:
            r = P.h1_run(window=w, exposures={"x": cc}, statewide_counts=cnt, accidents=fa)
            fake[w].append(r["terms"]["x"]["rr_doubling"])
    res["fake_dates_clean_30"] = {f"window_{w}": {"draws": len(v), "median_rr": round(float(np.median(v)), 3)}
                                  for w, v in fake.items()}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(res["fake_dates_clean_30"], flush=True)


if __name__ == "__main__":
    main()
