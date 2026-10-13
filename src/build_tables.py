"""Build the event table, the accident table and plant risk periods (plan 3.2 to 3.4).

This script only prepares tables. It does not relate events to accidents.

Outputs (data/derived/):
  events.csv.gz    one row per TCEQ incident, with plant, dates, type, duplicate flags
  accidents.csv    one row per de-duplicated Texas RMP accident, with plant and O1 to O4
  plant_risk.csv   time at risk per plant (from RMP registration and de-registration)

With the argument v2 (plan D2 and D3), plants come from plant_members_v2.csv (the extended, hand-reviewed links),
the duplicate-accident merges in accident_merges.json are applied, and the outputs carry the suffix _v2.
The R19 version (no merges) is the same table before the merges, kept in the column merged_into.

Usage: python3 src/build_tables.py [v2]
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SL = ROOT / "data" / "slices"
DER = ROOT / "data" / "derived"
READ = dict(dtype=str, keep_default_na=False)
TCEQ_START = pd.Timestamp("2003-02-01")
V2 = len(sys.argv) > 1 and sys.argv[1] == "v2"
SUF = "_v2" if V2 else ""

HARM_PEOPLE = ["DeathsWorkers", "DeathsPublicResponders", "DeathsPublic", "InjuriesWorkers",
               "InjuriesPublicResponders", "InjuriesPublic", "OffsiteDeaths"]
OFFSITE_NUM = ["OffsiteDeaths", "Hospitalization", "MedicalTreatment", "Evacuated", "ShelteredInPlace",
               "OffsitePropertyDamage"]
OFFSITE_FLAG = ["ED_Kills", "ED_MinorDefoliation", "ED_WaterContamination", "ED_SoilContamination"]


def num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)


def members(kind):
    pm = pd.read_csv(DER / f"plant_members{SUF}.csv", **READ)
    return pm[pm.id_type == kind].set_index("id")["plant_id"]


def build_events():
    m = pd.read_csv(ROOT / "data/master/incidents.csv.gz", **READ)
    fmt = "%m/%d/%Y %I:%M %p"
    start = pd.to_datetime(m["START DATE/TIME"].where(m["START DATE/TIME"] != "UNKNOWN"), format=fmt, errors="coerce")
    end = pd.to_datetime(m["END DATE/TIME"].where(m["END DATE/TIME"] != "UNKNOWN"), format=fmt, errors="coerce")
    ev = pd.DataFrame({
        "incident": m["INCIDENT NO."].astype(int),
        "rn": m["RN"],
        "event_type": m["EVENT TYPE"],
        "event_datetime": start.fillna(end),
        "date_source": start.notna().map({True: "start", False: "end"}),
        "report_date": pd.to_datetime(m["REPORT DATE"], format="%m/%d/%Y", errors="coerce"),
        "start_raw": m["START DATE/TIME"],
    })
    ev.loc[ev.event_datetime.isna(), "date_source"] = "none"
    ev["plant_id"] = ev["rn"].map(members("RN"))

    # duplicates: same RN, same start time, same event type -> keep the lowest incident number
    ev = ev.sort_values("incident")
    key = ["rn", "start_raw", "event_type"]
    has_start = ev["start_raw"] != "UNKNOWN"
    first = ev[has_start].groupby(key)["incident"].transform("min")
    ev["dup_of"] = pd.NA
    ev.loc[has_start, "dup_of"] = first.where(first != ev.loc[has_start, "incident"])
    ev["is_duplicate"] = ev["dup_of"].notna()
    ev["event_date"] = ev["event_datetime"].dt.strftime("%Y-%m-%d")
    out = ev.drop(columns=["start_raw"])
    out.to_csv(DER / f"events{SUF}.csv.gz", index=False)
    print(f"events: {len(out)} | no usable date: {(out.date_source == 'none').sum()} | dated by end date: "
          f"{(out.date_source == 'end').sum()} | duplicates merged: {out.is_duplicate.sum()} | "
          f"without a plant: {out.plant_id.isna().sum()}")


def build_accidents():
    a = pd.read_csv(SL / "rmp_accidents_tx.csv.gz", **READ)
    acc = pd.DataFrame({
        "AccidentHistoryID": a["AccidentHistoryID"], "EPAFacilityID": a["EPAFacilityID"],
        "date": pd.to_datetime(a["AccidentDate"], errors="coerce"),
    })
    acc["plant_id"] = acc["EPAFacilityID"].map(members("RMP"))
    acc["O1"] = True
    acc["O2"] = (a["RE_Fire"] == "Yes") | (a["RE_Explosion"] == "Yes")
    acc["O3"] = pd.concat([num(a[c]) > 0 for c in HARM_PEOPLE], axis=1).any(axis=1)
    acc["O4"] = (pd.concat([num(a[c]) > 0 for c in OFFSITE_NUM], axis=1).any(axis=1)
                 | pd.concat([a[c] == "Yes" for c in OFFSITE_FLAG], axis=1).any(axis=1))
    acc["merged_into"] = ""
    if V2:
        merges = json.loads((DER / "accident_merges.json").read_text())
        for gone, m in merges.items():
            acc.loc[acc.AccidentHistoryID == gone, "merged_into"] = m["kept"]
            acc.loc[acc.AccidentHistoryID == m["kept"], "date"] = pd.Timestamp(m["date"])
        print(f"duplicate merges applied: {(acc.merged_into != '').sum()} (rows kept, flagged in merged_into)")
    acc = acc.sort_values(["plant_id", "date"])
    # R9: accidents at the same plant within 3 days of the previous one
    gap = acc[acc.merged_into == ""].groupby("plant_id")["date"].diff().dt.days
    acc["within_3d_of_previous"] = gap.reindex(acc.index).le(3)
    acc.to_csv(DER / f"accidents{SUF}.csv", index=False)

    # re-check the de-duplication from the file that keeps duplicates
    d = pd.read_csv(SL / "rmp_accidents_with_duplicates_tx.csv.gz", **READ)
    same_day = d.drop_duplicates(["EPAFacilityID", "AccidentDate"])
    print(f"accidents: {len(acc)} de-duplicated | raw with duplicates: {len(d)} | unique facility-days: "
          f"{len(same_day)} | without a plant: {acc.plant_id.isna().sum()} | missing date: {acc.date.isna().sum()}")


def build_risk():
    s = pd.read_csv(SL / "rmp_submissions_tx.csv.gz", **READ)
    f = pd.read_csv(SL / "rmp_facilities_tx.csv.gz", **READ)
    first = pd.to_datetime(s["ReceiptDate"], errors="coerce").groupby(s["EPAFacilityID"]).min()
    dereg = pd.to_datetime(f["LatestDeregEffDate"].where(f["LatestDeregEffDate"] != "", f["LatestDeregDate"]),
                           errors="coerce")
    fac = pd.DataFrame({"EPAFacilityID": f["EPAFacilityID"], "dereg": dereg.values})
    fac["first_receipt"] = fac["EPAFacilityID"].map(first)
    fac["start"] = (fac["first_receipt"] - pd.DateOffset(years=5)).clip(lower=TCEQ_START)
    fac["end"] = fac["dereg"].fillna(pd.Timestamp("2099-12-31"))
    fac["plant_id"] = fac["EPAFacilityID"].map(members("RMP"))
    risk = fac.dropna(subset=["plant_id"]).groupby("plant_id").agg(risk_start=("start", "min"),
                                                                   risk_end=("end", "max")).reset_index()
    risk.to_csv(DER / f"plant_risk{SUF}.csv", index=False)
    print(f"plant risk periods: {len(risk)} plants | deregistered by now: {(risk.risk_end.dt.year < 2099).sum()}")


if __name__ == "__main__":
    build_events()
    build_accidents()
    build_risk()
