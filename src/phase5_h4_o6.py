"""Phase 5: H4 (National Response Center reports as the outcome, every TCEQ site with emission events) and O6 (OSHA
records as the outcome at RMP-linked plants), by the rules of plan D11, written after the author's link review and
before this was run. Links: data/manual/outcome_link_decisions.json (only reports the author linked).
Output: data/manifests/phase5_h4_o6.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "phase5_h4_o6.json"
WINDOW, GAP = 90, 7


def linked(source):
    dec = json.loads((ROOT / "data/manual/outcome_link_decisions.json").read_text())["decisions"]
    items = json.loads((ROOT / "data/derived/outcome_link_items.json").read_text())[source]
    rows = [(i["key"], dec[i["key"]], pd.Timestamp(i["date"])) for i in items
            if i["candidates"] and dec.get(i["key"]) not in (None, "none", "unsure")]
    return pd.DataFrame(rows, columns=["key", "unit", "day"])


def term(r, t="x"):
    x = r["terms"][t]
    return {"rr": round(x["rr_doubling"], 3), "ci": [round(c, 3) for c in x["ci"]], "p": round(x["p"], 4),
            "n_outcome_days": r["n_accidents"], "n_units": r["n_plants"], "n_strata": r["n_strata"]}


def rn_counts(ev, drop=None):
    """Kept unplanned emission-event occurrences per (RN, day), H1 filters but no plant link needed."""
    excl = P.exclusion("primary")
    e = ev[ev.event_type.eq("EMISSIONS EVENT") & ev.date_source.ne("none") & ev.rn.notna() & ~ev.incident.isin(excl)
           & ~ev.is_duplicate]
    c = e.assign(day=e.event_datetime.dt.normalize()).groupby(["rn", "day"]).size()
    c.index = c.index.set_names(["plant_id", "day"])
    if drop is not None:
        c = c[[k not in drop for k in c.index]]
    return c


def h4(ev, out_days, end, drop_k=None):
    end = pd.Timestamp(end)
    od = out_days[out_days.day.between(P.h1.STUDY_START, end)].drop_duplicates(["unit", "day"])
    drop = None
    if drop_k is not None:
        drop = {(u, d + pd.Timedelta(days=j)) for u, d in zip(od.unit, od.day) for j in range(drop_k + 1)}
    cnt = rn_counts(ev, drop)
    cnt_full = rn_counts(ev)
    units = set(cnt_full.index.get_level_values(0))
    od = od[od.unit.isin(units)]
    first_ok = P.DATA_START + pd.Timedelta(days=WINDOW + GAP)
    frames = []
    for (u, y), _ in od.groupby([od.unit, od.day.dt.year]):
        lo = max(pd.Timestamp(f"{y}-01-01"), P.h1.STUDY_START, first_ok)
        hi = min(pd.Timestamp(f"{y}-12-31"), end)
        frames.append(pd.DataFrame({"plant_id": u, "day": pd.date_range(lo, hi, freq="D")}))
    pan = pd.concat(frames, ignore_index=True)
    pan["year"], pan["moy"] = pan.day.dt.year, pan.day.dt.month
    pan["plant_year"] = pan.plant_id + "_" + pan.year.astype(str)
    yset = set(zip(od.unit, od.day))
    pan["y"] = [int((u, d) in yset) for u, d in zip(pan.plant_id, pan.day)]
    pad = WINDOW + GAP + 1
    pan["E"] = P.windowed(cnt, pan[["plant_id", "day"]], WINDOW, GAP, pad)
    pan["x"] = np.log1p(pan.E)
    own_full = P.windowed(cnt_full, pan[["plant_id", "day"]], WINDOW, GAP, pad)
    st = P.statewide(cnt_full, pan.day, WINDOW, GAP)
    pan["xs"] = np.log1p((pan.day.map(st).values - own_full).clip(min=0))
    r = P.fit(pan, ["x", "xs"], "plant_year + moy", "poisson")
    return r, pan


def main():
    plants, ev, *_ = P.tables("v2")
    res = {"note": __doc__.split("Links:")[0].strip()}
    nrc = linked("nrc")
    res["h4_links"] = {"linked_reports": len(nrc), "sites": int(nrc.unit.nunique()),
                       "site_days": int(nrc.drop_duplicates(["unit", "day"]).shape[0])}
    for end in ("2021-12-31", "2023-12-31"):
        r, pan = h4(ev, nrc, end)
        res[f"H4_end_{end[:4]}"] = term(r)
        r2, _ = h4(ev, nrc, end, drop_k=2)
        res[f"H4_end_{end[:4]}_own_reports_removed"] = term(r2)
        print("H4", end, res[f"H4_end_{end[:4]}"], res[f"H4_end_{end[:4]}_own_reports_removed"], flush=True)
        if end == "2021-12-31":
            res["H4_end_2021"]["sites_linked_to_rmp_plants"] = int(
                pan.drop_duplicates("plant_id").plant_id.isin(set(ev.loc[ev.plant_id.notna(), "rn"])).sum())
    osha = linked("osha")
    res["o6_links"] = {"linked_records": len(osha), "plants": int(osha.unit.nunique())}
    o = osha[osha.day >= "2015-01-01"].drop_duplicates(["unit", "day"])
    acc = pd.DataFrame({"plant_id": o.unit.values, "date": o.day.values, "AccidentHistoryID": o.unit.values})
    res["o6_links"]["plant_days_from_2015"] = len(acc)
    cnt = P.event_counts(ev)
    for end in ("2021-12-31", "2023-12-31"):
        r = P.h1_run(end=end, accidents=acc)
        res[f"O6_end_{end[:4]}"] = term(r) | {"log": r["log"]}
        a = acc[acc.date <= end]
        drop = {(p, d + pd.Timedelta(days=j)) for p, d in zip(a.plant_id, a.date) for j in range(3)}
        cc = cnt[[k not in drop for k in cnt.index]]
        r2 = P.h1_run(end=end, accidents=acc, exposures={"x": cc}, statewide_counts=cnt)
        res[f"O6_end_{end[:4]}_own_reports_removed"] = term(r2)
        print("O6", end, res[f"O6_end_{end[:4]}"], res[f"O6_end_{end[:4]}_own_reports_removed"], flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
