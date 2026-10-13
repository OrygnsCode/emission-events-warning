"""Apply the written duplicate-accident rule (plan D2 item 2) mechanically. No judgment, no events.

Candidates (same RMP facility; plan D8 adds the same rule for two RMP facilities linked to one plant):
  A. two accidents listed in different filings, 1 to 31 days apart, with the same chemicals and the same release
     type flags (gas, spill, fire, explosion);
  B. two accidents within 3 days of each other (the accident table's existing flag; also the basis of R9).
Rule: merge when the two records come from different filings AND every compared field agrees, or differs only
where one of the two records is blank. Two records in the same filing are never merged: a filing that lists two
accidents is the plant's own statement that there were two. Compared
fields: release duration; release source (storage vessel, piping, process vessel, transfer hose, valve, pump,
joint, other); consequences (deaths, injuries, property damage, offsite deaths, hospitalization, medical treatment,
evacuation, shelter in place, environmental damage flags); weather (wind speed and unit, wind direction,
temperature, stability class, precipitation, weather unknown). A merged accident takes the date from the record
whose most recent filing is later.

Reads only the RMP accident records and filing dates. Outputs data/derived/accident_doubles.csv (every candidate,
the fields that disagree, the decision) and data/derived/accident_merges.json (AccidentHistoryID merged away ->
the kept accident and its date).

Usage: python3 src/accident_doubles.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SL = ROOT / "data" / "slices"
OUT = ROOT / "data" / "derived"
READ = dict(dtype=str, keep_default_na=False)
FIELDS = {
    "duration": ["AccidentReleaseDuration"],
    "release source": ["RS_StorageVessel", "RS_Piping", "RS_ProcessVessel", "RS_TransferHose", "RS_Valve", "RS_Pump",
                       "RS_Joint", "OtherReleaseSource"],
    "consequences": ["DeathsWorkers", "DeathsPublicResponders", "DeathsPublic", "InjuriesWorkers",
                     "InjuriesPublicResponders", "InjuriesPublic", "OnsitePropertyDamage", "OffsiteDeaths",
                     "Hospitalization", "MedicalTreatment", "Evacuated", "ShelteredInPlace", "OffsitePropertyDamage",
                     "ED_Kills", "ED_MinorDefoliation", "ED_WaterContamination", "ED_SoilContamination", "ED_Other"],
    "weather": ["WindSpeed", "WindSpeedUnitCode", "WindDirection", "Temperature", "StabilityClass", "Precipitation",
                "WeatherUnknown"],
}
RE = ["RE_Gas", "RE_Spill", "RE_Fire", "RE_Explosion"]


def val(x):
    x = str(x).strip().upper()
    try:
        return float(x)
    except ValueError:
        return x


def compare(a, b):
    """Fields that disagree with both sides filled in."""
    bad = []
    for group, cols in FIELDS.items():
        for c in cols:
            x, y = str(a[c]).strip(), str(b[c]).strip()
            if x and y and val(x) != val(y):
                bad.append(f"{group}:{c}")
    return bad


def main():
    acc = pd.read_csv(SL / "rmp_accidents_tx.csv.gz", **READ)
    dup = pd.read_csv(SL / "rmp_accidents_with_duplicates_tx.csv.gz", **READ)
    sub = pd.read_csv(SL / "rmp_submissions_tx.csv.gz", usecols=["SubmissionID", "ReceiptDate"], **READ)
    dup = dup.merge(sub, on="SubmissionID", how="left")
    subs_of = dup.groupby(["EPAFacilityID", "AccidentDate"]).SubmissionID.apply(set).to_dict()
    last_filed = dup.groupby(["EPAFacilityID", "AccidentDate"]).ReceiptDate.max().to_dict()
    acc["date"] = pd.to_datetime(acc.AccidentDate, errors="coerce")
    rows = []
    for fac, g in acc.sort_values("date").groupby("EPAFacilityID"):
        g = g.reset_index(drop=True)
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                a, b = g.loc[i], g.loc[j]
                gap = (b.date - a.date).days
                if gap > 31:
                    break
                kinds = []
                if gap <= 3:
                    kinds.append("B_within_3_days")
                same_type = a.AccidentChemicals == b.AccidentChemicals and all(a[c] == b[c] for c in RE)
                diff_filings = not (subs_of.get((fac, a.AccidentDate), set()) & subs_of.get((fac, b.AccidentDate), set()))
                if 1 <= gap <= 31 and same_type and diff_filings:
                    kinds.append("A_same_type_different_filings")
                if not kinds:
                    continue
                bad = compare(a, b)
                merge = diff_filings and not bad
                la, lb = last_filed.get((fac, a.AccidentDate), ""), last_filed.get((fac, b.AccidentDate), "")
                keep, drop = (a, b) if la >= lb else (b, a)
                rows.append({"facility": fac, "accident_1": a.AccidentHistoryID, "date_1": a.AccidentDate,
                             "accident_2": b.AccidentHistoryID, "date_2": b.AccidentDate, "days_apart": gap,
                             "candidate_type": "+".join(kinds), "same_chemicals_and_release_type": same_type,
                             "different_filings": diff_filings, "fields_disagreeing": " ".join(bad),
                             "decision": "merge" if merge else "keep both",
                             "kept": keep.AccidentHistoryID if merge else "", "kept_date": keep.AccidentDate if merge else "",
                             "merged_away": drop.AccidentHistoryID if merge else ""})
    # plan D8: the same rule for two accidents at different RMP facilities linked to the same plant (the unit of the
    # analysis); records of different facilities are always in different filings
    pm = pd.read_csv(OUT / "plant_members_v2.csv", **READ)
    plant_of = dict(zip(pm.loc[pm.id_type == "RMP", "id"], pm.loc[pm.id_type == "RMP", "plant_id"]))
    acc["plant_id"] = acc.EPAFacilityID.map(plant_of)
    for plant, g in acc.dropna(subset=["plant_id"]).sort_values("date").groupby("plant_id"):
        g = g.reset_index(drop=True)
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                a, b = g.loc[i], g.loc[j]
                gap = (b.date - a.date).days
                if gap > 31:
                    break
                if a.EPAFacilityID == b.EPAFacilityID:
                    continue
                kinds = ["B_within_3_days"] if gap <= 3 else []
                same_type = a.AccidentChemicals == b.AccidentChemicals and all(a[c] == b[c] for c in RE)
                if 1 <= gap <= 31 and same_type:
                    kinds.append("A_same_type_different_filings")
                if not kinds:
                    continue
                bad = compare(a, b)
                la = last_filed.get((a.EPAFacilityID, a.AccidentDate), "")
                lb = last_filed.get((b.EPAFacilityID, b.AccidentDate), "")
                keep, drop = (a, b) if la >= lb else (b, a)
                rows.append({"facility": f"{a.EPAFacilityID}|{b.EPAFacilityID} (plant {plant})",
                             "accident_1": a.AccidentHistoryID, "date_1": a.AccidentDate,
                             "accident_2": b.AccidentHistoryID, "date_2": b.AccidentDate, "days_apart": gap,
                             "candidate_type": "+".join(kinds) + "+C_two_facilities_one_plant",
                             "same_chemicals_and_release_type": same_type, "different_filings": True,
                             "fields_disagreeing": " ".join(bad), "decision": "keep both" if bad else "merge",
                             "kept": "" if bad else keep.AccidentHistoryID,
                             "kept_date": "" if bad else keep.AccidentDate,
                             "merged_away": "" if bad else drop.AccidentHistoryID})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "accident_doubles.csv", index=False)
    merges = {r.merged_away: {"kept": r.kept, "date": r.kept_date} for r in out.itertuples() if r.decision == "merge"}
    (OUT / "accident_merges.json").write_text(json.dumps(merges, indent=1) + "\n")
    print(f"candidates: {len(out)} | by type: {out.candidate_type.value_counts().to_dict()}")
    print(f"decisions: {out.decision.value_counts().to_dict()}")
    print(out[["days_apart", "candidate_type", "decision", "fields_disagreeing"]].to_string(max_colwidth=70))


if __name__ == "__main__":
    main()
