"""Fresh test T3 of the planned-work lead (docs/planned_work_test.md; plan D11): National Response Center serious
reports linked by the author's review, on the H4 panel (TCEQ sites, RN-years with an outcome day), June 2003 to 2023.

Exposure as fixed in the test file: planned = log(1 + planned-work reports (MAINTENANCE, AIR STARTUP, AIR SHUTDOWN)
starting in days -7 to -1); unplanned = the same for EMISSIONS EVENT and EXCESS OPACITY; each with its statewide
total minus own. Primary-filter rules, plus: reports with an impossible date (after the data download, or starting
300 or more days after their own report date) are left out; in a same-start group whose kept report is in the
filed-in-error exclusion set, the occurrence is kept if any other report of the group is not excluded.
Model: y ~ planned + unplanned + xs_planned + xs_unplanned | RN-year + month of year, errors clustered by RN.
Primary outcome: linked NRC report days with no RMP accident at the same plant within 3 days; the version with all
linked NRC report days is shown beside it. Power check first (200 draws, planted 1.5). Decision rule as fixed:
confirmed if the 95% range is above 1; contradicted if its top is below 1.3; otherwise inconclusive.
Output: data/manifests/t3_planned_nrc.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402
import phase5_h4_o6 as H  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "t3_planned_nrc.json"
PLANNED = ("MAINTENANCE", "AIR STARTUP", "AIR SHUTDOWN")
UNPLANNED = ("EMISSIONS EVENT", "EXCESS OPACITY")
DOWNLOAD = pd.Timestamp("2026-10-02")
TERMS = ["planned", "unplanned", "xs_planned", "xs_unplanned"]


def occ_counts(ev, types, log):
    excl = P.exclusion("primary")
    e = ev[ev.event_type.isin(types) & ev.date_source.ne("none") & ev.rn.notna()].copy()
    e["day"] = e.event_datetime.dt.normalize()
    bad = (e.day > DOWNLOAD) | ((e.day - e.report_date).dt.days >= 300)
    log[f"impossible_dates_{types[0].split()[0].lower()}"] = int(bad.sum())
    e = e[~bad]
    e["occ"] = np.where(e.is_duplicate, e.dup_of, e.incident).astype(int)
    ok = e[~e.incident.isin(excl)]
    occ = ok.drop_duplicates("occ")[["occ"]]
    # each occurrence is placed and dated by its earliest report that is not excluded
    first = ok.sort_values("incident").drop_duplicates("occ")[["occ", "rn", "day"]]
    c = first.merge(occ, on="occ").groupby(["rn", "day"]).size()
    c.index = c.index.set_names(["plant_id", "day"])
    return c


def build_panel(ev, out_days, cp, cu):
    od = out_days.drop_duplicates(["unit", "day"])
    first_ok = P.DATA_START + pd.Timedelta(days=8)
    frames = []
    for (u, y), _ in od.groupby([od.unit, od.day.dt.year]):
        lo = max(pd.Timestamp(f"{y}-01-01"), P.h1.STUDY_START, first_ok)
        hi = min(pd.Timestamp(f"{y}-12-31"), P.h1.STUDY_END)
        frames.append(pd.DataFrame({"plant_id": u, "day": pd.date_range(lo, hi, freq="D")}))
    pan = pd.concat(frames, ignore_index=True)
    pan["year"], pan["moy"] = pan.day.dt.year, pan.day.dt.month
    pan["plant_year"] = pan.plant_id + "_" + pan.year.astype(str)
    yset = set(zip(od.unit, od.day))
    pan["y"] = [int((u, d) in yset) for u, d in zip(pan.plant_id, pan.day)]
    for name, c in (("planned", cp), ("unplanned", cu)):
        own = P.windowed(c, pan[["plant_id", "day"]], 7, 0, 8)
        pan["E_" + name] = own
        pan[name] = np.log1p(own)
        st = P.statewide(c, pan.day, 7, 0)
        pan["xs_" + name] = np.log1p((pan.day.map(st).values - own).clip(min=0))
    return pan


def term(r):
    t = r["terms"]["planned"]
    return {"rr": round(t["rr_doubling"], 3), "ci": [round(c, 3) for c in t["ci"]], "p": round(t["p"], 4),
            "n_outcome_days": r["n_accidents"], "n_sites": r["n_plants"], "n_strata": r["n_strata"]}


def decide(ci):
    return "confirmed" if ci[0] > 1 else "contradicted" if ci[1] < 1.3 else "inconclusive"


def main():
    plants, ev, acc, *_ = P.tables("v2")
    log = {}
    cp, cu = occ_counts(ev, PLANNED, log), occ_counts(ev, UNPLANNED, log)
    nrc = H.linked("nrc")
    units = set(cu.index.get_level_values(0)) | set(cp.index.get_level_values(0))
    nrc = nrc[nrc.unit.isin(units) & nrc.day.between(P.h1.STUDY_START, P.h1.STUDY_END)]
    # NRC report days with an RMP accident at the same plant within 3 days
    rn_plant = ev.dropna(subset=["plant_id"]).drop_duplicates("rn").set_index("rn").plant_id
    acc_days = acc.groupby("plant_id").date.apply(lambda s: s.dt.normalize().values)
    def near_rmp(u, d):
        p = rn_plant.get(u)
        if p is None or p not in acc_days.index:
            return False
        return bool((np.abs((acc_days[p] - np.datetime64(d)) / np.timedelta64(1, "D")) <= 3).any())
    nrc["near_rmp"] = [near_rmp(u, d) for u, d in zip(nrc.unit, nrc.day)]
    prim = nrc[~nrc.near_rmp]
    res = {"note": __doc__.split("Output:")[0].strip(), "exposure_log": log,
           "nrc_report_days_all": int(nrc.drop_duplicates(["unit", "day"]).shape[0]),
           "nrc_report_days_without_rmp_accident_within_3_days": int(prim.drop_duplicates(["unit", "day"]).shape[0])}
    pan = build_panel(ev, prim, cp, cu)
    res["panel"] = {"days": len(pan), "outcome_days": int(pan.y.sum()), "sites": int(pan.plant_id.nunique()),
                    "outcome_days_with_planned_last_week": int(((pan.y > 0) & (pan.E_planned > 0)).sum()),
                    "share_all_days_with_planned_last_week": round(float((pan.E_planned > 0).mean()), 4)}
    print(res["panel"], flush=True)
    # power check on the primary panel, before the real outcome is fitted
    b = np.log2(1.5)
    w = np.exp(b * pan.planned.values)
    rng = np.random.default_rng(31)
    k = pan.groupby("plant_year").y.sum()
    idx = pan.groupby("plant_year").indices
    hits = []
    for i in range(200):
        y = np.zeros(len(pan), dtype=int)
        for py, rows in idx.items():
            pr = w[rows] / w[rows].sum()
            np.add.at(y, rng.choice(rows, size=int(k[py]), replace=True, p=pr), 1)
        rf = P.fit(pan.assign(y=y), TERMS, "plant_year + moy", "poisson")
        hits.append(rf["terms"]["planned"]["ci"][0] > 1 if "planned" in rf["terms"] else False)
    res["power_planted_1.5"] = round(float(np.mean(hits)), 3)
    res["power_label"] = ("underpowered (below 50%)" if res["power_planted_1.5"] < 0.5 else "adequate") \
        if res["power_planted_1.5"] >= 0.2 else "not run: power below 20%"
    print("power", res["power_planted_1.5"], flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=str) + "\n")
    if res["power_planted_1.5"] < 0.2:
        return
    r = P.fit(pan, TERMS, "plant_year + moy", "poisson")
    res["T3_primary"] = term(r) | {"decision": decide(r["terms"]["planned"]["ci"])}
    pan_all = build_panel(ev, nrc, cp, cu)
    r = P.fit(pan_all, TERMS, "plant_year + moy", "poisson")
    res["T3_all_nrc_reports"] = term(r) | {"decision_if_primary": decide(r["terms"]["planned"]["ci"])}
    OUT.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "note"}, indent=1, default=str))


if __name__ == "__main__":
    main()
