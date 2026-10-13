"""TCEQ site tables used by the plant linking (rules/linking_rules.json) and the warning-sign checks.

central_registry.parquet   the TCEQ Central Registry files (data/external/tceq_open_data/central_registry_*.csv.gz)
                           stacked, with the columns the linking uses renamed to short names and the source file kept
tceq_rn_points_raw.parquet every coordinate TCEQ publishes for a site (RN): the Point Source Emissions Inventory site
                           list (all years), emergency response spills, and complaints and enforcement notices where
                           the file has coordinate columns; points outside the Texas box are dropped

Outputs: data/derived/central_registry.parquet, data/derived/tceq_rn_points_raw.parquet
Usage:   python3 src/build_site_tables.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "data" / "external"
DER = ROOT / "data" / "derived"
R = dict(dtype=str, keep_default_na=False)
CR_COLUMNS = {
    "Regulated Entity Number (RE)": "rn", "RE Name": "re_name", "RE Physical Address": "addr",
    "RE Physical Address Cont.": "addr2", "City": "city", "County": "county", "ZIP Code": "zip",
    "RE Physical Location Description": "loc_desc", "RE NAICS Code": "naics", "Customer Name": "customer",
    "Customer Number": "cn", "Program": "program", "Additional ID (AI)": "ai", "AI Status": "ai_status",
    "Additional ID Status": "ai_status", "AI Physical Address": "ai_addr", "AI City": "ai_city",
    "AI ZIP Code": "ai_zip", "AI SIC Code": "ai_sic", "RE Status": "re_status", "Affiliation Begin Date": "aff_begin",
    "Affiliation Begin Date ": "aff_begin", "Affiliation End Date": "aff_end"}
OPEN_DATA_POINTS = [("complaints_tdzs-qqjn.csv", "complaints"), ("notices_of_violation_mwzi-gyw7.csv", "nov"),
                    ("notices_of_enforcement_rua3-iswk.csv", "noe")]


def central_registry():
    parts = []
    for f in sorted((EXT / "tceq_open_data").glob("central_registry_*.csv.gz")):
        d = pd.read_csv(f, **R)
        d = d[[c for c in d.columns if c in CR_COLUMNS]].rename(columns=CR_COLUMNS)
        d["file"] = str(f.relative_to(ROOT)).split("central_registry_")[1][:-7]
        parts.append(d)
    cr = pd.concat(parts, ignore_index=True)
    cr.to_parquet(DER / "central_registry.parquet", index=False)
    print("central registry rows", len(cr), "| distinct RNs", cr.rn.nunique())


def site_points():
    pts = []
    x = pd.ExcelFile(EXT / "tceq_psei" / "2010-2024-state-sum.xlsx")
    for sh in x.sheet_names[1:]:
        d = x.parse(sh, dtype=str)[["RN", "LATITUDE", "LONGITUDE"]]
        d.columns = ["rn", "lat", "lon"]
        d["src"] = "psei"
        pts.append(d)
    s = pd.read_csv(EXT / "tceq_open_data" / "emergency_response_spills_xagr-a3x2.csv.gz",
                    usecols=["Regulated Entity Number", "Latitude", "Longitude"], **R)
    s.columns = ["rn", "lat", "lon"]
    s["src"] = "spills"
    pts.append(s)
    for f, name in OPEN_DATA_POINTS:
        h = list(pd.read_csv(EXT / "tceq_open_data" / f, nrows=0).columns)
        if "Latitude" in h and "Longitude" in h and "Regulated Entity Number" in h:
            d = pd.read_csv(EXT / "tceq_open_data" / f, usecols=["Regulated Entity Number", "Latitude", "Longitude"],
                            **R)
            d.columns = ["rn", "lat", "lon"]
            d["src"] = name
            pts.append(d)
        else:
            print(name, "has no coordinate columns")
    p = pd.concat(pts, ignore_index=True)
    p["lat"] = pd.to_numeric(p.lat, errors="coerce")
    p["lon"] = pd.to_numeric(p.lon, errors="coerce")
    p = p[(p.lat.between(25.5, 36.6)) & (p.lon.between(-106.7, -93.4))].dropna()
    p.to_parquet(DER / "tceq_rn_points_raw.parquet", index=False)
    print("coordinate rows", len(p), "| RNs", p.rn.nunique())


if __name__ == "__main__":
    central_registry()
    site_points()
