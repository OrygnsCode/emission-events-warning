"""Point Source Emissions Inventory census for check V5 (data dossier, no accident data).

Reads the yearly TCEQ PSEI workbooks (data/external/tceq_psei/<year>.xlsx, 2016 to 2024) row by row and keeps, per
site (RN), year and contaminant: annual routine TPY, emissions event (EE) TPY and MSS TPY, plus the site's SIC,
county and coordinates. The two older snapshots (2016ei_data.xlsx, 2022ei_data.xlsx) are compared with the newer
files for the same year to show how much the inventory changes between pulls.

This file only describes the inventory. It does not compare it with the event database; that comparison is V5 and
runs only after its definition is written into the plan.

Outputs: data/derived/psei_site_year_contaminant.parquet, data/derived/psei_census.json
Usage: python3 src/census_psei.py
"""
import json
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "external" / "tceq_psei"
DER = ROOT / "data" / "derived"
COLS = ["RN", "COMPANY", "SITE", "COUNTY", "Standard Industry Classification (SIC)", "LATITUDE", "LONGITUDE", "YEAR",
        "CONTAMINANT CODE", "CONTAMINANT NAME", "ANNUAL ROUTINE TPY", "EE TPY", "MSS TPY", "HAP", "VOC", "NOx"]


def read(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    # the data sheet is the one whose first cell is "RN" (the notes sheet is called READ ME in most years, Sheet1 in 2018)
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        hdr = [str(c).strip() if c is not None else "" for c in next(it)]
        if hdr and hdr[0] == "RN":
            break
    idx = [hdr.index(c) for c in COLS]
    rows = [[r[i] for i in idx] for r in it if r and r[0]]
    d = pd.DataFrame(rows, columns=COLS)
    for c in ["ANNUAL ROUTINE TPY", "EE TPY", "MSS TPY", "LATITUDE", "LONGITUDE"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def agg(d):
    return d.groupby(["RN", "YEAR", "CONTAMINANT CODE", "CONTAMINANT NAME"], as_index=False).agg(
        site=("SITE", "first"), company=("COMPANY", "first"), county=("COUNTY", "first"),
        sic=("Standard Industry Classification (SIC)", "first"), lat=("LATITUDE", "median"), lon=("LONGITUDE", "median"),
        routine_tpy=("ANNUAL ROUTINE TPY", "sum"), ee_tpy=("EE TPY", "sum"), mss_tpy=("MSS TPY", "sum"),
        hap=("HAP", "first"), voc=("VOC", "first"), nox=("NOx", "first"), rows=("RN", "size"))


def main():
    parts, out = [], {"years": {}}
    cache = DER / "psei_cache"
    cache.mkdir(exist_ok=True)
    for y in range(2016, 2025):
        if (cache / f"{y}.parquet").exists():
            a = pd.read_parquet(cache / f"{y}.parquet")
            d = pd.read_parquet(cache / f"{y}_meta.parquet")
        else:
            d = read(SRC / f"{y}.xlsx")
            a = agg(d)
            a.to_parquet(cache / f"{y}.parquet", index=False)
            d = d[["YEAR"]].assign(n=1)
            d.to_parquet(cache / f"{y}_meta.parquet", index=False)
        parts.append(a)
        site = a.groupby("RN")[["routine_tpy", "ee_tpy", "mss_tpy"]].sum()
        out["years"][y] = {"rows": len(d), "sites": int(site.shape[0]), "sites_with_ee": int((site.ee_tpy > 0).sum()),
                           "ee_tpy_total": round(float(site.ee_tpy.sum()), 1),
                           "routine_tpy_total": round(float(site.routine_tpy.sum()), 1),
                           "year_values_in_file": sorted(map(int, d.YEAR.dropna().unique()))}
        print(y, out["years"][y], flush=True)
    allp = pd.concat(parts)
    allp.to_parquet(DER / "psei_site_year_contaminant.parquet", index=False)
    for y in (2016, 2022):
        old = agg(read(SRC / f"{y}ei_data.xlsx")).groupby("RN")[["routine_tpy", "ee_tpy"]].sum()
        new = allp[allp.YEAR == y].groupby("RN")[["routine_tpy", "ee_tpy"]].sum()
        j = old.join(new, lsuffix="_old", rsuffix="_new", how="outer").fillna(0)
        out[f"snapshot_change_{y}"] = {
            "sites_old": int((j.routine_tpy_old + j.ee_tpy_old > 0).sum()), "sites_new": int((j.routine_tpy_new + j.ee_tpy_new > 0).sum()),
            "sites_ee_changed_over_1pct": int(((j.ee_tpy_new - j.ee_tpy_old).abs() > 0.01 * j[["ee_tpy_old", "ee_tpy_new"]].max(axis=1)).sum()),
            "ee_tpy_old": round(float(j.ee_tpy_old.sum()), 1), "ee_tpy_new": round(float(j.ee_tpy_new.sum()), 1)}
    rs = set(pd.read_csv(DER / "plant_members_v2.csv").query("id_type == 'RN'").id)
    risk = set(pd.read_csv(DER / "plant_risk_v2.csv").plant_id)
    pm = pd.read_csv(DER / "plant_members_v2.csv")
    risk_rns = set(pm[(pm.id_type == "RN") & pm.plant_id.isin(risk)].id)
    s = allp.groupby(["RN", "YEAR"])[["ee_tpy"]].sum().reset_index()
    out["site_years"] = len(s)
    out["site_years_in_plant_table"] = int(s.RN.isin(rs).sum())
    out["site_years_at_rmp_plants"] = int(s.RN.isin(risk_rns).sum())
    out["site_years_at_rmp_plants_with_ee"] = int((s.RN.isin(risk_rns) & (s.ee_tpy > 0)).sum())
    (DER / "psei_census.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
