"""Completeness checks on the yearly search exports.

1. Each export has exactly as many rows as TCEQ said the search returned.
2. No incident number repeats within one list.
3. The by-start-date lists and by-end-date lists cover the same incidents.
   Any incident found by only one of them (for example, one with a missing
   date) is printed so it can be investigated.

Usage: python3 src/check_lists.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "search_exports"


def main():
    sets = {"start": set(), "end": set(), "region": set()}
    meta_total = {"start": 0, "end": 0, "region": 0}
    problems = 0
    for js in sorted(DIR.glob("*.json")):
        m = json.loads(js.read_text())
        by = {"event_start": "start", "event_end": "end", "region": "region"}[m["search_field"]]
        reported = m["tceq_reported_records"]
        meta_total[by] += reported
        if not m["file"]:
            if reported:
                print(f"PROBLEM {js.name}: reported {reported} but no file"); problems += 1
            continue
        df = pd.read_excel(DIR / m["file"])
        n = len(df)
        dup = n - df["INCIDENT NO."].nunique()
        if n != reported or dup:
            print(f"PROBLEM {m['file']}: rows {n}, TCEQ reported {reported}, duplicate incident numbers {dup}")
            problems += 1
        sets[by].update(int(x) for x in df["INCIDENT NO."])
    print(f"by start date: {meta_total['start']} reported, {len(sets['start'])} distinct incidents")
    print(f"by end date:   {meta_total['end']} reported, {len(sets['end'])} distinct incidents")
    print(f"by region:     {meta_total['region']} reported, {len(sets['region'])} distinct incidents")
    only_start = sorted(sets["start"] - sets["end"])
    only_end = sorted(sets["end"] - sets["start"])
    print(f"in start lists only: {len(only_start)}   in end lists only: {len(only_end)}")
    dates = sets["start"] | sets["end"]
    print(f"union of date lists: {len(dates)}")
    if sets["region"]:
        only_region = sorted(sets["region"] - dates)
        not_in_region = sorted(dates - sets["region"])
        print(f"found by region only (invisible to date searches): {len(only_region)} {only_region}")
        print(f"in date lists but not in region lists: {len(not_in_region)} {not_in_region[:15]}")
        print(f"MASTER LIST (union of all): {len(dates | sets['region'])}")
    print("per-file row counts: OK" if not problems else f"{problems} PROBLEM FILES")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
