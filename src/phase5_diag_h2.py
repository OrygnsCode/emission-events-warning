"""Diagnostic added after H2 was seen (D9): is the H2/H2b association carried by accident aftermath? (a) all H2b
coefficients printed; (b) H2b plus accidents in the previous calendar year; (c) H2b with prior-year events counted
without events in the 30 days after any accident at the plant.
Output: data/manifests/phase5_diag_h2.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402
import phase5_h2h3 as H  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_h2.json"


def main():
    pan, _ = H.build(list(range(2004, 2022)))
    pan["log_fte"] = np.log1p(pan.fte_zero_missing)
    pan["log_maxq"] = np.log1p(pan.maxq)
    pan["log_nproc"] = np.log1p(pan.nproc)
    pan = pan.dropna(subset=["log_fte", "log_maxq", "log_nproc", "sector"]).reset_index(drop=True)
    base = ["prior_acc5", "log_fte", "log_maxq", "log_nproc", "log_emis", "no_nei", "inspections", "violations", "enforcement"]
    out = {}
    m = H.poisson(pan, ["x"] + base)
    out["H2b_all_terms"] = {t: H.coef(m, t) for t in ["x"] + base}
    plants, ev, acc, acc_all, risk = P.tables("v2")
    yearly = acc.assign(year=acc.date.dt.year).groupby(["plant_id", "year"]).size()
    pan["acc_prev_year"] = np.log1p([yearly.get((p, y - 1), 0) for p, y in zip(pan.plant_id, pan.year)])
    m = H.poisson(pan, ["x", "acc_prev_year"] + base)
    out["H2b_plus_previous_year_accidents"] = {"x": H.coef(m), "acc_prev_year": H.coef(m, "acc_prev_year")}
    # events in the prior year without those in the 30 days after an accident at the plant
    cnt = P.event_counts(ev).rename("n").reset_index()
    cnt.columns = ["plant_id", "day", "n"]
    ad = {p: g.date.values.astype("datetime64[D]") for p, g in acc.groupby("plant_id")}
    after = np.zeros(len(cnt), dtype=bool)
    for p, idx in cnt.groupby("plant_id").indices.items():
        a = ad.get(p)
        if a is None:
            continue
        d = cnt.day.values[idx].astype("datetime64[D]")
        lag = (d[:, None] - a[None, :]).astype(int)          # days since each accident at the plant
        after[idx] = ((lag >= 0) & (lag <= 30)).any(axis=1)
    clean = cnt[~after]
    by = clean.assign(year=clean.day.dt.year).groupby(["plant_id", "year"]).n.sum()
    pan["x_clean"] = np.log1p([by.get((p, y - 1), 0) for p, y in zip(pan.plant_id, pan.year)])
    m = H.poisson(pan, ["x_clean"] + base)
    out["H2b_events_without_30_days_after_accidents"] = {"x_clean": H.coef(m, "x_clean"),
                                                        "events_removed": int(cnt.n[after].sum()),
                                                        "events_total": int(cnt.n.sum())}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
