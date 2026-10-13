"""Phase 5, part C: N1 negative control, concordance and the exploratory breakdowns (plan 6.3, 3.4, 5.6, D4 item 6).

N1        accidents at OTHER linked plants in the same county and sector, as the outcome of this plant's events
          (statewide count in): should come out null. Each real accident at plant q becomes an outcome at every
          other linked plant p with p's county and sector equal to q's.
concord   how often an RMP accident also appears as a TCEQ report at the same plant starting within 2 days of it
          (any event type), overall and by period. Descriptive.
5.6       H1 by sector (refining, chemicals, gas processing, other) and by region group (TCEQ regions 12 Houston,
          10 Beaumont, 14 Corpus Christi, all others), and with the exposure split by frozen cause category and by
          frozen unit-type flag (one model each, each with the statewide total). Estimates with intervals, no tests.
          Cells with fewer than 5 plants or 5 accidents are suppressed (D4 item 6).
Output: data/manifests/phase5_other.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_exposures as X  # noqa: E402
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "phase5_other.json"
REGION_GROUP = {"REGION 12 - HOUSTON": "houston", "REGION 10 - BEAUMONT": "beaumont",
                "REGION 14 - CORPUS CHRISTI": "corpus_christi"}


def est(r, term="x"):
    t = r["terms"][term]
    ok = r["n_plants"] >= 5 and r["n_accidents"] >= 5
    return {"rr": round(t["rr_doubling"], 4) if ok else None,
            "ci": [round(c, 4) for c in t["ci"]] if ok else None, "p": t["p"] if ok else None,
            "n_accidents": r["n_accidents"] if ok else "<5 or fewer than 5 plants (suppressed)",
            "n_plants": r["n_plants"] if ok else None}


def main():
    plants, ev, acc, acc_all, risk = P.tables("v2")
    attrs = pd.read_csv(P.DER / "plant_attributes.csv").set_index("plant_id")
    linked = set(plants.loc[plants.linked, "plant_id"])
    out = {}
    # N1
    a = acc[acc.plant_id.isin(linked) & acc.date.between(P.h1.STUDY_START, pd.Timestamp("2021-12-31"))]
    la = attrs.loc[sorted(linked)]
    grp = la.groupby(["county", "sector"]).groups
    rows = []
    for q, d in zip(a.plant_id, a.date):
        key = (attrs.at[q, "county"], attrs.at[q, "sector"])
        for p in grp.get(key, []):
            if p != q:
                rows.append((p, d))
    pseudo = pd.DataFrame(rows, columns=["plant_id", "date"])
    pseudo["O1"] = True
    r = P.h1_run(accidents=pseudo)
    out["N1_other_plants_same_county_sector"] = {**est(r), "pseudo_outcomes": len(pseudo),
                                                 "real_accidents_with_a_neighbour": int(
                                                     sum(len(grp.get((attrs.at[q, "county"], attrs.at[q, "sector"]), []))
                                                         > 1 for q in a.plant_id))}
    print("N1", out["N1_other_plants_same_county_sector"], flush=True)
    # concordance
    e = ev.dropna(subset=["plant_id"])
    e = e[e.date_source.ne("none")]
    by = {p: g.event_datetime.dt.normalize().values for p, g in e.groupby("plant_id")}
    hit = []
    for p, d in zip(a.plant_id, a.date):
        ds = by.get(p)
        hit.append(bool(ds is not None and (np.abs((ds - np.datetime64(d)) / np.timedelta64(1, "D")) <= 2).any()))
    a = a.assign(in_tceq=hit, period=np.select([a.date.dt.year <= 2005, a.date.dt.year <= 2014],
                                               ["2003-2005", "2006-2014"], "2015-2021"))
    out["concordance"] = {"accidents": len(a), "with_tceq_report_within_2_days": int(a.in_tceq.sum()),
                          "share": round(float(a.in_tceq.mean()), 3),
                          "by_period": a.groupby("period").in_tceq.agg(["size", "mean"]).round(3).to_dict(orient="index")}
    print("concordance", out["concordance"], flush=True)
    # 5.6 by sector and region group
    for s in ("refining", "chemicals", "gas_processing", "other"):
        keep = set(attrs.index[attrs.sector.eq(s)]) & linked
        r = P.h1_run(accidents=acc[acc.plant_id.isin(keep)])
        out[f"sector_{s}"] = est(r)
        print("sector", s, out[f"sector_{s}"], flush=True)
    rg = attrs.region.map(REGION_GROUP).fillna("other_regions")
    for g in ("houston", "beaumont", "corpus_christi", "other_regions"):
        keep = set(attrs.index[rg.eq(g)]) & linked
        r = P.h1_run(accidents=acc[acc.plant_id.isin(keep)])
        out[f"region_{g}"] = est(r)
        print("region", g, out[f"region_{g}"], flush=True)
    # 5.6 by cause and by unit type: exposure = events of that kind, statewide total kept
    cnt = P.event_counts(ev)
    c = pd.read_csv(P.DER / "causes.csv.gz")
    c = c.set_index("incident").reindex(ev.incident.values)
    for cause in sorted(c.primary_cause.dropna().unique()):
        w = X.kept_indicator(ev, (c.primary_cause == cause).values)
        r = P.h1_run(exposures={"x": P.event_counts(ev, weight=w)}, statewide_counts=cnt)
        out[f"cause_{cause}"] = est(r)
        print("cause", cause, out[f"cause_{cause}"], flush=True)
    for u in [k for k in c.columns if k.startswith("unit_")]:
        w = X.kept_indicator(ev, c[u].fillna(False).astype(bool).values)
        r = P.h1_run(exposures={"x": P.event_counts(ev, weight=w)}, statewide_counts=cnt)
        out[u] = est(r)
        print(u, out[u], flush=True)
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
