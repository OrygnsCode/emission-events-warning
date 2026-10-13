"""Phase 5 diagnostic (D9/D10, exploratory): permutation check of the planned-work finding. Accidents stay fixed;
within each plant-year of the primary panel, the daily series of planned-work report starts is shifted by a random
circular offset (keeps how planned work bunches together, breaks its timing relative to accidents). The 7-day sum
(days -7 to -1) is computed inside the plant-year for both the real and the shifted series, so both are built the
same way. Statistic: the planned-work coefficient in the same model as phase5_diag_planned.py (unplanned and
statewide terms kept real). 500 draws. Output: data/manifests/phase5_diag_planned_perm.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_planned as D  # noqa: E402
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_planned_perm.json"
TERMS = ["planned", "unplanned", "xs_planned", "xs_unplanned"]


def lastweek(daily):
    c = np.concatenate([[0], np.cumsum(daily)])
    i = np.arange(len(daily))
    return c[i] - c[np.maximum(i - 7, 0)]


def main():
    plants, ev, *_ = P.tables("v2")
    e = D.planned_reports(ev)
    cp = D.counts(e)
    cu = P.event_counts(ev, D.UNPLANNED)
    pan = P.h1_run(exposures={"planned": (cp, 7, 0), "unplanned": (cu, 7, 0)}, statewide_each=True,
                   keep_panel=True)["panel"].sort_values(["plant_year", "day"]).reset_index(drop=True)
    daily = cp.reindex(list(zip(pan.plant_id, pan.day)), fill_value=0).values.astype(float)
    groups = list(pan.groupby("plant_year", sort=False).indices.values())
    # the days of a plant-year must be consecutive for the circular shift; check and record
    gaps = sum(int((np.diff(pan.day.values[g]).astype("timedelta64[D]").astype(int) != 1).any()) for g in groups)

    def stat(series):
        x = np.empty(len(series))
        for g in groups:
            x[g] = lastweek(series[g])
        r = P.fit(pan.assign(planned=np.log1p(x)), TERMS, "plant_year + moy", "poisson")
        return r["terms"]["planned"]["beta"]

    real = stat(daily)
    rng = np.random.default_rng(23)
    null = []
    for i in range(500):
        sh = daily.copy()
        for g in groups:
            sh[g] = np.roll(daily[g], rng.integers(len(g)))
        null.append(stat(sh))
        if (i + 1) % 100 == 0:
            print(i + 1, flush=True)
    null = np.array(null)
    res = {"note": __doc__.split("Output:")[0].strip(), "plant_years_with_day_gaps": gaps,
           "real_rr_within_year_build": round(2 ** real, 3), "draws": len(null),
           "null_median_rr": round(float(2 ** np.median(null)), 3),
           "null_p5_p95_rr": [round(float(2 ** np.percentile(null, q)), 3) for q in (5, 95)],
           "p_one_sided": round(float((1 + (null >= real).sum()) / (1 + len(null))), 4),
           "p_two_sided": round(float((1 + (np.abs(null - np.median(null)) >= abs(real - np.median(null))).sum()) / (1 + len(null))), 4)}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(res)


if __name__ == "__main__":
    main()
