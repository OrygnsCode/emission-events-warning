"""Summary of the quality pass over the saved TCEQ detail pages (made after src/quality_pass.py).

Counts from data/derived/page_checks.csv.gz: pages saved, hash and incident-number checks, parser warnings, pages
without emission points or contaminants, and header fields that differ from the official search list. The two notes
say what the differences turned out to be when they were looked at. Also the share of each primary cause (frozen
rules v1.0) among unplanned emission events.

Output: data/manifests/quality_report.json
Usage:  python3 src/quality_summary.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DER = ROOT / "data" / "derived"
OUT = ROOT / "data" / "manifests" / "quality_report.json"
NOTES = {
    "customer": "formatting only: the list joins co-owners with | and repeats names; the page prints them side by side",
    "start": "one event on 2008-03-09, the daylight saving switch day (page 03:12 AM, list 02:12 AM)"}


def main():
    p = pd.read_csv(DER / "page_checks.csv.gz", dtype=str, keep_default_na=False)
    master = pd.read_csv(ROOT / "data" / "master" / "incidents.csv.gz", dtype=str)
    causes = pd.read_csv(DER / "causes.csv.gz", dtype=str)
    yes = lambda c: p[c] == "True"  # noqa: E731
    unplanned = set(master.loc[master["EVENT TYPE"] == "EMISSIONS EVENT", "INCIDENT NO."])
    u = causes[causes.incident.isin(unplanned)]
    res = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tceq_detail_pages": {
            "master_incidents": len(master),
            "pages_saved": len(p),
            "distinct_incidents": int(p.incident.nunique()),
            "sha256_mismatches": int((~yes("sha_ok")).sum()),
            "wrong_incident_number": int((~yes("incident_matches")).sum()),
            "missing_from_master": int((~yes("in_master")).sum()),
            "parser_warnings": int((p.n_warnings.astype(int) > 0).sum()),
            "pages_without_emission_points": int((p.n_emission_points.astype(int) == 0).sum()),
            "pages_without_contaminants": int((p.n_contaminants.astype(int) == 0).sum())},
        "header_mismatches_vs_official_list": {c[len("mismatch_"):]: int(yes(c).sum())
                                               for c in p.columns if c.startswith("mismatch_")},
        "header_mismatch_notes": NOTES,
        "cause_rules": {
            "version": "1.0, frozen 2026-10-02 on the development sample (1,000 events), before any linking to accidents",
            "unplanned_events": len(u),
            "primary_cause_shares": {k: round(float(v), 3)
                                     for k, v in u.primary_cause.value_counts(normalize=True).items()}}}
    OUT.write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
