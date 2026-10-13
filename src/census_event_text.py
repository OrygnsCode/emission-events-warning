"""Phrase census of the TCEQ emission event report text (data dossier, no accident data).

Counts, over all 103,614 parsed reports, the wordings found while reading the 3,058-report stratified sample:
retractions and non-events, duplicate and continuation wordings, references to other incident numbers,
placeholder zero amounts, and reporting delays. Each count is also split by whether the frozen
report_status rules (rules/cause_rules.json, v1.0) already flag the report, so the size of any gap is known
before any rule is proposed. Nothing here changes a frozen rule or touches accident data.

Output: data/derived/event_text_census.json
Usage:  python3 src/census_event_text.py
"""
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="This pattern is interpreted")
ROOT = Path(__file__).resolve().parent.parent
DER = ROOT / "data" / "derived"

# wordings seen in the reading, grouped; matched case-insensitively on cause + actions + basis
NON_EVENT = {
    "non_event": r"\bnon[- ]?event\b|\bnot an? (emissions? )?event\b",
    "did_not_occur": r"\b(did not|didn'?t|never) (occur|take place|happen)\b|\b(event|activity|startup|start-up|shutdown) (did not|didn'?t) (occur|take place)\b",
    "cancelled_postponed": r"\b(was|been|is|has been) cancell?ed\b|\bcancell?ed\b|\bpostponed\b",
    "rescind_void_delete": r"\brescind\w*\b|\bvoid(ed)?\b|\bplease delete\b|\bdelete (this|the) (report|incident|notification)\b",
    "should_not_have_been_reported": r"\bshould (not|n'?t) have been (reported|submitted|entered)\b|\bnotification was not required\b",
    "uml0": r"\buml[- ]?[0o]\b",
    "recordable_only": r"\brecordable[- ]only\b|\brecordable \(non[- ]reportable\)|\breclassified as (a )?recordable\b|\brecordable (emissions? )?event only\b",
    "zeroed_out": r"\bzero'?(e)?d out\b",
    "no_excess_emissions": r"\bno (excess|unauthorized) (emissions?|opacity)\b|\bwithout (any )?excess (opacity|emissions?)\b|\bno (visible|excess) (opacity|emissions?) (was|were) observed\b",
    "abundance_of_caution": r"\babundance of caution\b|\bout of an abundance\b|\bprotective filing\b",
    "below_rq_other": r"\bnon[- ]?rq\b|\bnot (above|exceed\w*|reach\w*) (the |a |any )?(rq|reportable quantit)|\bno (reportable quantit(y|ies)|rqs?) (was|were) (exceeded|reached)\b",
}
DUPLICATE = {
    "duplicate_other_wording": r"\bduplicate (steers|entry|report)\b|\bdouble[- ]?report\w*\b|\b(reported|entered|submitted|put in|input) twice\b",
    "refer_to_incident": r"\b(please )?refer to (incident|steers|tceq)\b|\breported under (steers|incident|tceq)\b|\bsuperseded by\b",
    "same_event_as": r"\bsame (event|incident) (as|that)\b|\bfor the same incident\b|\b\d+ of \d+ (reports|notifications)\b|\bnotification \d+ of \d+\b",
    "continuation": r"\bcontinuation of\b|\bcontinued from (incident|steers)\b|\bongoing event under\b",
}
# narrower versions written after reading random hits of the wide lists above (wide lists catch boilerplate such as
# "this was not an event that required an emergency response" and "refer to TCEQ, Region 3, confidential files")
NARROW_NON_EVENT = {
    "rescind_void": r"\brescind\w*\b|\b(report|notification|incident|event|steers)\w* (is |was |be |has been )?void(ed)?\b|\bplease (delete|void|back out)\b|\bcancell?ed/void\b",
    "not_required": r"\bshould (not|n'?t) have been (reported|submitted|entered)\b|\bnotification was not (required|applicable)\b",
    "uml0": r"\buml[- ]?[0o]\b",
    "zeroed": r"\b(been|being|were|was|is) zero'?e?d out\b",
    "did_not_occur": r"\b(event|activity|startup|start-up|shutdown|shut down|maintenance|incident) (did not|didn'?t|never) (occur|take place|happen)\b|\bdid not take place\b",
    "cancelled": r"\b(activity|event|job|maintenance|startup|start-up|shutdown|notification|work|bake out)\s+(was |has been |is |been )?(cancell?ed|postponed)\b",
    "non_event": r"\b(this|it) (was|is) a (non[- ]?event|nonevent)\b|\bnon[- ]emissions? event\b|\"non-event\"",
}
NARROW_DUPLICATE = {
    "duplicate_other_wording": DUPLICATE["duplicate_other_wording"],
    "split": r"\bnotification \d+ of \d+\b|\b\d+ of \d+ (reports|notifications) for the same\b|\bsame (event|incident) as\b",
    "continuation": DUPLICATE["continuation"],
    "refer": r"\b(please )?refer to (tceq |steers )?(incident|steers|tracking)\s*(no\.?|number|#)?\s*#?\s*\d{5,6}\b"
             r"|\breported under (steers|incident|tceq)\s*(no\.?|number|#)?\s*#?\s*\d{5,6}\b",
}
FROZEN = ["status_duplicate", "status_not_reportable", "status_filed_in_error"]
INC_REF = re.compile(r"(?:INCIDENT|STEERS|TCEQ|TRACKING|REPORT)\s*(?:NO\.?|NUMBER|NUM|#|ID)?\s*[#:]?\s*(\d{5,6})\b")
SURROGATES = [0.0001, 0.001, 0.01]


