"""Incident lists for the H1 count variants (plan section 3.4, R13, R17, and D6 item 1). No accident data is read.

Writes data/derived/h1_exclusion_sets.json (the counts also to data/manifests/h1_exclusion_counts.json) with:
  primary:      reports whose text says they duplicate another (frozen rule status_duplicate) -> not counted
  r17:          primary + frozen not_reportable + frozen filed_in_error
  r17_extended: r17 + NARROW_NON_EVENT hits (never happened, cancelled, rescinded, voided, should not have been filed)
  r30_absorbed: reports absorbed into another occurrence under R30 (on top of the primary exclusions):
                - a report that names another report's incident number at the same plant within 7 days: the pair is
                  one occurrence; the later-dated report is absorbed (the occurrence keeps the earliest date);
                - a report with split, continuation or duplicate wording (NARROW_DUPLICATE) that names no usable
                  number: absorbed if the same plant has another report in the 7 days before it.
Each list is passed to h1.daily_counts(exclude_incidents=...).
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from census_event_text import INC_REF, NARROW_DUPLICATE, NARROW_NON_EVENT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DER = ROOT / "data" / "derived"


def main():
    ev = pd.read_csv(DER / "events_v2.csv.gz", parse_dates=["event_datetime"])
    st = pd.read_csv(DER / "causes.csv.gz", usecols=["incident", "status_duplicate", "status_not_reportable",
                                                     "status_filed_in_error"])
    d = pd.read_parquet(DER / "details_table.parquet", columns=["incident", "cause", "actions_taken", "basis"])
    d["incident"] = d.incident.astype(int)
    e = ev.merge(st, on="incident", how="left").merge(d, on="incident", how="left")
    text = (e.cause.fillna("") + " | " + e.actions_taken.fillna("") + " | " + e.basis.fillna("")).str.upper()
    f = lambda c: e[c].fillna(False).astype(bool)  # noqa: E731
    primary = set(e.incident[f("status_duplicate")])
    r17 = primary | set(e.incident[f("status_not_reportable") | f("status_filed_in_error")])
    ne = pd.Series(False, index=e.index)
    for pat in NARROW_NON_EVENT.values():
        ne |= text.str.contains(pat, flags=re.I, regex=True)
    r17x = r17 | set(e.incident[ne])

    # R30
    by_inc = e.set_index("incident")
    absorbed, cited_pairs = set(), 0
    for inc, t, pid, dtm in zip(e.incident, text, e.plant_id, e.event_datetime):
        if pd.isna(pid) or pd.isna(dtm):
            continue
        for m in INC_REF.finditer(t):
            r = int(m.group(1))
            if r == inc or r not in by_inc.index:
                continue
            o = by_inc.loc[r]
            if o.plant_id == pid and pd.notna(o.event_datetime) and abs((o.event_datetime - dtm).days) <= 7:
                cited_pairs += 1
                later = inc if (dtm, inc) > (o.event_datetime, r) else r
                absorbed.add(later)
    dup = pd.Series(False, index=e.index)
    for pat in NARROW_DUPLICATE.values():
        dup |= text.str.contains(pat, flags=re.I, regex=True)
    e_sorted = e.dropna(subset=["plant_id", "event_datetime"]).sort_values("event_datetime")
    word_only = 0
    for pid, g in e_sorted[dup.reindex(e_sorted.index).values].groupby("plant_id"):
        allp = e_sorted[e_sorted.plant_id == pid]
        for inc, dtm in zip(g.incident, g.event_datetime):
            if inc in absorbed:
                continue
            prior = allp[(allp.event_datetime < dtm) & (allp.event_datetime >= dtm - pd.Timedelta(days=7))
                         & (allp.incident != inc)]
            if len(prior):
                absorbed.add(inc)
                word_only += 1
    out = {"primary": sorted(primary), "r17": sorted(r17), "r17_extended": sorted(r17x),
           "r30_absorbed": sorted(absorbed - primary),
           "_counts": {"primary": len(primary), "r17": len(r17), "r17_extended": len(r17x),
                       "r30_absorbed": len(absorbed - primary), "r30_cited_pairs": cited_pairs,
                       "r30_wording_only": word_only}}
        (DER / "h1_exclusion_sets.json").write_text(json.dumps(out) + "\n")
    (ROOT / "data" / "manifests" / "h1_exclusion_counts.json").write_text(json.dumps(out["_counts"], indent=1))
    print(json.dumps(out["_counts"], indent=1))


if __name__ == "__main__":
    main()
