"""O7 (descriptive) and the completeness check of D2 item 7: CSB investigations in Texas and the RMP accidents that may
be the same event, for the author's hand review.

Each CSB investigation page states "Location: City, ST" and "Accident Occurred On: MM/DD/YYYY". Texas investigations
with an accident from June 2003 to 2023 are listed. Candidates: RMP accidents (any facility, linked or not) whose
facility city (latest RMP filing) is the CSB city and whose date is within 7 days of the CSB date, or whose facility or
parent company name shares a word with the CSB title (words as in the linking code, generic words and place words
left out) and whose date is within 30 days. A CSB event with
no candidate is reported as possibly missing from RMP after the review. Output: data/derived/csb_items.json
(merged into the review page as a third tab).
"""
import gzip
import html
import json
import re
from pathlib import Path

import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_plants_v2 import words  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SL = ROOT / "data" / "slices"
R = dict(dtype=str, keep_default_na=False)


def parse(path):
    t = gzip.open(path, "rt", errors="replace").read()
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    title = re.search(r"<title>(.*?)</title>", t, flags=re.S)
    s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))
    loc = re.search(r"Location:\s*(?:Location:\s*)?([^|]*?),\s*([A-Z]{2})\b", s)
    date = re.search(r"Accident Occurred On:\s*(\d{1,2}/\d{1,2}/\d{4})", s)
    return {"page": path.name, "title": html.unescape(title.group(1)).split("|")[0].strip() if title else path.name,
            "city": loc.group(1).strip().upper() if loc else None, "state": loc.group(2) if loc else None,
            "date": pd.to_datetime(date.group(1), format="%m/%d/%Y") if date else None}


def main():
    pages = [parse(p) for p in sorted((ROOT / "data/external/csb/pages").glob("*.html.gz"))]
    d = pd.DataFrame(pages)
    log = {"pages": len(d), "with_location": int(d.state.notna().sum()), "with_date": int(d.date.notna().sum())}
    tx = d[d.state.eq("TX") & d.date.between("2003-06-01", "2023-12-31")]
    log["texas_2003_2023"] = len(tx)
    acc = pd.read_csv(SL / "rmp_accidents_tx.csv.gz", usecols=["AccidentHistoryID", "EPAFacilityID", "AccidentDate"], **R)
    acc["date"] = pd.to_datetime(acc.AccidentDate.str[:10])
    f = pd.read_csv(SL / "rmp_raw/tblS1Facilities.csv.gz", usecols=["EPAFacilityID", "FacilityName", "FacilityCity",
                                                                   "FacilityStr1", "ParentCompanyName", "ReceiptDate"], **R)
    f = f.sort_values("ReceiptDate").groupby("EPAFacilityID").tail(1)
    acc = acc.merge(f, on="EPAFacilityID", how="left")
    acc["city"] = acc.FacilityCity.str.upper().str.replace(r"[^A-Z]", "", regex=True)   # LA PORTE = LAPORTE
    items = []
    import collections
    allnames = f.FacilityName + " " + f.ParentCompanyName
    dfreq = collections.Counter(w for n in allnames for w in words(n))
    generic = {w for w, c in dfreq.items() if c / len(allnames) > 0.005} | {"INVESTIGATION", "EXPLOSION", "FIRE",
                                                                             "RELEASE", "FATAL", "CHEMICAL", "TANK"}
    acc["w"] = (acc.FacilityName + " " + acc.ParentCompanyName).map(words)
    for r in tx.itertuples():
        tw = words(r.title) - generic - words(r.city)
        near = (acc.date - r.date).abs()
        city = re.sub(r"[^A-Z]", "", r.city)
        c = acc[(acc.city.eq(city) & (near <= pd.Timedelta(days=7)))
                | ((near <= pd.Timedelta(days=30)) & acc.w.map(lambda w: bool(w & tw)))]
        items.append({"key": f"CSB-{r.page}", "source": "CSB investigation", "date": str(r.date.date()),
                      "name": r.title, "address": f"{r.city}, TX",
                      "candidates": [{"id": a.AccidentHistoryID, "names": f"{a.FacilityName} (RMP accident dated {a.date.date()})",
                                      "addresses": [f"{a.FacilityStr1}, {a.FacilityCity}"],
                                      "why": [f"{'same city' if a.city == city else 'shared name word'}, "
                                              f"{abs((a.date - r.date).days)} days apart"]}
                                     for a in c.itertuples()]})
    log["with_a_candidate"] = sum(1 for i in items if i["candidates"])
    (ROOT / "data/derived/csb_items.json").write_text(json.dumps({"csb": items, "log": log}, indent=1) + "\n")
    print(log)
    for i in items:
        print(i["date"], i["address"], "|", i["name"][:70], "| candidates:", len(i["candidates"]))


if __name__ == "__main__":
    main()
