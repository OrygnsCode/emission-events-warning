"""Calibration of the own-report removal for K = 0 and K = 7 (plan D16 item 3; K = 2 is in
phase5_diag_own_reports.json): each accident is redrawn to a random at-risk day of its plant-year (60 draws), the
plant's reports on the fake accident day and the K days after are removed, and the 90-day H1 model is refitted.
With no real accidents on those days, the median shows how far the removal itself moves the estimate.
Output: data/manifests/phase5_removal_calibration.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_own_reports as OR  # noqa: E402
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_removal_calibration.json"


def main():
    plants, ev, acc, *_ = P.tables("v2")
    cnt = P.event_counts(ev)
    linked = set(plants.loc[plants.linked, "plant_id"])
    a = acc[acc.plant_id.isin(linked)]
    pan = P.h1_run(keep_panel=True)["panel"]
    days_by_py = pan.groupby("plant_year").day.apply(lambda s: s.values)
    ap = a.assign(day=a.date.dt.normalize())
    ap = ap[ap.day.between(P.h1.STUDY_START, "2021-12-31")]
    ap = ap.assign(plant_year=ap.plant_id + "_" + ap.day.dt.year.astype(str))
    ap = ap[ap.plant_year.isin(days_by_py.index)]
    rng = np.random.default_rng(17)
    res = {"note": __doc__.split("Output:")[0].strip()}
    vals = {0: [], 7: []}
    for i in range(60):
        fd = pd.to_datetime([days_by_py[py][rng.integers(len(days_by_py[py]))] for py in ap.plant_year])
        fa = ap.assign(date=fd)
        for k in vals:
            cc, _ = OR.remove_after(cnt, pd.DataFrame({"plant_id": fa.plant_id.values, "day": fd}), k)
            vals[k].append(P.h1_run(exposures={"x": cc}, statewide_counts=cnt, accidents=fa)["terms"]["x"]["rr_doubling"])
        if (i + 1) % 10 == 0:
            res["window_90"] = {f"K_{k}": {"draws": len(v), "median_rr": round(float(np.median(v)), 3),
                                           "p5_p95": [round(float(np.percentile(v, q)), 3) for q in (5, 95)]}
                                for k, v in vals.items()}
            OUT.write_text(json.dumps(res, indent=1) + "\n")
            print(i + 1, res["window_90"], flush=True)


if __name__ == "__main__":
    main()
