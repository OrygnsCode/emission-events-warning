"""Download TCEQ emission event search exports, one per date window.

Why a real browser: the search form rejects headless user agents and plain
HTTP posts. Each export is saved untouched, with a sidecar JSON recording the
search used, the record count TCEQ reported, and a SHA-256 of the file, so the
list of incident numbers can be audited later.

Usage:
    python3 src/get_incident_lists.py --by start --years 2020
    python3 src/get_incident_lists.py --by start            # every year
    python3 src/get_incident_lists.py --by end              # cross-check list
    python3 src/get_incident_lists.py --by region           # no dates: catches
                                                            # incidents with unknown dates
"""
import os
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://www2.tceq.texas.gov/oce/eer/"
FORM = BASE + "index.cfm?fuseaction=main.searchForm&newsearch=yes"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium")  # any local Chromium build
FIRST_DAY = dt.date(2003, 1, 31)
SPLIT_ABOVE = 55000  # xls caps near 65,000 rows; split windows well before that
OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "search_exports"


def fmt(d):
    return d.strftime("%m/%d/%Y")


def search(page, by, start, end):
    """Run one search and return the record count TCEQ reports."""
    page.goto(FORM, wait_until="domcontentloaded")
    page.fill(f"#event_{by}_beg_dt", fmt(start))
    page.fill(f"#event_{by}_end_dt", fmt(end))
    page.click("#searchsubmit1")
    page.wait_for_load_state("domcontentloaded", timeout=240_000)
    text = page.inner_text("body")
    m = re.search(r"Your search returned\s+([\d,]+)\s+records?", text)
    if not m:
        if re.search(r"returned\s+0\s+records|no records", text, re.I):
            return 0
        raise RuntimeError(f"no record count on page for {by} {start}..{end}: {text[:300]!r}")
    return int(m.group(1).replace(",", ""))


def download_export(page, dest):
    with page.expect_download(timeout=600_000) as dl:
        page.click("text=Excel spreadsheet")
    dl.value.save_as(dest)


def fetch_region(page, code):
    """One search by TCEQ region, with no date criteria at all."""
    page.goto(FORM, wait_until="domcontentloaded")
    page.select_option("#ls_region_cd", code)
    page.click("#searchsubmit1")
    page.wait_for_load_state("domcontentloaded", timeout=240_000)
    m = re.search(r"Your search returned\s+([\d,]+)\s+records?", page.inner_text("body"))
    count = int(m.group(1).replace(",", "")) if m else 0
    label = f"region_{int(code):02d}"
    print(f"{label}: TCEQ reports {count} records", flush=True)
    if count > SPLIT_ABOVE:
        raise RuntimeError(f"{label} has {count} rows, too many for one xls export")
    OUT.mkdir(parents=True, exist_ok=True)
    xls = OUT / f"{label}.xls"
    if count:
        download_export(page, xls)
    meta = {
        "search_field": "region", "region": code, "tceq_reported_records": count,
        "file": xls.name if count else None,
        "bytes": xls.stat().st_size if count else 0,
        "sha256": hashlib.sha256(xls.read_bytes()).hexdigest() if count else None,
        "downloaded_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / f"{label}.json").write_text(json.dumps(meta, indent=2) + "\n")


def windows(start, end):
    """Yield (start, end) windows, splitting a span in half."""
    mid = start + (end - start) // 2
    return (start, mid), (mid + dt.timedelta(days=1), end)


def fetch_window(page, by, start, end, depth=0):
    count = search(page, by, start, end)
    label = f"{by}_{start:%Y%m%d}_{end:%Y%m%d}"
    print(f"{'  ' * depth}{label}: TCEQ reports {count} records", flush=True)
    if count > SPLIT_ABOVE and start < end:
        for a, b in windows(start, end):
            fetch_window(page, by, a, b, depth + 1)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    xls = OUT / f"{label}.xls"
    if count > 0:
        download_export(page, xls)
        digest = hashlib.sha256(xls.read_bytes()).hexdigest()
        size = xls.stat().st_size
    else:
        digest, size = None, 0
    meta = {
        "search_field": f"event_{by}",
        "begin": fmt(start),
        "end": fmt(end),
        "tceq_reported_records": count,
        "file": xls.name if count > 0 else None,
        "bytes": size,
        "sha256": digest,
        "downloaded_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / f"{label}.json").write_text(json.dumps(meta, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--by", choices=["start", "end", "region"], default="start")
    ap.add_argument("--years", nargs="*", type=int)
    args = ap.parse_args()

    today = dt.date.today()
    years = args.years or list(range(2003, today.year + 1))
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(user_agent=UA, accept_downloads=True)
        page = ctx.new_page()
        page.set_default_timeout(240_000)
        if args.by == "region":
            for code in (str(i) for i in range(1, 17)):
                for attempt in range(3):
                    try:
                        fetch_region(page, code)
                        break
                    except Exception as e:
                        print(f"  retry {attempt + 1} for region {code}: {e}", file=sys.stderr, flush=True)
                        time.sleep(10 * (attempt + 1))
                else:
                    print(f"FAILED region {code}", file=sys.stderr)
                    sys.exit(1)
                time.sleep(3)
            browser.close()
            return
        for y in years:
            start = max(dt.date(y, 1, 1), FIRST_DAY)
            end = min(dt.date(y, 12, 31), today)
            for attempt in range(3):
                try:
                    fetch_window(page, args.by, start, end)
                    break
                except Exception as e:  # network blips, slow server
                    print(f"  retry {attempt + 1} for {y}: {e}", file=sys.stderr, flush=True)
                    time.sleep(10 * (attempt + 1))
            else:
                print(f"FAILED year {y}", file=sys.stderr)
                sys.exit(1)
            time.sleep(3)
        browser.close()


if __name__ == "__main__":
    main()
