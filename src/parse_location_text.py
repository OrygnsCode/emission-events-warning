"""Read coordinates that are written into TCEQ Central Registry location descriptions (linking rules v1.3).

Mechanical pattern matching only. Accepted forms:
  decimal pairs   "32.423083, -101.411908", "LAT 29.852563 LONG -95.088702", "29.42406 N, -98.3905 W"
                  (each number with at least 3 decimals, about 110 m or better)
  degrees-minutes-seconds after the words LAT/LATITUDE and LONG/LONGITUDE
                  ("LAT 31 27' 41.7\" LONG 102 20' 56.2\"", "LATITUDE 31 DEGREES, 24 MINUTES, AND 24 SECONDS ...")
A point is kept only if it falls inside Texas (latitude 25.5 to 36.6, longitude -106.7 to -93.4). Longitudes written
without a minus sign are taken as west, since every Texas longitude is west. Driving directions and other text that
would need a person to interpret are ignored.

Check: for RNs that already have coordinates from other sources, the distance from each parsed point to the
nearest known point is reported (data/derived/location_text_check.json).

Output: data/derived/tceq_rn_points_desc.parquet (rn, lat, lon, src = cr_location_text)
Usage: python3 src/parse_location_text.py
"""
import json
import math
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DER = ROOT / "data" / "derived"
LAT_RANGE, LON_RANGE = (25.5, 36.6), (93.4, 106.7)

DEC_PAIR = re.compile(r"(\d{2}\.\d{3,})\s*(?:°)?\s*N?\s*[,;/ ]\s*(?:LONG(?:ITUDE)?\s*[:=]?\s*)?(-?\s*\d{2,3}\.\d{3,})\s*(W?)")
LABELED = re.compile(r"LAT(?:ITUDE)?\W{0,4}(\d{2}\.\d{3,}).{0,30}?LONG(?:ITUDE)?\W{0,4}(-?\d{2,3}\.\d{3,})", re.S)
DMS = re.compile(r"LAT(?:ITUDE)?\D{0,12}?(\d{2})\D{1,20}?(\d{1,2})\D{1,20}?(\d{1,2}(?:\.\d+)?)"
                 r".{0,40}?LONG(?:ITUDE)?\D{0,12}?(\d{2,3})\D{1,20}?(\d{1,2})\D{1,20}?(\d{1,2}(?:\.\d+)?)", re.S)


def in_tx(lat, lon):
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and -LON_RANGE[1] <= lon <= -LON_RANGE[0]


def parse(text):
    t = str(text).upper()
    pts = []
    for m in DEC_PAIR.finditer(t):
        lat, lon = float(m.group(1)), float(m.group(2).replace(" ", ""))
        lon = -abs(lon)
        if in_tx(lat, lon):
            pts.append((round(lat, 6), round(lon, 6)))
    for m in LABELED.finditer(t):
        lat, lon = float(m.group(1)), -abs(float(m.group(2)))
        if in_tx(lat, lon):
            pts.append((round(lat, 6), round(lon, 6)))
    for m in DMS.finditer(t):
        d1, m1, s1, d2, m2, s2 = (float(x) for x in m.groups())
        if m1 < 60 and s1 < 60 and m2 < 60 and s2 < 60:
            lat, lon = d1 + m1 / 60 + s1 / 3600, -(d2 + m2 / 60 + s2 / 3600)
            if in_tx(lat, lon):
                pts.append((round(lat, 6), round(lon, 6)))
    return sorted(set(pts))


def km(a, b, c, d):
    x = math.radians(d - b) * math.cos(math.radians((a + c) / 2))
    return 6371.0 * math.hypot(x, math.radians(c - a))


def main():
    cr = pd.read_parquet(DER / "central_registry.parquet", columns=["rn", "loc_desc"]).dropna().drop_duplicates()
    rows = [(rn, la, lo) for rn, t in zip(cr.rn, cr.loc_desc) for la, lo in parse(t)]
    out = pd.DataFrame(rows, columns=["rn", "lat", "lon"]).drop_duplicates()
    out["src"] = "cr_location_text"
    out.to_parquet(DER / "tceq_rn_points_desc.parquet", index=False)

    # check against coordinates already known from other sources (emissions inventory, spills, notices, EPA registry)
    known = pd.read_parquet(DER / "tceq_rn_points_raw.parquet")
    known = known[known.lat.between(*LAT_RANGE) & known.lon.between(-LON_RANGE[1], -LON_RANGE[0])]
    kp = known.groupby("rn")[["lat", "lon"]].apply(lambda g: list(zip(g.lat, g.lon))).to_dict()
    d = [min(km(la, lo, a, b) for a, b in kp[rn]) for rn, la, lo in zip(out.rn, out.lat, out.lon) if rn in kp]
    s = pd.Series(d)
    check = {"rns_with_parsed_points": int(out.rn.nunique()), "parsed_points": len(out),
             "points_with_known_coordinates_to_compare": len(s),
             "median_km_to_nearest_known_point": round(float(s.median()), 3) if len(s) else None,
             "share_within_0_25_km": round(float((s <= 0.25).mean()), 3) if len(s) else None,
             "share_within_1_km": round(float((s <= 1).mean()), 3) if len(s) else None,
             "share_beyond_5_km": round(float((s > 5).mean()), 3) if len(s) else None}
    (DER / "location_text_check.json").write_text(json.dumps(check, indent=1) + "\n")
    print(json.dumps(check, indent=1))


if __name__ == "__main__":
    main()
