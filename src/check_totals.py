"""Count the whole TCEQ database without using dates, and compare to our list.

Date searches cannot see an incident whose start and end are both UNKNOWN.
Splitting by region, or by event type, covers every incident whatever its
dates. The counts only (no downloads) are read from the results page. Each
split should add up to the same total, and that total should equal the number
of distinct incident numbers in our saved lists.

Usage: python3 src/check_totals.py
"""
import re
import sys
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from get_incident_lists import CHROME, FORM, UA  # noqa: E402

DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "search_exports"
REGIONS = [str(i) for i in range(1, 17)]
TYPES = ["AIRSHUTDWN", "AIRSTARTUP", "AIRU", "AIROPACITY", "AIRM"]


def count(page, field=None, value=None):
    page.goto(FORM, wait_until="domcontentloaded")
    if field:
        page.select_option(f"#{field}", value)
    page.click("#searchsubmit1")
    page.wait_for_load_state("domcontentloaded", timeout=240_000)
    text = page.inner_text("body")
    m = re.search(r"Your search returned\s+([\d,]+)\s+records?", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0 if re.search(r"returned\s+0|no records", text, re.I) else None


def main():
    ours = set()
    for f in sorted(DIR.glob("*.xls")):
        ours.update(int(x) for x in pd.read_excel(f, usecols=["INCIDENT NO."])["INCIDENT NO."])
    print(f"distinct incidents in our saved lists: {len(ours)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        page = browser.new_context(user_agent=UA).new_page()
        page.set_default_timeout(240_000)

        def split(field, values):
            out = {}
            for v in values:
                out[v] = count(page, field, v)
                time.sleep(2)
            return out

        everything = count(page)
        by_region = split("ls_region_cd", REGIONS)
        by_type = split("ls_event_typ_cd", TYPES)
        browser.close()

    print(f"no criteria at all: {everything}")
    print(f"by region: {by_region}")
    print(f"  sum {sum(v or 0 for v in by_region.values())}")
    print(f"by event type: {by_type}")
    print(f"  sum {sum(v or 0 for v in by_type.values())}")
    totals = {sum(v or 0 for v in by_region.values()), sum(v or 0 for v in by_type.values())}
    if everything:
        totals.add(everything)
    if len(totals) == 1 and totals == {len(ours)}:
        print("RESULT: every way of counting agrees with our list. No incidents missed.")
    else:
        print(f"RESULT: counts {sorted(totals)} vs our list {len(ours)}. Investigate the gap.")
        sys.exit(1)


if __name__ == "__main__":
    main()
