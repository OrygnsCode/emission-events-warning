"""Time-scale check (D9) rerun with each plant's reports from the accident day and the 2 days after removed
(plan D15). Strata by plant (R12), by plant and 5-, 3- and 2-year block, and by plant-year, each with year and
month-of-year effects as in src/phase5_diag_era.py; every day kept; statewide count unchanged.
Output: data/manifests/phase5_diag_era_own_removed.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_era as E  # noqa: E402
import phase5_diag_own_reports as OR  # noqa: E402
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_era_own_removed.json"


def main():
    plants, ev, acc, *_ = P.tables("v2")
    cnt = P.event_counts(ev)
    linked = set(plants.loc[plants.linked, "plant_id"])
    a = acc[acc.plant_id.isin(linked)]
    cc, removed = OR.remove_after(cnt, pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values}), 2)
    out = {"note": __doc__.split("Output:")[0].strip(), "events_removed": removed}
    specs = [("plant_only_R12", dict(formula_fe="plant_id + year + moy")),
             ("plant_x_5yr", dict(formula_fe="plant_era + year + moy", extra_cols=E.era(5))),
             ("plant_x_3yr", dict(formula_fe="plant_era + year + moy", extra_cols=E.era(3))),
             ("plant_x_2yr", dict(formula_fe="plant_era + year + moy", extra_cols=E.era(2))),
             ("plant_year_primary", dict())]
    for name, kw in specs:
        r = P.h1_run(exposures={"x": cc}, statewide_counts=cnt, **kw)
        t = r["terms"]["x"]
        out[name] = {"rr": round(t["rr_doubling"], 4), "ci": [round(c, 4) for c in t["ci"]], "p": t["p"],
                     "n_accidents": r["n_accidents"], "n_days": r["n_days"], "fitted_by": r.get("fitted_by")}
        print(name, out[name], flush=True)
        OUT.write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
