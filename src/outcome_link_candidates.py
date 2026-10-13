"""Candidate links for the independent outcomes, for the author's hand review (plan 6.4 for O5/H4, D2 item 7 for O6).

O5 (National Response Center, H4): serious reports (fire, injury, fatality or evacuation) at fixed facilities in
Texas (NRC incident type FIXED), June 2003 to 2023. Candidates per plan 6.4: TCEQ sites with emission event reports
in the same county whose names share a word with the report's company or location text; a street number match is
shown where both records have one.
O6 (OSHA, H1 outcome for linked RMP plants): OSHA fatality and catastrophe investigations (accident records with
their inspection's establishment and site address), and OSHA severe injury reports (2015 on). Candidates per D2 item
3: same street address key (house number, street, ZIP) as a TCEQ site of the plant; or within 1 km of the plant
(severe injury reports carry coordinates) with a shared name word; or the same ZIP with a shared name word.
Name words: upper case words of 3 or more letters, not digits, not among the generic words of the linking code
(words in more than 0.5% of TCEQ site names) and not the record's own city or county words. Candidates are
generated broadly on purpose: no link is used unless the author marks it "same site".
The reviewer sees identifying fields only (names, addresses, county, ZIP, date, distance), never emission events
or accidents. Output: data/derived/outcome_link_items.json
"""
import collections
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_plants_v2 import addr_key, words  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DER = ROOT / "data" / "derived"
SL = ROOT / "data" / "slices"
R = dict(dtype=str, keep_default_na=False)
START, END = pd.Timestamp("2003-06-01"), pd.Timestamp("2023-12-31")


def rn_side():
    ev = pd.read_csv(DER / "events_v2.csv.gz", usecols=["rn", "plant_id"]).dropna()
    ev_rns = set(ev.rn)
    cr = pd.read_parquet(DER / "central_registry.parquet", columns=["rn", "re_name", "customer", "addr", "city", "county", "zip"])
    cr = cr[cr.rn.isin(ev_rns)].drop_duplicates(["rn", "re_name", "customer", "addr", "zip", "county"])
    def name_strings(d):
        # every distinct site name and customer name of an RN, joined (same strings as the linking code compares)
        long = pd.concat([d[["rn", "re_name"]].rename(columns={"re_name": "n"}),
                          d[["rn", "customer"]].rename(columns={"customer": "n"})]).drop_duplicates()
        return long.sort_values(["rn", "n"]).groupby("rn").n.agg(" | ".join)

    names = name_strings(cr)
    allcr = pd.read_parquet(DER / "central_registry.parquet", columns=["rn", "re_name", "customer"])
    allnames = name_strings(allcr)
    df = collections.Counter(w for n in allnames.values for w in words(n))
    generic = {w for w, c in df.items() if c / len(allnames) > 0.005}
    info = {}
    for rn, g in cr.groupby("rn"):
        place = set()
        for c1, c2 in zip(g.city, g.county):
            place |= words(c1) | words(c2)
        info[rn] = {"names": names[rn], "words": words(names[rn]) - generic - place,
                    "county": {x.strip().upper() for x in g.county if x.strip()},
                    "addr_keys": {k for k in (addr_key(a, z) for a, z in zip(g.addr, g.zip)) if k},
                    "zips": {re.sub(r"\D", "", z)[:5] for z in g.zip if len(re.sub(r"\D", "", z)) >= 5},
                    "addresses": sorted({f"{a}, {c} {z}".strip(", ") for a, c, z in zip(g.addr, g.city, g.zip) if a})[:3]}
    plant_of = dict(zip(ev.rn, ev.plant_id))
    return info, generic, plant_of


