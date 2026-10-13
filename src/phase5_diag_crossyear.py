"""STOPPED 2026-10-05 before writing output: its fake-data check placed fake accidents in the real accident years, so it could not
separate design bias from the real year-level pattern (D9). Kept for the record; superseded by phase5_diag_era.py.

Diagnostic added after the Phase 5 family results were seen (D9): the post-accident check for long windows.
Within one plant-year, dropping every day after an accident leaves the accident as the last day of every stratum,
so long windows cannot be checked that way. Here strata are by plant with year and month-of-year effects (the R12
design), with and without dropping (window + gap) days after each accident. The same design is first run on fake
accident dates (same count per plant-year, uniform days, no effect) to show it is not biased itself.
Output: data/manifests/phase5_diag_crossyear.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_crossyear.json"
FE = "plant_id + year + moy"


def fake_acc(acc, linked, end, risk, seed):
    a = acc[acc.plant_id.isin(linked) & acc.date.between(P.h1.STUDY_START, pd.Timestamp(end))]
    k = a.assign(year=a.date.dt.year).groupby(["plant_id", "year"]).size()
    days = P.base_days(sorted(k.index.get_level_values(0).unique()), risk, P.h1.STUDY_START, pd.Timestamp(end))
    rng = np.random.default_rng(seed)
    rows = []
    for (p, y), g in days.groupby(["plant_id", "year"]):
        n = int(k.get((p, y), 0))
        if n:
            rows += [(p, d) for d in g.day.values[rng.choice(len(g), size=min(n, len(g)), replace=False)]]
    f = pd.DataFrame(rows, columns=["plant_id", "date"])
    f["O1"] = True
    return f


def main():
    plants, ev, acc, acc_all, risk = P.tables("v2")
    linked = set(plants.loc[plants.linked, "plant_id"])
    cnt = P.event_counts(ev)
    lag = {"l0_3": (cnt, 84, 7), "l3_6": (cnt, 92, 91), "l6_12": (cnt, 182, 183), "l12_24": (cnt, 365, 365)}
    items = {"window_90": (dict(), ["x"], 97), "window_180": (dict(window=180), ["x"], 187),
             "window_365": (dict(window=365), ["x"], 372),
             "lag_profile": (dict(exposures=lag, statewide_each=True), list(lag), 730),
             "O4_harm_outside_fence": (dict(outcome="O4"), ["x"], 97)}
    out = {"fake_no_effect": {}, "real": {}}
    for name in ("window_365", "lag_profile"):
        kw, terms, days = items[name]
        est = []
        for s in range(12):
            r = P.h1_run(formula_fe=FE, post_excl=days, accidents=fake_acc(acc, linked, "2021-12-31", risk, 900 + s), **kw)
            est.append({t: r["terms"][t]["rr_doubling"] for t in terms})
        out["fake_no_effect"][name] = {t: {"median": float(np.median([e[t] for e in est])),
                                           "min": float(min(e[t] for e in est)), "max": float(max(e[t] for e in est))}
                                       for t in terms}
        print("fake", name, out["fake_no_effect"][name], flush=True)
    for name, (kw, terms, days) in items.items():
        for label, pe in (("all_days", 0), ("post_accident_days_dropped", days)):
            r = P.h1_run(formula_fe=FE, post_excl=pe, **kw)
            out["real"].setdefault(name, {})[label] = {
                "n_accidents": r["n_accidents"], "n_plants": r["n_plants"], "fitted_by": r.get("fitted_by"),
                **{t: {"rr": round(r["terms"][t]["rr_doubling"], 4), "ci": [round(c, 4) for c in r["terms"][t]["ci"]],
                       "p": r["terms"][t]["p"]} for t in terms}}
            print("real", name, label, {t: (out["real"][name][label][t]["rr"], round(out["real"][name][label][t]["p"], 4))
                                        for t in terms}, flush=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
