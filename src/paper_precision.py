"""Values the paper quotes whose stored, rounded form sits on a rounding boundary (for example 1.365), recomputed at
full precision with the same code, so the paper rounds them correctly. Nothing else is changed: each script is run
with its rounding turned off and its output sent to a scratch file instead of its manifest.
Output: data/manifests/paper_precision.json
"""
import functools
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_own_reports as OR  # noqa: E402
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "paper_precision.json"
TMP = Path(tempfile.mkdtemp())


def unrounded(mod, name):
    mod.round = lambda x, n=None: x
    mod.OUT = TMP / f"{name}.json"
    mod.main()
    return json.loads(mod.OUT.read_text())


def main():
    res = {"note": __doc__.split("Output:")[0].strip()}
    plants, ev, acc, *_ = P.tables("v2")
    cnt = P.event_counts(ev)
    linked = set(plants.loc[plants.linked, "plant_id"])
    a = acc[acc.plant_id.isin(linked)]
    cc, _ = OR.remove_after(cnt, pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values}), 2)
    t = P.h1_run(window=365, exposures={"x": cc}, statewide_counts=cnt)["terms"]["x"]
    res["own_reports_removed_window_365"] = {"rr": t["rr_doubling"], "ci": list(t["ci"])}
    print(res, flush=True)
    sim = pd.DataFrame(json.loads((ROOT / "data/manifests/sim_design_trap.json").read_text())["draws"])
    res["sim_medians"] = {s: {c: float(np.median(g[c])) for c in ("naive_90", "fixed_90", "naive_365", "fixed_365")}
                          for s, g in sim.groupby("scenario")}
    import t3_planned_nrc as T3
    res["T3_primary"] = unrounded(T3, "t3")["T3_primary"]
    print(res["T3_primary"], flush=True)
    import phase5_h4_o6 as H
    h = unrounded(H, "h4o6")
    res["O6_end_2021"] = h["O6_end_2021"]
    res["H4_end_2021_own_reports_removed"] = h["H4_end_2021_own_reports_removed"]
    print(res["O6_end_2021"], flush=True)
    import phase5_h2h3 as HH
    HH.h3_measures = functools.partial(HH.h3_measures, B=20)
    hh = unrounded(HH, "h2h3")
    res["H3_test_2016_2021_point"] = {k: hh["H3_test_2016_2021"][k] for k in ("baseline", "with_events")}
    res["H3_test_2016_2021_point"]["auc_roc_gain"] = hh["H3_test_2016_2021"]["auc_roc_gain"]["value"]
    OUT.write_text(json.dumps(res, indent=1, default=float) + "\n")
    print(json.dumps(res, indent=1, default=float)[:3000])


if __name__ == "__main__":
    main()
