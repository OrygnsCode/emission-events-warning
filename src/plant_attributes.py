"""Plant attributes for Phase 5 (county, TCEQ region, sector, location), each from a stated public source.

county   the most common county named on the plant's TCEQ event reports; for a plant with no event report, the
         county of its RMP filings (FacilityCountyFIPS of the latest filing, named by EPA's county lookup).
region   TCEQ region of that county, read from TCEQ's own complaint records, where every row carries both county and
         region (254 counties, 16 regions, no county with two regions).
sector   from the NAICS codes of the processes in each RMP facility's latest filing (a 5-digit code gets its dropped
         trailing zero back, as EPA's table stores 324110 as 32411): refining (324110), chemicals (325...),
         gas processing (211112 natural gas liquid extraction, or 211130 natural gas extraction), other. A plant takes the sector with the most
         processes; a tie goes to refining, then chemicals, then gas processing.
lat, lon the median of the plant's TCEQ site points (tceq_rn_points_raw); else the median RMP filing location.
Output: data/derived/plant_attributes.csv (plant_id and the fields above, plus agreement of the two county sources).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vchecks_common as vc  # noqa: E402

DER = vc.DER
SL = vc.ROOT / "data" / "slices" / "rmp_raw"
R = dict(dtype=str, keep_default_na=False)
PRIORITY = ["refining", "chemicals", "gas_processing", "other"]


def sector_of(naics):
    n = str(naics).strip()
    if len(n) == 5:
        n += "0"   # EPA's RMP table drops the trailing zero of many codes (32411 is 324110)
    if n == "324110":
        return "refining"
    if n.startswith("325"):
        return "chemicals"
    if n in ("211112", "211130"):
        return "gas_processing"
    return "other"


def main():
    pm = pd.read_csv(DER / "plant_members_v2.csv", **R)
    rn_plant = pm[pm.id_type == "RN"].set_index("id").plant_id
    rmp_plant = pm[pm.id_type == "RMP"].set_index("id").plant_id
    # TCEQ county per plant from event reports
    d = pd.read_parquet(DER / "details_table.parquet", columns=["incident", "rn", "county"])
    d["plant_id"] = d.rn.map(rn_plant)
    d["county"] = d.county.fillna("").str.upper().str.strip()
    ct = d[d.county.ne("") & d.plant_id.notna()].groupby("plant_id").county.agg(lambda s: s.value_counts().index[0])
    # RMP latest filing per facility
    f = pd.read_csv(SL / "tblS1Facilities.csv.gz", usecols=["FacilityID", "EPAFacilityID", "FacilityCountyFIPS",
                                                            "FacilityLatDecDegs", "FacilityLongDecDegs", "ReceiptDate"], **R)
    f = f.sort_values("ReceiptDate").groupby("EPAFacilityID").tail(1)
    f["plant_id"] = f.EPAFacilityID.map(rmp_plant)
    cf = pd.read_csv(SL / "tlkpCountyFIPSCodes.csv.gz", **R)
    fips = dict(zip(cf.StateCounty_Code, cf.County_Name.str.upper().str.strip()))
    f["county_rmp"] = f.FacilityCountyFIPS.map(fips)
    cr = f.dropna(subset=["plant_id"]).groupby("plant_id").county_rmp.agg(
        lambda s: s.dropna().value_counts().index[0] if s.notna().any() else None)
    # sector
    pr = pd.read_csv(SL / "tblS1Processes.csv.gz", usecols=["ProcessID", "FacilityID"], **R)
    pn = pd.read_csv(SL / "tblS1Process_NAICS.csv.gz", usecols=["ProcessID", "NAICSCode"], **R)
    x = pn.merge(pr, on="ProcessID").merge(f[["FacilityID", "plant_id"]], on="FacilityID")
    x["sector"] = x.NAICSCode.map(sector_of)
    sec = x.groupby("plant_id").sector.agg(
        lambda s: sorted(s.value_counts().items(), key=lambda kv: (-kv[1], PRIORITY.index(kv[0])))[0][0])
    # region from TCEQ complaint records
    c = pd.read_csv(vc.ROOT / "data/external/tceq_open_data/complaints_tdzs-qqjn.csv", usecols=["County", "TCEQ Region"],
                    low_memory=False).dropna()
    reg = c.assign(County=c.County.str.upper().str.strip()).groupby("County")["TCEQ Region"].agg(
        lambda s: s.value_counts().index[0])
    # location
    pts = vc.rn_points()
    loc = pts.join(rn_plant.rename("plant_id"), how="inner").groupby("plant_id")[["lat", "lon"]].median()
    f["lat_r"] = pd.to_numeric(f.FacilityLatDecDegs, errors="coerce")
    f["lon_r"] = pd.to_numeric(f.FacilityLongDecDegs, errors="coerce")
    locr = f.dropna(subset=["plant_id"]).groupby("plant_id")[["lat_r", "lon_r"]].median()
    plants = pd.read_csv(DER / "plants_v2.csv")
    out = plants[["plant_id", "linked"]].set_index("plant_id")
    out["county_tceq"] = ct
    out["county_rmp"] = cr
    out["county"] = out.county_tceq.fillna(out.county_rmp)
    out["region"] = out.county.map(reg)
    out["sector"] = sec
    out["lat"] = loc.lat.reindex(out.index).fillna(locr.lat_r.reindex(out.index))
    out["lon"] = loc.lon.reindex(out.index).fillna(locr.lon_r.reindex(out.index))
    out.reset_index().to_csv(DER / "plant_attributes.csv", index=False)
    L = out[out.linked]
    both = L.dropna(subset=["county_tceq", "county_rmp"])
    print({"plants": len(out), "linked": len(L), "linked_with_county": int(L.county.notna().sum()),
           "linked_with_region": int(L.region.notna().sum()), "linked_with_location": int(L.lat.notna().sum()),
           "linked_with_sector": int(L.sector.notna().sum()),
           "county_sources_agree_share": round(float((both.county_tceq == both.county_rmp).mean()), 3),
           "sectors_linked": L.sector.value_counts().to_dict()})


if __name__ == "__main__":
    main()