def main():
    d = pd.read_parquet(DER / "details_table.parquet", columns=["incident", "report_type", "event_type", "rn",
                                                                  "cause", "actions_taken", "basis"])
    d["incident"] = d.incident.astype(int)
    st = pd.read_csv(DER / "causes.csv.gz", usecols=["incident"] + FROZEN)
    ev = pd.read_csv(DER / "events_v2.csv.gz", parse_dates=["event_datetime", "report_date"])
    d = d.merge(st, on="incident", how="left").merge(
        ev[["incident", "plant_id", "event_datetime", "report_date", "is_duplicate"]], on="incident", how="left")
    text = (d.cause.fillna("") + " | " + d.actions_taken.fillna("") + " | " + d.basis.fillna("")).str.upper()
    frozen_any = d[FROZEN].fillna(False).any(axis=1)
    # reports that can enter the H1 exposure: emissions events at plants with an RMP risk period, dated from 97 days
    # before the study start to the D2 primary end, after the same-start merge
    risk_ids = set(pd.read_csv(DER / "plant_risk_v2.csv").plant_id)
    expo = (d.event_type.eq("EMISSIONS EVENT") & d.plant_id.isin(risk_ids) & ~d.is_duplicate.fillna(False).astype(bool)
            & d.event_datetime.between(pd.Timestamp("2003-06-01") - pd.Timedelta(days=97), pd.Timestamp("2021-12-31")))
    out = {"reports": len(d), "frozen_status_any": int(frozen_any.sum()),
           "frozen_status": {c: int(d[c].fillna(False).sum()) for c in FROZEN}}

    def tally(groups):
        res, hit_any = {}, pd.Series(False, index=d.index)
        for k, pat in groups.items():
            h = text.str.contains(pat, flags=re.I, regex=True)
            hit_any |= h
            res[k] = {"reports": int(h.sum()), "not_flagged_by_frozen_rules": int((h & ~frozen_any).sum())}
        res["_any"] = {"reports": int(hit_any.sum()), "not_flagged_by_frozen_rules": int((hit_any & ~frozen_any).sum()),
                       "emissions_events_at_linked_plants_not_flagged": int(
                           (hit_any & ~frozen_any & d.event_type.eq("EMISSIONS EVENT") & d.plant_id.notna()).sum()),
                       "h1_exposure_reports_not_flagged": int((hit_any & ~frozen_any & expo).sum())}
        return res, hit_any

    out["non_event_wordings"], ne = tally(NON_EVENT)
    out["duplicate_wordings"], du = tally(DUPLICATE)
    out["narrow_non_event"], _ = tally(NARROW_NON_EVENT)
    out["narrow_duplicate"], _ = tally(NARROW_DUPLICATE)
    out["h1_exposure_reports"] = {"total": int(expo.sum()),
                                  **{c: int((expo & d[c].fillna(False)).sum()) for c in FROZEN},
                                  "initial_only": int((expo & d.report_type.eq("INITIAL")).sum())}

    # references to other incident numbers
    nums = set(d.incident)
    by_inc = d.set_index("incident")
    refs = []
    for inc, t in zip(d.incident, text):
        for m in INC_REF.finditer(t):
            r = int(m.group(1))
            if r != inc and r in nums:
                refs.append((inc, r))
    rf = pd.DataFrame(refs, columns=["incident", "ref"]).drop_duplicates()
    rf["same_rn"] = by_inc.rn.reindex(rf.incident).values == by_inc.rn.reindex(rf.ref).values
    gap = (by_inc.event_datetime.reindex(rf.incident).values - by_inc.event_datetime.reindex(rf.ref).values)
    rf["abs_days"] = np.abs(pd.to_timedelta(gap).days)
    out["cross_references"] = {
        "reports_citing_another_existing_incident": int(rf.incident.nunique()),
        "pairs": len(rf),
        "pairs_same_rn": int(rf.same_rn.sum()),
        "pairs_same_rn_within_7_days": int((rf.same_rn & rf.abs_days.le(7)).sum()),
        "pairs_same_rn_already_merged_by_same_start_rule": int(
            (rf.same_rn & (by_inc.is_duplicate.reindex(rf.incident).fillna(False).values
                           | by_inc.is_duplicate.reindex(rf.ref).fillna(False).values)).sum()),
        "pairs_other_rn": int((~rf.same_rn).sum()),
        "citing_reports_flagged_by_frozen_rules": int(frozen_any[d.incident.isin(rf.incident)].sum()),
    }

    # report form and delay
    out["report_type"] = d.report_type.value_counts().to_dict()
    lag = (d.report_date - d.event_datetime.dt.normalize()).dt.days
    out["report_lag_days"] = {"median": float(lag.median()), "share_over_30": round(float((lag > 30).mean()), 4),
                              "share_over_365": round(float((lag > 365).mean()), 4),
                              "reports_over_365": int((lag > 365).sum()), "negative": int((lag < 0).sum())}
    alt = text.str.contains(r"STEERS (WAS |IS )?(DOWN|OUTAGE|UNAVAILABLE)|STEERS DOWNTIME|DUE TO STEERS", regex=True)
    out["steers_outage_mentions"] = int(alt.sum())

    # placeholder amounts and opacity
    c = pd.read_csv(DER / "contaminants.csv.gz", usecols=["incident", "description", "quantity", "units"])
    lb = c[c.units.eq("POUNDS")]
    out["contaminant_rows_pounds"] = len(lb)
    out["placeholder_amounts"] = {str(v): int(np.isclose(lb.quantity, v, rtol=0, atol=v * 1e-6).sum()) for v in SURROGATES}
    out["zero_amounts"] = int(lb.quantity.eq(0).sum())
    op = c[c.units.eq("% OPACITY")]
    out["opacity_rows"] = len(op)
    out["opacity_over_100"] = int(op.quantity.gt(100).sum())
    co2 = lb.description.str.upper().str.strip().isin(["CARBON DIOXIDE", "CO2"])
    out["co2_share_of_reported_pounds"] = round(float(lb.quantity[co2].sum() / lb.quantity.sum()), 4)

    (DER / "event_text_census.json").write_text(json.dumps(out, indent=1, default=int) + "\n")
    print(json.dumps(out, indent=1, default=int))


if __name__ == "__main__":
    main()
