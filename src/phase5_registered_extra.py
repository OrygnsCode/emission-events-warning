"""Two registered secondary exposures (plan section 3.4) that had not been run (plan D16 item 1): duration of
unplanned events, and maintenance, startup and shutdown reports counted on their own over 90 days. H1 design (window
90, gap 7, end 2021); as registered and with the plant's own reports from the accident day and the 2 days after
removed. Outside the Holm family.
Output: data/manifests/phase5_registered_extra.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_own_reports as OR  # noqa: E402
import phase5_diag_planned as DP  # noqa: E402
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "phase5_registered_extra.json"
CAP = 720.0


def term(r):
    x = r["terms"]["x"]
    return {"rr": round(x["rr_doubling"], 4), "ci": [round(c, 4) for c in x["ci"]], "p": round(x["p"], 4),
            "n_accidents": r["n_accidents"]}


def durations(ev):
    excl = P.exclusion("primary")
    e = ev[ev.event_type.eq("EMISSIONS EVENT") & ev.date_source.ne("none") & ev.plant_id.notna()
           & ~ev.incident.isin(excl) & ~ev.is_duplicate].copy()
    d = pd.read_parquet(ROOT / "data/derived/details_table.parquet", columns=["incident", "start_text", "end_text"])
    d["incident"] = d.incident.astype(e.incident.dtype)
    e = e.merge(d.drop_duplicates("incident"), on="incident", how="left")
    st = pd.to_datetime(e.start_text, format=DP.FMT, errors="coerce")
    en = pd.to_datetime(e.end_text, format=DP.FMT, errors="coerce")
    h = (en - st).dt.total_seconds() / 3600
    log = {"occurrences": len(e), "unreadable": int(h.isna().sum()), "negative": int((h < 0).sum()),
           "capped_at_720h": int((h > CAP).sum())}
    e["hours"] = h.where(h >= 0).clip(upper=CAP)
    e = e.dropna(subset=["hours"])
    e["day"] = e.event_datetime.dt.normalize()
    s = e.groupby(["plant_id", "day"]).hours.sum()
    s.index = s.index.set_names(["plant_id", "day"])
    log["median_hours"] = round(float(e.hours.median()), 2)
    return s, log


def main():
    plants, ev, acc, *_ = P.tables("v2")
    linked = set(plants.loc[plants.linked, "plant_id"])
    a = acc[acc.plant_id.isin(linked)]
    ad = pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values})
    cnt = P.event_counts(ev)
    res = {"note": __doc__.split("Output:")[0].strip()}
    hrs, log = durations(ev)
    res["duration_log"] = log
    hc, removed = OR.remove_after(hrs, ad, 2)
    res["duration"] = {"registered_design": term(P.h1_run(exposures={"x": hrs}, statewide_counts=cnt)),
                       "own_reports_removed": term(P.h1_run(exposures={"x": hc}, statewide_counts=cnt)),
                       "hours_removed": round(float(removed), 1)}
    print("duration", res["duration"], flush=True)
    cp = DP.counts(DP.planned_reports(ev))
    cp.index = cp.index.set_names(["plant_id", "day"])
    pc, removed = OR.remove_after(cp, ad, 2)
    res["planned_90_days"] = {"registered_design": term(P.h1_run(exposures={"x": cp}, statewide_counts=cp)),
                              "own_reports_removed": term(P.h1_run(exposures={"x": pc}, statewide_counts=cp)),
                              "reports_removed": removed}
    print("planned 90", res["planned_90_days"], flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
