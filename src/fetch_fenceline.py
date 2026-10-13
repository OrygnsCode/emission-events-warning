"""Download EPA refinery fenceline benzene reports for Texas (40 CFR 63 Subpart CC, 63.658).

Route: the EPA WebFIRE report search. A GET of esearch2.cfm sets the session cookie,
then one POST to eSearchResults.cfm per calendar quarter (CEDRI submission date) with
state=TX, CFRpart="Part 63", CFRSubpart="Subpart CC". Each result row links to
FIRE/view/dspERTDocumentDetails.cfm?ID=<n>, a plain GET that serves the report file
(mostly CEDRI zips holding the quarterly xlsx/csv with the biweekly sampler values and
delta c). Reports for quarter N are submitted in quarter N+1, so 2018Q1 onward is covered
by searching submission quarters 2018Q1 to today (the first Texas submissions are in 2019).

Saved under data/external/epa_fenceline/:
  search/TX_CC_<YYYY>Q<q>.html.gz   search result pages (POST, recorded by this script)
  reports/<YYYY>Q<q>/<ID>_<title>   report files, by submission quarter (via fx.download)
  reports_index.csv                 one row per search hit (rebuilt every run)
  tceq_refinery_mact_summary.pdf    TCEQ's own quarterly summary of the same data
Every download goes into data/external/MANIFEST.jsonl. Re-running skips what is recorded.
The open quarter is searched up to today; its manifest key carries that end date, so a
later run searches it again and picks up new reports. At most 1 request per second.

Only report type AER is downloaded by default (the fenceline reports); semiannual MACT CC
compliance reports, NOCS and test reports that match the same search are listed in the
index but skipped unless --all-types is given.

Usage: python3 src/fetch_fenceline.py [--from 2018Q1] [--to 2026Q4] [--all-types] [--search-only]
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_external as fx  # noqa: E402

log = fx.log
SOURCE = "epa_fenceline"
OUT = fx.EXT / SOURCE
BASE = "https://cfpub.epa.gov/webfire/"
FORM = BASE + "reports/esearch2.cfm"
RESULTS = BASE + "reports/eSearchResults.cfm"
DOC = BASE + "FIRE/view/dspERTDocumentDetails.cfm?ID={}"
TCEQ_PDF = ("https://www.tceq.texas.gov/downloads/toxicology/refinery-mact/"
            "qrtlydata.pdf/@@download/file/qrtlydata.pdf")
PAUSE = 1.1
_last = [0.0]
_cookie = [False]


def wait():
    """Keep at least PAUSE seconds between requests to any server."""
    gap = time.monotonic() - _last[0]
    if gap < PAUSE:
        time.sleep(PAUSE - gap)
    _last[0] = time.monotonic()


def quarters(first, last):
    """(year, q) pairs from first to last inclusive, e.g. ("2018Q1", "2026Q4")."""
    y, q = int(first[:4]), int(first[-1])
    y2, q2 = int(last[:4]), int(last[-1])
    while (y, q) <= (y2, q2):
        yield y, q
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)


def quarter_dates(y, q):
    """Start and end date of a quarter as MM/DD/YYYY; an open quarter ends today."""
    start = dt.date(y, 3 * q - 2, 1)
    end = dt.date(y + (q == 4), (3 * q) % 12 + 1, 1) - dt.timedelta(days=1)
    end = min(end, dt.date.today())
    return start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")


def form(start, end):
    return {"organization": "", "facility": "", "startdate": start, "enddate": end,
            "state": "TX", "city": "", "zip": "", "CFRpart": "Part 63",
            "CFRSubpart": "Subpart CC", "Submit": "Submit Search"}


def record(name, key, body):
    """Store body gzip-compressed and append a manifest record like fx.download writes."""
    dest = OUT / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with gzip.open(tmp, "wb", compresslevel=6) as f:
        f.write(body)
    tmp.rename(dest)
    rec = {"source": SOURCE, "url": key, "file": f"{SOURCE}/{name}", "bytes": len(body),
           "sha256": hashlib.sha256(body).hexdigest(), "stored": "gzip", "last_modified": None,
           "downloaded_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(fx.MANIFEST, "a") as m:
        m.write(json.dumps(rec) + "\n")
    fx.done_urls().add(key)


def search(y, q):
    """Result page HTML for one submission quarter, from disk if already recorded."""
    start, end = quarter_dates(y, q)
    data = form(start, end)
    key = RESULTS + "?POST&" + urlencode({k: data[k] for k in ("state", "CFRpart", "CFRSubpart",
                                                               "startdate", "enddate")})
    name = f"search/TX_CC_{y}Q{q}.html.gz"
    if key in fx.done_urls() and (OUT / name).exists():
        return gzip.open(OUT / name).read().decode("utf-8", "replace")
    if not _cookie[0]:
        wait()
        fx.S.get(FORM, timeout=60).raise_for_status()
        _cookie[0] = True
    for attempt in range(1, 6):
        wait()
        try:
            r = fx.S.post(RESULTS, data=data, timeout=(20, 300))
            if r.status_code == 200 and "Report Search Results" in r.text:
                record(name, key, r.content)
                return r.text
            log(f"search {y}Q{q}: HTTP {r.status_code}, {len(r.content)} bytes")
        except Exception as e:
            log(f"search {y}Q{q} retry {attempt}: {type(e).__name__}: {str(e)[:120]}")
        _cookie[0] = False
        time.sleep(5 * attempt * attempt)
        wait()
        fx.S.get(FORM, timeout=60)
        _cookie[0] = True
    log(f"GAVE UP on search {y}Q{q}")
    return None


def cell(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def rows(page):
    """Report rows of a result page as dicts."""
    body = page[page.find("<tbody>"):page.find("</tbody>")]
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        td = re.findall(r"<td>(.*?)</td>", tr, re.S)
        doc = re.search(r'dspERTDocumentDetails\.cfm\?ID=(\d+)"\s+title="([^"]*)"', tr)
        if len(td) < 12 or not doc:
            continue
        bulk = re.search(r'name="docbulk1"[^>]*value="(\d+)"', tr)
        out.append({"organization": cell(td[0]), "facility": cell(td[1]), "city": cell(td[2]),
                    "county": cell(td[4]), "submitted": cell(td[5]), "report_type": cell(td[6]),
                    "sub_type": cell(td[7]), "doc_id": doc.group(1),
                    "bulk_id": bulk.group(1) if bulk else "", "title": html.unescape(doc.group(2)),
                    "attachments": cell(td[11])})
    n = re.search(r"Counts:\s*(\d+)", page)
    if n and int(n.group(1)) != len(out):
        log(f"  WARNING: page says {n.group(1)} reports, parsed {len(out)}")
    return out


def safe(title):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")[:120] or "report"


def fetch_report(y, q, row):
    """Download one report file; returns its stored path relative to data/external, or ''."""
    url = DOC.format(row["doc_id"])
    name = f"reports/{y}Q{q}/{row['doc_id']}_{safe(row['title'])}"
    if url not in fx.done_urls():
        wait()
    path = fx.download(SOURCE, url, name, gz=False, quiet=url in fx.done_urls())
    if row["attachments"] and row["attachments"] != "No Attachments":
        log(f"  NOTE: doc {row['doc_id']} lists related attachments, not fetched: {row['attachments'][:80]}")
    return f"{SOURCE}/{name}" if path else ""


def write_index(index):
    cols = ["search_quarter", "organization", "facility", "city", "county", "submitted",
            "report_type", "sub_type", "doc_id", "bulk_id", "title", "attachments", "file"]
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "reports_index.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(index)


def main():
    today = dt.date.today()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="first", default="2018Q1")
    ap.add_argument("--to", dest="last", default=f"{today.year}Q{(today.month - 1) // 3 + 1}")
    ap.add_argument("--all-types", action="store_true", help="also download non-AER reports")
    ap.add_argument("--search-only", action="store_true", help="save search pages and index only")
    a = ap.parse_args()
    index, total, got = [], 0, 0
    for y, q in quarters(a.first, a.last):
        page = search(y, q)
        if page is None:
            continue
        hits = rows(page)
        keep = [r for r in hits if a.all_types or r["report_type"] == "AER"]
        log(f"{y}Q{q}: {len(hits)} reports, {len(keep)} to fetch")
        total += len(keep)
        for r in hits:
            r["search_quarter"] = f"{y}Q{q}"
            r["file"] = ""
            if r in keep and not a.search_only:
                r["file"] = fetch_report(y, q, r)
                got += bool(r["file"])
            index.append(r)
        write_index(index)
    if not a.search_only:
        wait()
        fx.download(SOURCE, TCEQ_PDF, "tceq_refinery_mact_summary.pdf")
    log(f"done: {len(index)} rows in index, {total} selected, {got} files on disk")


if __name__ == "__main__":
    main()
