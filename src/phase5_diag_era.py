"""Diagnostic added after R12 was seen (D9): on what time scale does the association live? H1 with strata by plant
(R12), then by plant and 5-, 3- and 2-year era, then by plant-year (primary), each with year and month-of-year
effects. Eras are fixed calendar blocks from 2003 (2003-2007, 2008-2012, ... for 5 years).
Output: data/manifests/phase5_diag_era.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_era.json"


def era(n):
    def add(pan):
        pan["plant_era"] = pan.plant_id + "_" + ((pan.year - 2003) // n).astype(str)
        return pan
    return add


def main():
    out = {}
    specs = [("plant_only_R12", dict(formula_fe="plant_id + year + moy")),
             ("plant_x_5yr", dict(formula_fe="plant_era + year + moy", extra_cols=era(5))),
             ("plant_x_3yr", dict(formula_fe="plant_era + year + moy", extra_cols=era(3))),
             ("plant_x_2yr", dict(formula_fe="plant_era + year + moy", extra_cols=era(2))),
             ("plant_year_primary", dict())]
    for name, kw in specs:
        r = P.h1_run(**kw)
        t = r["terms"]["x"]
        out[name] = {"rr": round(t["rr_doubling"], 4), "ci": [round(c, 4) for c in t["ci"]], "p": t["p"],
                     "n_accidents": r["n_accidents"], "n_days": r["n_days"], "fitted_by": r.get("fitted_by")}
        print(name, out[name], flush=True)
        OUT.write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
