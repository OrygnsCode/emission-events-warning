"""Planned-work checks kept in the repository (plan D16 item 4; they were first computed in separate scratch code):
on the base model of phase5_diag_planned.py (planned and unplanned report counts starting in days -7 to -1, each with
its own statewide control, end 2021):
  yes_no       any planned report in days -7 to -1 (0 or 1), rate ratio exp(beta)
  drop_top2    the two plants with the most accident days after planned work left out
  year_out     each calendar year with such an accident left out in turn (smallest and largest estimate, largest p)
  eras         2003 to 2005, 2006 to 2010, 2011 to 2021 separately
Output: data/manifests/phase5_diag_planned_extra.json
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_planned as DP  # noqa: E402
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_planned_extra.json"
TERMS = ["planned", "unplanned", "xs_planned", "xs_unplanned"]


def rr(r, t="planned"):
    x = r["terms"][t]
    return {"rr": round(x["rr_doubling"], 3), "ci": [round(c, 3) for c in x["ci"]], "p": round(x["p"], 4)}


def main():
    plants, ev, *_ = P.tables("v2")
    cp = DP.counts(DP.planned_reports(ev))
    cu = P.event_counts(ev, DP.UNPLANNED)
    r0 = P.h1_run(end="2021-12-31", exposures={"planned": (cp, 7, 0), "unplanned": (cu, 7, 0)}, statewide_each=True,
                  keep_panel=True)
    pan = r0["panel"]
    res = {"note": __doc__.split("Output:")[0].strip(), "base": rr(r0) | {"n_accidents": r0["n_accidents"]}}
    hits = pan[(pan.y > 0) & (pan.E_planned > 0)]
    res["hits"] = {"accident_days": int(len(hits)), "plants": int(hits.plant_id.nunique()),
                   "years": sorted(int(y) for y in hits.year.unique())}
    p2 = pan.assign(planned_any=(pan.E_planned > 0).astype(int))
    x = P.fit(p2, ["planned_any"] + TERMS[1:], "plant_year + moy", "poisson")["terms"]["planned_any"]
    res["yes_no"] = {"rr": round(math.exp(x["beta"]), 3),
                     "ci": [round(math.exp(x["beta"] + s * 1.96 * x["se"]), 3) for s in (-1, 1)], "p": round(x["p"], 4)}
    top2 = hits.plant_id.value_counts().head(2)
    sub = pan[~pan.plant_id.isin(top2.index)]
    res["drop_top2"] = rr(P.fit(sub, TERMS, "plant_year + moy", "poisson")) | {"cases_removed": int(top2.sum())}
    yo = []
    for y in res["hits"]["years"]:
        t = P.fit(pan[pan.year != y], TERMS, "plant_year + moy", "poisson")["terms"]["planned"]
        yo.append((t["rr_doubling"], t["p"]))
    res["year_out"] = {"years": len(yo), "min_rr": round(min(v for v, _ in yo), 3),
                       "max_rr": round(max(v for v, _ in yo), 3), "max_p": round(max(p for _, p in yo), 4)}
    res["eras"] = {}
    for name, lo, hi in (("2003_2005", 2003, 2005), ("2006_2010", 2006, 2010), ("2011_2021", 2011, 2021)):
        sub = pan[pan.year.between(lo, hi)]
        res["eras"][name] = rr(P.fit(sub, TERMS, "plant_year + moy", "poisson")) | {
            "accident_days_after_planned": int(((sub.y > 0) & (sub.E_planned > 0)).sum())}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "note"}, indent=1))


if __name__ == "__main__":
    main()
