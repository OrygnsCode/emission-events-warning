"""Download the external reference datasets, with a hash manifest.

Sources: EPA FRS (plant ID crosswalk), NOAA Storm Events (weather confounders),
EPA ECHO (inspections, violations, industry codes), National Response Center
(independent incident reports). File names are read from each site's own
listing, not guessed. Every file is recorded in data/external/MANIFEST.jsonl
with its URL, size, SHA-256 and download time. Re-running skips finished files.

Usage: python3 src/fetch_external.py [noaa|echo|nrc|frs|tceq ...]
"""
import datetime as dt
import gzip
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "data" / "external"
MANIFEST = EXT / "MANIFEST.jsonl"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
S = requests.Session()
S.headers["User-Agent"] = UA


def log(msg):
    print(f"{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {msg}", flush=True)


_DONE = None


def done_urls():
    """URLs already in the manifest (read once per process, then kept up to date)."""
    global _DONE
    if _DONE is None:
        _DONE = set()
        if MANIFEST.exists():
            _DONE = {json.loads(l)["url"] for l in MANIFEST.read_text().splitlines() if l.strip()}
    return _DONE


_MLOCK = __import__("threading").Lock()


def download(source, url, name=None, gz=False, params=None, headers=None, key=None, quiet=False, timeout=120,
             session=None):
    """Download url to data/external/<source>/<name> and record it in the manifest.

    gz=True stores the file gzip-compressed (name gets .gz); the SHA-256 and byte count are of the
    original bytes as served, so the hash can be checked against a fresh download.
    key is what the manifest records as the URL (defaults to url; use it when params carry the query).
    Returns the stored path, or None if the server refused or it kept failing.
    session: a requests session to use instead of the shared one (for parallel downloads).
    """
    sess = session or S
    key = key or url
    name = name or url.rsplit("/", 1)[-1]
    if gz and not name.endswith(".gz"):
        name += ".gz"
    dest = EXT / source / name
    if key in done_urls() and dest.exists():
        if not quiet:
            log(f"skip (have it): {source}/{name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, 6):
        try:
            h = hashlib.sha256()
            size = 0
            with sess.get(url, params=params, headers=headers, stream=True, timeout=(20, timeout)) as r:
                if r.status_code != 200:
                    log(f"FAILED {url} {params or ''}: HTTP {r.status_code}")
                    if r.status_code in (400, 401, 403, 404, 410, 422):
                        return None
                    raise RuntimeError(f"http {r.status_code}")
                last_mod = r.headers.get("Last-Modified")
                out = gzip.open(tmp, "wb", compresslevel=6) if gz else open(tmp, "wb")
                with out as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                        h.update(chunk)
                        size += len(chunk)
                expect = r.headers.get("Content-Length")
                if expect and r.headers.get("Content-Encoding") in (None, "identity") and int(expect) != size:
                    raise RuntimeError(f"short read {size} of {expect}")
            tmp.rename(dest)
            rec = {"source": source, "url": key, "file": f"{source}/{name}", "bytes": size,
                   "sha256": h.hexdigest(), "stored": "gzip" if gz else "as served", "last_modified": last_mod,
                   "downloaded_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
            with _MLOCK:
                with open(MANIFEST, "a") as m:
                    m.write(json.dumps(rec) + "\n")
                done_urls().add(key)
            if not quiet:
                log(f"ok {source}/{name} ({size / 1e6:.1f} MB)")
            return dest
        except Exception as e:
            log(f"retry {attempt} for {name}: {type(e).__name__}: {str(e)[:120]}")
            time.sleep(min(60, 5 * attempt * attempt))
    log(f"GAVE UP on {url} {params or ''}")
    return None


def noaa():
    base = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
    html = S.get(base, timeout=60).text
    pat = r'href="(StormEvents_(?:details|locations|fatalities)-ftp_v1\.0_d(\d{4})_c\d+\.csv\.gz)"'
    files = sorted({n for n, y in re.findall(pat, html) if 2003 <= int(y) <= 2026})
    log(f"NOAA: {len(files)} year files found")
    for n in files:
        download("noaa_storm_events", base + n)
    for n in ("README", "Storm-Data-Bulk-csv-Format.pdf", "Storm-Data-Export-Format.pdf", "ugc_areas.csv"):
        download("noaa_storm_events", base + n)


def echo():
    base = "https://echo.epa.gov/"
    for path in ("files/echodownloads/ICIS-AIR_downloads.zip",
                 "files/echodownloads/echo_exporter.zip",
                 "system/files/echo_exporter_columns_7-16-2025_0.xlsx",
                 "files/echodownloads/POLL_RPT_COMBINED_EMISSIONS.zip"):
        download("epa_echo", base + path)


def nrc():
    page = "https://nrc.uscg.mil/"
    html = S.get(page, timeout=60).text
    links = sorted(set(re.findall(r'href=["\']([^"\']*FOIAFiles/[^"\']+)["\']', html)))
    log(f"NRC: {len(links)} download links on the home page")
    for l in links:
        log(f"  found {l}")
    # decade files cover through 2024; the yearly files named CY25 and CY26 cover the rest
    want = [l for l in links if re.search(r"DECADE|DataDictionary|CY2[56]\.xlsx", l, re.I)]
    for l in want:
        download("nrc", urljoin(page, l))


def frs():
    download("epa_frs", "https://ordsext.epa.gov/FLA/www3/state_files/state_combined_tx.zip")


def tceq():
    page = "https://www.tceq.texas.gov/agency/data/lookup-data/download-data.html"
    r = S.get(page, timeout=60, allow_redirects=True)
    out = EXT / "tceq_pages" / "download-data.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    links = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
    log(f"TCEQ download-data page: HTTP {r.status_code}, final URL {r.url}, {len(links)} links")
    for l in links:
        if re.search(r"\.(zip|xlsx?|csv|txt|gz)\b|central|registry|regulated|download", l, re.I):
            log(f"  candidate {urljoin(r.url, l)}")


JOBS = {"frs": frs, "noaa": noaa, "echo": echo, "nrc": nrc, "tceq": tceq}

if __name__ == "__main__":
    EXT.mkdir(parents=True, exist_ok=True)
    for name in (sys.argv[1:] or list(JOBS)):
        log(f"=== {name} ===")
        try:
            JOBS[name]()
        except Exception as e:
            log(f"{name} failed: {type(e).__name__}: {e}")
    log("all done")
