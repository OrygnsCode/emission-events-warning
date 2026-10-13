"""Plan D12: the news-sample completeness check, from the author's answers (data/manual/news_review_answers.json).

Steps, as written in D12 before the sample was drawn:
1. Links the author marked "yes" with a site: a suggested RMP facility is used as picked; a typed site ("name, city
   (address)") is matched to Texas RMP facilities by the linking rules: same city (letters only) and a shared
   non-generic name word, or the same street number and street word. One match: linked; none: treated as not RMP
   registered; several: listed for the author to settle (not decided here).
2. Incident date: the date the author typed, else the article date. Incidents before June 2003 are out of scope.
3. Distinct incidents: same site and incident dates within 7 days (the earliest date is kept).
4. For incidents at RMP facilities: an RMP accident at that facility within 7 days of the incident date, and the
   days between them.
Outputs: data/manifests/news_completeness.json (counts only), private/news_completeness_incidents.csv
(site names; internal).
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_plants_v2 import words  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
R = dict(dtype=str, keep_default_na=False)


def letters(s):
    return re.sub(r"[^A-Z]", "", str(s).upper())


def main():
    ans = json.loads((ROOT / "data/manual/news_review_answers.json").read_text())["answers"]
    links = pd.read_csv(ROOT / "data/manifests/news_sample_links.csv", parse_dates=["day"]).set_index("key")
    f = pd.read_csv(ROOT / "data/slices/rmp_raw/tblS1Facilities.csv.gz", usecols=[
        "EPAFacilityID", "FacilityName", "ParentCompanyName", "FacilityStr1", "FacilityCity", "ReceiptDate"], **R)
    f = f.sort_values("ReceiptDate")
    latest = f.groupby("EPAFacilityID").tail(1).set_index("EPAFacilityID")
    names = (f.FacilityName + " " + f.ParentCompanyName).map(words)
    dfreq = pd.Series([w for n in names for w in n]).value_counts()
    generic = set(dfreq[dfreq / f.EPAFacilityID.nunique() > 0.005].index) | {"PLANT", "TEXAS", "CHEMICAL"}
    f["nw"] = [n - generic for n in names]          # every filing's names (old names count too)
    f["city"] = f.FacilityCity.map(letters)
    f["num"] = f.FacilityStr1.str.extract(r"^\s*(\d+)")[0]
    f["stw"] = f.FacilityStr1.map(lambda s: words(re.sub(r"^\s*\d+", "", s)) - {"ROAD", "STREET", "HIGHWAY", "HWY",
                                                                                  "BLVD", "BOULEVARD", "AVE", "AVENUE"})
    settle = {}
    sp = ROOT / "data/manual/news_settle_answers.json"
    if sp.exists():
        st = json.loads(sp.read_text())
        typed_of = {i["key"]: i["typed"] for i in st["items"]}
        settle = {typed_of[k]: v for k, v in st["answers"].items()}
    rows = []
    for k, v in sorted(ans.items()):
        if v.get("q1") != "yes":
            continue
        site, how, typed = v.get("site"), "picked", ""
        if site == "other":
            typed = v.get("other", "")
            m = re.match(r"\s*([^,]+),\s*([^,(]+)", typed)
            nm, city = (m.group(1), m.group(2)) if m else (typed, "")
            cityl = letters(city.replace("near", "").replace("area", ""))
            nw = words(nm) - generic
            addr = re.search(r"\((\d+)\s+([^)]*)\)", typed)
            by_name = f[(f.city == cityl) & f.nw.map(lambda w: bool(w & nw))].EPAFacilityID.unique()
            by_addr = []
            if addr:
                aw = words(addr.group(2))
                by_addr = f[(f.num == addr.group(1)) & f.stw.map(lambda w: bool(w & aw))].EPAFacilityID.unique()
            hits = sorted(set(by_name) | set(by_addr))
            site, how = (hits[0], "rule match") if len(hits) == 1 else ((None, "no RMP match") if not hits else
                                                                         ("|".join(hits), "several: author to settle"))
            if typed in settle:   # the author's settling answer (D12) replaces the strict rule's outcome
                site, how = (None, "author: no RMP facility") if settle[typed] == "none" else (settle[typed], "author settled")
        elif site == "unknown":
            site, how = None, "site unknown"
        day = pd.Timestamp(v["date"]) if v.get("date") else links.at[k, "day"]
        rows.append({"key": k, "typed": typed, "site": site, "how": how, "incident_date": day})
    d = pd.DataFrame(rows)
    out = {"answers": len(ans), "yes": len(d), "no": sum(v.get("q1") == "no" for v in ans.values()),
           "cant_tell": sum(v.get("q1") == "unsure" for v in ans.values()),
           "yes_by_site_status": d.how.value_counts().to_dict()}
    d["in_scope"] = d.incident_date >= pd.Timestamp("2003-06-01")
    out["yes_before_june_2003"] = int((~d.in_scope).sum())
    # distinct incidents (sites known and single), dates within 7 days merged
    known = d[d.in_scope & d.how.isin(["picked", "rule match", "no RMP match", "author settled", "author: no RMP facility"])].copy()
    known["unit"] = np.where(known.site.notna(), known.site, "TYPED:" + known.typed.str.upper())
    inc = []
    for u, g in known.sort_values("incident_date").groupby("unit"):
        cur = None
        for r in g.itertuples():
            if cur is None or (r.incident_date - cur["incident_date"]).days > 7:
                cur = {"unit": u, "site": r.site, "typed": r.typed, "incident_date": r.incident_date, "articles": 0}
                inc.append(cur)
            cur["articles"] += 1
    inc = pd.DataFrame(inc)
    acc = pd.read_csv(ROOT / "data/slices/rmp_accidents_tx.csv.gz", usecols=["EPAFacilityID", "AccidentDate"], **R)
    acc["date"] = pd.to_datetime(acc.AccidentDate.str[:10])
    by_fac = acc.groupby("EPAFacilityID").date.apply(lambda s: s.values)
    gap = []
    for r in inc.itertuples():
        a = by_fac.get(r.site) if isinstance(r.site, str) else None
        gap.append(np.nan if a is None or not len(a) else
                   float(np.min(np.abs((a - np.datetime64(r.incident_date)) / np.timedelta64(1, "D")))))
    inc["nearest_rmp_accident_days"] = gap
    inc["rmp_facility"] = inc.site.notna()
    inc["name"] = [latest.FacilityName.get(s, "") if isinstance(s, str) else t for s, t in zip(inc.site, inc.typed)]
    rmp = inc[inc.rmp_facility]
    out["distinct_incidents"] = len(inc)
    out["incidents_at_rmp_facilities"] = len(rmp)
    out["of_which_rmp_accident_within_7_days"] = int((rmp.nearest_rmp_accident_days <= 7).sum())
    out["days_apart_when_found"] = rmp.loc[rmp.nearest_rmp_accident_days <= 7, "nearest_rmp_accident_days"].tolist()
    out["incidents_not_at_rmp_facilities"] = int((~inc.rmp_facility).sum())
    out["articles_per_incident_median"] = float(inc.articles.median())
    out["several_matches_to_settle"] = d.loc[d.how.str.startswith("several"), ["key", "typed", "site"]].to_dict("records")
    (ROOT / "data/manifests/news_completeness.json").write_text(json.dumps(
        {k: v for k, v in out.items() if k != "several_matches_to_settle"}, indent=1, default=str) + "\n")
    (ROOT / "private").mkdir(exist_ok=True)
    inc.sort_values("incident_date").to_csv(ROOT / "private/news_completeness_incidents.csv", index=False)
    print(json.dumps(out, indent=1, default=str))
    print(inc.sort_values("incident_date")[["incident_date", "name", "site", "articles", "nearest_rmp_accident_days"]].to_string())


if __name__ == "__main__":
    main()
