"""NOAA Storm Events zone records -> Texas counties (for robustness check R5).

Rule, in order: (1) the record's zone name is a Texas county name; (2) the name with leading COASTAL, INLAND,
NORTHERN, SOUTHERN, EASTERN, WESTERN, UPPER or LOWER and trailing COUNTY, ISLAND(S) removed, and the spellings
SAN PATRICO and DE WITT corrected, is a county name; (3) the official NWS zone-county correlation file
(bp18mr25.dbx, weather.gov): the counties of the zone with the same name; (4) the counties of the zone with the same
number; (5) five retired West Texas zones, mapped to the current NWS zones that replaced them:
VAN HORN & HWY 54 CORRIDOR -> Culberson (NWS "Van Horn and Highway 54 Corridor"); DAVIS / APACHE MOUNTAINS AREA ->
Brewster, Jeff Davis, Presidio (NWS "Davis Mountains"); BIG BEND AREA -> Brewster (its successors Central Brewster
County, Chisos Basin and Lower Brewster County are all in Brewster); REEVES COUNTY AND UPPER TRANS PECOS -> Reeves;
GUADALUPE MOUNTAINS OF CULBERSON COUNTY -> Culberson. Records left unmapped are counted.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIX = {"SAN PATRICO": "SAN PATRICIO", "DE WITT": "DEWITT"}
RETIRED = {"VAN HORN & HWY 54 CORRIDOR": ["CULBERSON"], "DAVIS / APACHE MOUNTAINS AREA": ["BREWSTER", "JEFF DAVIS", "PRESIDIO"],
           "BIG BEND AREA": ["BREWSTER"], "REEVES COUNTY AND UPPER TRANS PECOS": ["REEVES"],
           "GUADALUPE MOUNTAINS OF CULBERSON COUNTY": ["CULBERSON"]}


def tx_counties():
    cf = pd.read_csv(ROOT / "data/slices/rmp_raw/tlkpCountyFIPSCodes.csv.gz", dtype=str, keep_default_na=False)
    return set(cf[cf.State_Code == "TX"].County_Name.str.upper().str.strip())


def nws():
    z = pd.read_csv(ROOT / "data/external/nws_zones/bp18mr25.dbx.gz", sep="|", header=None, dtype=str,
                    names=["STATE", "ZONE", "CWA", "NAME", "STATE_ZONE", "COUNTY", "FIPS", "TZ", "FE", "LAT", "LON"])
    z = z[z.STATE == "TX"].copy()
    z["county"] = z.COUNTY.str.upper().str.strip()
    z["key"] = z.NAME.map(lambda t: re.sub(r"[^A-Z]", "", t.upper()))
    return z


def strip(name):
    n = name.upper().strip()
    n = re.sub(r"^(COASTAL|INLAND|NORTHERN|SOUTHERN|EASTERN|WESTERN|UPPER|LOWER)\s+", "", n)
    n = re.sub(r"\s+(COUNTY ISLANDS|COUNTY|ISLANDS|ISLAND)$", "", n)
    for a, b in FIX.items():
        n = n.replace(a, b)
    return n.strip()


def counties_of(name, number, TX, Z):
    n = name.upper().strip()
    if n in RETIRED:
        return RETIRED[n]
    for cand in (n, strip(n)):
        c = FIX.get(cand, cand)
        if c in TX:
            return [c]
    key = re.sub(r"[^A-Z]", "", n)
    hit = Z[Z.key == key]
    if len(hit):
        return sorted(set(hit.county) & TX)
    hit = Z[Z.ZONE.astype(int) == int(number)]
    return sorted(set(hit.county) & TX)


def storm_county_days(types):
    s = pd.read_csv(ROOT / "data/slices/noaa_storm_events_details_tx.csv.gz", low_memory=False)
    s = s[s.EVENT_TYPE.isin(types)].copy()
    TX, Z = tx_counties(), nws()
    s["counties"] = [counties_of(n, f, TX, Z) if t == "Z" else [n.upper().strip()]
                     for n, f, t in zip(s.CZ_NAME, s.CZ_FIPS, s.CZ_TYPE)]
    s["begin"] = pd.to_datetime(s.BEGIN_DATE_TIME, format="%d-%b-%y %H:%M:%S").dt.normalize()
    s["end"] = pd.to_datetime(s.END_DATE_TIME, format="%d-%b-%y %H:%M:%S").dt.normalize()
    log = {"records": len(s), "unmapped": int((s.counties.str.len() == 0).sum()),
           "unmapped_names": sorted(set(s.loc[s.counties.str.len() == 0, "CZ_NAME"]))}
    return s.explode("counties").dropna(subset=["counties"])[["counties", "begin", "end", "EVENT_TYPE"]], log


if __name__ == "__main__":
    d, log = storm_county_days(["Hurricane (Typhoon)", "Tropical Storm", "Winter Storm", "Ice Storm",
                                "Extreme Cold/Wind Chill"])
    print(log, "| county-event rows", len(d), "| date range", d.begin.min(), d.end.max())
    print(d.EVENT_TYPE.value_counts().to_dict())
