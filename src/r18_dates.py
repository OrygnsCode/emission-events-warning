"""Original dates of the RMP accidents whose date the plant later changed, for robustness check R18 (plan 6.2, D2).

EPA's change history (tblS6AccidentHistory_ChangeHistory) keeps the old date of every corrected accident record.
Each changed record is matched to the accident the study uses: the record itself if it is in the accident table
with the corrected date, otherwise the accident table's record for the same facility on the corrected date (a later
filing that carries the corrected date forward).

Output: data/manifests/r18_original_dates.csv (changed_record, EPAFacilityID, study_record, corrected, original)
Usage:  python3 src/r18_dates.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "slices" / "rmp_raw"
OUT = ROOT / "data" / "manifests" / "r18_original_dates.csv"
R = dict(dtype=str, keep_default_na=False)


def main():
    ch = pd.read_csv(RAW / "tblS6AccidentHistory_ChangeHistory.csv.gz",
                     usecols=["AccidentHistoryID", "FacilityID", "AccidentDate", "OldAccidentDate"], **R)
    ch["corrected"], ch["original"] = ch.AccidentDate.str[:10], ch.OldAccidentDate.str[:10]
    ch = ch[(ch.corrected != "") & (ch.original != "") & (ch.corrected != ch.original)]
    fac = pd.read_csv(RAW / "tblS1Facilities.csv.gz", usecols=["FacilityID", "EPAFacilityID"], **R).drop_duplicates()
    ch = ch.merge(fac, on="FacilityID", how="left")
    acc = pd.read_csv(ROOT / "data" / "derived" / "accidents_v2.csv", dtype=str)
    own = set(zip(acc.AccidentHistoryID, acc.date))
    rows = []
    for r in ch.itertuples():
        if (r.AccidentHistoryID, r.corrected) in own:
            study = r.AccidentHistoryID
        else:
            m = acc[(acc.EPAFacilityID == r.EPAFacilityID) & (acc.date == r.corrected)]
            if len(m) != 1:
                raise SystemExit(f"record {r.AccidentHistoryID}: {len(m)} accidents on the corrected date")
            study = m.AccidentHistoryID.iloc[0]
        rows.append((r.AccidentHistoryID, r.EPAFacilityID, study, r.corrected, r.original))
    out = pd.DataFrame(rows, columns=["changed_record", "EPAFacilityID", "study_record", "corrected", "original"])
    out.to_csv(OUT, index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
