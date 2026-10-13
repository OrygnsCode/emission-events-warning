"""Exploratory test A (plan D14 item 3, with the matching change logged the same day before running): unplanned
emission events that release a chemical the plant handles in its RMP processes.

Exposure: kept unplanned emission-event occurrences (same filters, merge and exclusion set as the primary count)
with at least one listed contaminant matching one of the plant's RMP process chemicals (any filing; components of
flammable mixtures included; confidential "CBI" entries left out). Name matching as in D14. Model as H1 (window
90, gap 7, end 2021); statewide count: the same matched count at all other plants. Shown as registered and with the
plant's matched reports on accident days and the 2 days after removed.
Output: data/manifests/phase5_same_chemical.json
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_own_reports as OR  # noqa: E402
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
RAW = ROOT / "data" / "slices" / "rmp_raw"
OUT = ROOT / "data" / "manifests" / "phase5_same_chemical.json"
R = dict(dtype=str, keep_default_na=False)


def candidates(name):
    s = str(name)
    parts = [s] + re.split(r"[\[\]()]", s)
    out = set()
    for p in parts:
        p = re.sub(r",\s*n-\s*$", "", p.strip(), flags=re.I)
        p = re.sub(r"^n-", "", p.strip(), flags=re.I)
        k = re.sub(r"[^a-z0-9]", "", p.lower())
        if len(k) >= 3:
            out.add(k)
    return out


def plant_chemicals():
    chem = pd.read_csv(RAW / "tlkpChemicals.csv.gz", **R)
    chem = chem[~chem.ChemicalName.str.upper().str.startswith("CBI")]
    cand = {r.ChemicalID: candidates(r.ChemicalName) for r in chem.itertuples()}
    fac = pd.read_csv(RAW / "tblS1Facilities.csv.gz", usecols=["FacilityID", "EPAFacilityID"], **R)
    proc = pd.read_csv(RAW / "tblS1Processes.csv.gz", usecols=["ProcessID", "FacilityID"], **R)
    pc = pd.read_csv(RAW / "tblS1ProcessChemicals.csv.gz", usecols=["ProcessChemicalID", "ProcessID", "ChemicalID"], **R)
    fm = pd.read_csv(RAW / "tblS1FlammableMixtureChemicals.csv.gz", usecols=["ProcessChemicalID", "ChemicalID"], **R)
    pcs = pd.concat([pc[["ProcessChemicalID", "ProcessID", "ChemicalID"]],
                     fm.merge(pc[["ProcessChemicalID", "ProcessID"]], on="ProcessChemicalID")[
                         ["ProcessChemicalID", "ProcessID", "ChemicalID"]]])
    x = pcs.merge(proc, on="ProcessID").merge(fac, on="FacilityID")
    pm = pd.read_csv(ROOT / "data/derived/plant_members_v2.csv", **R)
    rmp = pm[pm.id_type.eq("RMP")].rename(columns={"id": "EPAFacilityID"})[["plant_id", "EPAFacilityID"]]
    x = x.merge(rmp, on="EPAFacilityID")
    out = {}
    for p, g in x.groupby("plant_id"):
        s = set()
        for c in g.ChemicalID.unique():
            s |= cand.get(c, set())
        out[p] = s
    return out


def main():
    plants, ev, *_ = P.tables("v2")
    chems = plant_chemicals()
    con = pd.read_csv(ROOT / "data/derived/contaminants.csv.gz", usecols=["incident", "description"])
    names = con.description.dropna().unique()
    cmap = {n: candidates(n) for n in names}
    excl = P.exclusion("primary")
    e = ev[ev.event_type.eq("EMISSIONS EVENT") & ev.date_source.ne("none") & ev.plant_id.notna()
           & ~ev.incident.isin(excl)].copy()
    e["occ"] = np.where(e.is_duplicate, e.dup_of, e.incident).astype(int)
    cons = con.dropna().groupby("incident").description.apply(list)
    def flag(inc, plant):
        cs = chems.get(plant)
        if not cs:
            return False
        return any(cmap[d] & cs for d in cons.get(inc, []))
    e["match"] = [flag(i, p) for i, p in zip(e.incident, e.plant_id)]
    occ_match = e.groupby("occ").match.any()
    kept = e[~e.is_duplicate].copy()
    kept["match"] = kept.occ.map(occ_match).fillna(False)
    kept["day"] = kept.event_datetime.dt.normalize()
    cnt = kept[kept.match].groupby(["plant_id", "day"]).size()
    cnt.index = cnt.index.set_names(["plant_id", "day"])
    all_cnt = P.event_counts(ev)
    # match rates
    with_con = kept.incident.isin(cons.index)
    res = {"note": __doc__.split("Output:")[0].strip(),
           "plants_with_rmp_chemicals": len(chems),
           "kept_occurrences_with_contaminants": int(with_con.sum()),
           "matched_occurrences": int(kept.match.sum()),
           "share_matched": round(float(kept.match.sum() / max(with_con.sum(), 1)), 3)}
    top = pd.Series([d for i, p in zip(e[e.match].incident, e[e.match].plant_id) for d in cons.get(i, [])
                     if cmap[d] & chems.get(p, set())]).value_counts().head(10)
    res["top_matched_contaminants"] = top.to_dict()
    print({k: v for k, v in res.items() if k != "note"}, flush=True)
    r = P.h1_run(exposures={"x": cnt}, statewide_counts=cnt)
    t = r["terms"]["x"]
    res["registered_design"] = {"rr": round(t["rr_doubling"], 3), "ci": [round(c, 3) for c in t["ci"]],
                                "p": round(t["p"], 4), "n_accidents": r["n_accidents"]}
    plants_l = set(plants.loc[plants.linked, "plant_id"])
    _, _, acc, *_ = P.tables("v2")
    a = acc[acc.plant_id.isin(plants_l)]
    cc, removed = OR.remove_after(cnt, pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values}), 2)
    r = P.h1_run(exposures={"x": cc}, statewide_counts=cnt)
    t = r["terms"]["x"]
    res["own_reports_removed"] = {"rr": round(t["rr_doubling"], 3), "ci": [round(c, 3) for c in t["ci"]],
                                  "p": round(t["p"], 4), "n_accidents": r["n_accidents"], "events_removed": removed}
    OUT.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(res["registered_design"], res["own_reports_removed"])


if __name__ == "__main__":
    main()