def nrc_items(info, generic):
    calls = pd.read_csv(SL / "nrc_calls_tx.csv.gz", usecols=["SEQNOS", "RESPONSIBLE_COMPANY", "RESPONSIBLE_CITY"], **R)
    com = pd.read_csv(SL / "nrc_incident_commons_tx.csv.gz",
                      usecols=["SEQNOS", "TYPE_OF_INCIDENT", "INCIDENT_DATE_TIME", "INCIDENT_LOCATION", "LOCATION_ADDRESS",
                               "LOCATION_STREET1", "LOCATION_NEAREST_CITY", "LOCATION_COUNTY", "LOCATION_ZIP",
                               "LOCATION_STATE"], **R)
    det = pd.read_csv(SL / "nrc_incident_details_tx.csv.gz",
                      usecols=["SEQNOS", "FIRE_INVOLVED", "ANY_INJURIES", "ANY_FATALITIES", "ANY_EVACUATIONS"], **R)
    x = com.merge(det, on="SEQNOS", how="left").merge(calls.drop_duplicates("SEQNOS"), on="SEQNOS", how="left")
    x["date"] = pd.to_datetime(x.INCIDENT_DATE_TIME.str[:10], errors="coerce", format="mixed")
    serious = x[["FIRE_INVOLVED", "ANY_INJURIES", "ANY_FATALITIES", "ANY_EVACUATIONS"]].apply(
        lambda s: s.str.upper().eq("Y")).any(axis=1)
    x = x[x.TYPE_OF_INCIDENT.str.upper().eq("FIXED") & x.LOCATION_STATE.isin(["TX", ""]) & serious
          & x.date.between(START, END)].drop_duplicates("SEQNOS")
    by_county = collections.defaultdict(list)
    for rn, v in info.items():
        for c in v["county"]:
            by_county[c].append(rn)
    items = []
    for r in x.itertuples():
        county = r.LOCATION_COUNTY.strip().upper()
        text = f"{r.RESPONSIBLE_COMPANY} | {r.INCIDENT_LOCATION}"
        w = words(text) - generic - words(r.LOCATION_NEAREST_CITY) - words(county) - words(r.RESPONSIBLE_CITY)
        street = (r.LOCATION_ADDRESS or r.LOCATION_STREET1)
        num = re.match(r"\s*(\d+)\s", street + " ")
        cands = []
        for rn in by_county.get(county, []):
            shared = w & info[rn]["words"]
            if not shared:
                continue
            nm = bool(num) and any(k[0] == num.group(1) for k in info[rn]["addr_keys"])
            cands.append({"id": rn, "names": info[rn]["names"][:300], "addresses": info[rn]["addresses"],
                          "shared_words": sorted(shared), "street_number_match": nm})
        cands.sort(key=lambda c: (not c["street_number_match"], -len(c["shared_words"])))
        items.append({"key": f"NRC-{r.SEQNOS}", "source": "NRC", "date": str(r.date.date()), "county": county,
                      "name": r.RESPONSIBLE_COMPANY, "location": r.INCIDENT_LOCATION[:200],
                      "address": f"{street}, {r.LOCATION_NEAREST_CITY} {r.LOCATION_ZIP}".strip(", "),
                      "candidates": cands})
    return items


def osha_items(info, generic, plant_of):
    plants = pd.read_csv(DER / "plants_v2.csv")
    linked = set(plants.loc[plants.linked, "plant_id"])
    attrs = pd.read_csv(DER / "plant_attributes.csv").set_index("plant_id")
    plant_rns = collections.defaultdict(list)
    for rn, p in plant_of.items():
        if p in linked and rn in info:
            plant_rns[p].append(rn)
    addr_index, zip_index = collections.defaultdict(set), collections.defaultdict(set)
    for p, rns in plant_rns.items():
        for rn in rns:
            for k in info[rn]["addr_keys"]:
                addr_index[k].add(p)
            for z in info[rn]["zips"]:
                zip_index[z].add(p)
    pw = {p: set().union(*(info[rn]["words"] for rn in rns)) for p, rns in plant_rns.items()}

    def cands_for(name, address, city, zp, lat=None, lon=None):
        w = words(name) - generic - words(city)
        k = addr_key(address, zp)
        z = re.sub(r"\D", "", str(zp))[:5]
        out = {}
        if k:
            for p in addr_index.get(k, ()):
                out.setdefault(p, set()).add("same street address")
        for p in zip_index.get(z, ()):
            if w & pw[p]:
                out.setdefault(p, set()).add("same ZIP and shared name word")
        if lat is not None and lat == lat:
            for p in linked:
                if p in attrs.index and attrs.at[p, "lat"] == attrs.at[p, "lat"]:
                    d = np.hypot((lat - attrs.at[p, "lat"]) * 111, (lon - attrs.at[p, "lon"]) * 111 * np.cos(np.radians(lat)))
                    if d <= 1.0 and (w & pw.get(p, set())):
                        out.setdefault(p, set()).add(f"within 1 km ({d:.2f} km) and shared name word")
        return [{"id": p, "names": " / ".join(info[rn]["names"][:150] for rn in plant_rns[p][:3]),
                 "addresses": sorted({a for rn in plant_rns[p] for a in info[rn]["addresses"]})[:3],
                 "shared_words": sorted(w & pw.get(p, set())), "why": sorted(v)} for p, v in out.items()]

    items = []
    # fatality and catastrophe investigations
    acc = pd.read_csv(SL / "osha/accident_tx.csv.gz", usecols=["SUMMARY_NR", "EVENT_DATE", "FATALITY"], **R)
    inj = pd.read_csv(SL / "osha/accident_injury_tx.csv.gz", usecols=["SUMMARY_NR", "REL_INSP_NR"], **R).drop_duplicates()
    ins = pd.read_csv(SL / "osha/inspection_tx.csv.gz", usecols=["ACTIVITY_NR", "ESTAB_NAME", "SITE_ADDRESS", "SITE_CITY",
                                                                "SITE_ZIP", "SITE_STATE"], **R)
    a = acc.merge(inj, on="SUMMARY_NR").merge(ins, left_on="REL_INSP_NR", right_on="ACTIVITY_NR")
    a["date"] = pd.to_datetime(a.EVENT_DATE.str[:10], errors="coerce")
    a = a[a.SITE_STATE.eq("TX") & a.date.between(START, END)].drop_duplicates(["SUMMARY_NR", "ACTIVITY_NR"])
    for r in a.itertuples():
        c = cands_for(r.ESTAB_NAME, r.SITE_ADDRESS, r.SITE_CITY, r.SITE_ZIP)
        if c:
            items.append({"key": f"OSHA-ACC-{r.SUMMARY_NR}-{r.ACTIVITY_NR}", "source": "OSHA fatality/catastrophe",
                          "date": str(r.date.date()), "name": r.ESTAB_NAME,
                          "address": f"{r.SITE_ADDRESS}, {r.SITE_CITY} {r.SITE_ZIP}", "candidates": c})
    # severe injury reports
    z = zipfile.ZipFile(next((ROOT / "data/external/osha/severe_injury").glob("*.zip")))
    member = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    s = pd.read_csv(io.BytesIO(z.read(member)), dtype=str, keep_default_na=False, encoding="latin-1")
    s.columns = [c.strip() for c in s.columns]
    col = {c.lower(): c for c in s.columns}
    s = s[s[col["state"]].str.upper().isin(["TX", "TEXAS"])]
    s["date"] = pd.to_datetime(s[col["eventdate"]], errors="coerce")
    s = s[s.date.between(START, END)]
    for r in s.itertuples(index=False):
        rr = r._asdict()
        g = lambda k: str(rr.get(col.get(k, k), "") or "")  # noqa: E731
        lat = pd.to_numeric(g("latitude"), errors="coerce")
        lon = pd.to_numeric(g("longitude"), errors="coerce")
        c = cands_for(g("employer"), g("address1"), g("city"), g("zip"), lat, lon)
        if c:
            items.append({"key": f"OSHA-SIR-{g('id')}", "source": "OSHA severe injury", "date": str(rr["date"].date()),
                          "name": g("employer"), "address": f"{g('address1')}, {g('city')} {g('zip')}", "candidates": c})
    return items, {"fatality_catastrophe_records": len(a), "severe_injury_records": len(s), "severe_injury_columns": list(s.columns)[:30]}


def main():
    info, generic, plant_of = rn_side()
    nrc = nrc_items(info, generic)
    osha, olog = osha_items(info, generic, plant_of)
    out = {"nrc": nrc, "osha": osha,
           "summary": {"nrc_serious_reports": len(nrc), "nrc_with_candidates": sum(1 for i in nrc if i["candidates"]),
                       "nrc_candidate_pairs": sum(len(i["candidates"]) for i in nrc),
                       "osha_records_with_candidates": len(osha), "osha_candidate_pairs": sum(len(i["candidates"]) for i in osha),
                       **olog}}
    (DER / "outcome_link_items.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out["summary"], indent=1, default=str))


if __name__ == "__main__":
    main()
