"""Stream GDELT article lists and keep only links that match the written rules (rules/gdelt_url_rules.json).

Strict use (plan Deviation D1): only the batch time, collection type, website and article link are
read. Each GDELT file is downloaded, checked against GDELT's MD5 (GDELT 2), scanned, and deleted; only
the matching rows are kept. A fast first pass (awk) keeps rows whose link contains any event word (every kept row
must have one), then the exact rules are applied in Python.

Outputs (data/external/gdelt/):
  hits/<stream>/<YYYYMM>.tsv   matching rows: date, collection, website, link, rules matched, file
  done_<stream>.tsv           every processed file: url, bytes, md5, sha256, rows scanned, rows kept
  masterfilelist.txt          GDELT's own list of files (recorded in MANIFEST.jsonl with its hash)

Usage: python3 src/fetch_gdelt.py [gdelt1_gkg_daily gdelt1_events_daily gdelt2_gkg] [--workers 3]
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_external as fx  # noqa: E402
from fetch_external import S, log  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "external" / "gdelt"
# each file is held only while it is scanned; RAM disk avoids writing 150 MB/s of throwaway files
TMP = Path("/dev/shm/gdelt_tmp") if Path("/dev/shm").is_dir() else ROOT / "data" / "state" / "gdelt_tmp"
RULES = json.loads((ROOT / "rules" / "gdelt_url_rules.json").read_text())
BASE = "https://data.gdeltproject.org/"
LOCK = threading.Lock()


def _compile(words):
    """One regex per list: whole words for entries of 3 letters or fewer, word-prefix otherwise;
    phrases must be consecutive words. Applied to ' '.join(words) of the link."""
    parts = []
    for w in words:
        toks = w.lower().split()
        last = re.escape(toks[-1]) + ("" if len(toks) == 1 and len(toks[0]) <= 3 else r"\w*")
        if len(toks) == 1 and len(toks[0]) <= 3:
            last = re.escape(toks[0])
        body = r"\s".join([re.escape(t) for t in toks[:-1]] + [last])
        parts.append(body)
    return re.compile(r"(?:^|\s)(?:" + "|".join(parts) + r")(?=\s|$)")


EVENT = _compile(RULES["event_words"])
FACIL = _compile(RULES["facility_words"])
TOWN = _compile(RULES["industrial_town_words"])
PLACE = _compile(RULES["texas_place_words"])
SITES = tuple(RULES["texas_news_websites"])
# fast first pass (C grep): any event word as a substring, case-insensitive
PREFILTER = "|".join(sorted({w.split()[0] for w in RULES["event_words"]}))


def link_words(url):
    u = url.lower()
    u = re.sub(r"^[a-z]+://", "", u)
    u = u.split("/", 1)[1] if "/" in u else ""
    return " ".join(w for w in re.split(r"[^a-z0-9]+", u) if w)


def judge(url, site):
    words = link_words(url)
    if not EVENT.search(words):
        return None
    b = bool(FACIL.search(words))
    c = bool(TOWN.search(words))
    if not (b or c):
        return None
    tx_place = bool(PLACE.search(words))
    full = (site + "/" + url.lower().split("://", 1)[-1])
    tx_site = any(s in full for s in SITES)
    return ("B" if b else "") + ("C" if c else "") + ("|txplace" if tx_place else "") + ("|txsite" if tx_site else "")


def fetch(url, size_hint=None):
    TMP.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(dir=TMP, suffix=".zip")
    os.close(fd)
    for attempt in range(1, 6):
        try:
            md5, sha, n = hashlib.md5(), hashlib.sha256(), 0
            with S.get(url, stream=True, timeout=(20, 300)) as r:
                if r.status_code == 404:
                    os.unlink(path)
                    return None, None
                r.raise_for_status()
                with open(path, "wb") as f:
                    for ch in r.iter_content(1 << 20):
                        f.write(ch)
                        md5.update(ch)
                        sha.update(ch)
                        n += len(ch)
            # the listed size is sometimes wrong in GDELT's own file list; the MD5 check in work() is the real test
            return path, {"bytes": n, "md5": md5.hexdigest(), "sha256": sha.hexdigest()}
        except Exception as e:
            log(f"retry {attempt} {url.rsplit('/', 1)[-1]}: {type(e).__name__} {str(e)[:100]}")
            time.sleep(5 * attempt)
    os.unlink(path)
    raise RuntimeError(f"gave up on {url}")


def scan(path, stream):
    """Return (rows scanned, list of kept rows)."""
    # one awk pass: count every row (to stderr) and print date, collection, website, link for rows whose
    # link contains any event word (case-insensitive); only the link field is tested
    if stream == "gdelt2_gkg":
        test, out = "tolower($5)", '$2 "\\t" $3 "\\t" $4 "\\t" $5'
    elif stream == "gdelt1_gkg_daily":
        test, out = "tolower($11)", '$1 "\\t" $11'
    else:
        test, out = "tolower($NF)", '$(NF-1) "\\t" $NF'
    prog = f'END{{print NR > "/dev/stderr"}} {test} ~ re {{print {out}}}'
    # pigz reads GDELT's one-file zips with about a third less CPU than unzip (same bytes out)
    cmd = f"set -o pipefail; pigz -dc '{path}' | LC_ALL=C mawk -F'\\t' -v re='{PREFILTER}' '{prog}'"
    p = subprocess.run(["bash", "-c", cmd], capture_output=True)
    if p.returncode != 0:  # GDELT sometimes publishes an empty (stored) zip entry that pigz cannot read
        p = subprocess.run(["bash", "-c", cmd.replace("pigz -dc", "unzip -p")], capture_output=True, check=True)
    scanned = int(p.stderr.decode().strip().splitlines()[-1])
    kept = []
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        f = line.split("\t")
        if stream == "gdelt2_gkg":
            if len(f) < 4:
                continue
            date, coll, site, urls = f[0], f[1], f[2], [f[3]]
        else:
            if len(f) < 2:
                continue
            date, coll, site, urls = f[0], "", "", f[1].split("<UDIV>")
        for u in urls:
            u = u.strip()
            if not u:
                continue
            s = site or re.sub(r"^[a-z]+://(www\.)?", "", u.lower()).split("/", 1)[0]
            j = judge(u, s)
            if j:
                kept.append((date, coll, s, u, j))
    return scanned, kept


def done_set(stream):
    f = OUT / f"done_{stream}.tsv"
    return {l.split("\t", 1)[0] for l in f.read_text().splitlines()[1:]} if f.exists() else set()


def write_result(stream, url, info, scanned, kept):
    with LOCK:
        for row in kept:
            month = re.sub(r"\D", "", row[0])[:6] or "unknown"
            h = OUT / "hits" / stream / f"{month}.tsv"
            h.parent.mkdir(parents=True, exist_ok=True)
            new = not h.exists()
            with open(h, "a") as g:
                if new:
                    g.write("date\tcollection\twebsite\tlink\trules\tfile\n")
                g.write("\t".join(x.replace("\t", " ") for x in row) + "\t" + url.rsplit("/", 1)[-1] + "\n")
        d = OUT / f"done_{stream}.tsv"
        new = not d.exists()
        with open(d, "a") as g:
            if new:
                g.write("url\tbytes\tmd5\tsha256\trows_scanned\trows_kept\tutc\n")
            g.write(f"{url}\t{info['bytes']}\t{info['md5']}\t{info['sha256']}\t{scanned}\t{len(kept)}\t"
                    f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%S}\n")


def work(stream, url, size=None, md5=None):
    """Process one file; a file that keeps failing is recorded in failed_<stream>.tsv and retried next run."""
    try:
        path, info = fetch(url, size)
        if path is None:
            return url, 0, 0, "missing (404)"
        try:
            if md5 and info["md5"] != md5:
                raise RuntimeError(f"MD5 {info['md5']} != listed {md5}")
            scanned, kept = scan(path, stream)
        finally:
            os.unlink(path)
    except Exception as e:  # keep going; the run summary lists failures
        with LOCK, open(OUT / f"failed_{stream}.tsv", "a") as g:
            g.write(f"{url}\t{type(e).__name__}: {str(e)[:150]}\t{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%S}\n")
        return url, 0, 0, f"FAILED {type(e).__name__}"
    write_result(stream, url, info, scanned, kept)
    return url, scanned, len(kept), "ok"


def file_list(stream):
    if stream == "gdelt2_gkg":
        ml = fx.download("gdelt", BASE + "gdeltv2/masterfilelist.txt", f"masterfilelist_{dt.date.today()}.txt",
                         timeout=900)
        out = []
        for line in ml.read_text().splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[2].endswith(".gkg.csv.zip"):
                out.append((parts[2].replace("http://", "https://"), int(parts[0]), parts[1]))
        return out
    days, d = [], dt.date(2013, 4, 1)
    while d <= dt.date(2015, 2, 18):
        days.append(d)
        d += dt.timedelta(days=1)
    if stream == "gdelt1_gkg_daily":
        return [(f"{BASE}gkg/{d:%Y%m%d}.gkg.csv.zip", None, None) for d in days]
    return [(f"{BASE}events/{d:%Y%m%d}.export.CSV.zip", None, None) for d in days]


def run(stream, workers):
    files = file_list(stream)
    have = done_set(stream)
    todo = [f for f in files if f[0] not in have]
    log(f"{stream}: {len(files)} files listed, {len(todo)} to do, {workers} connections")
    t0, n, kept_total, gb = time.time(), 0, 0, 0.0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(work, stream, *f): f for f in todo}
        for fut in as_completed(futs):
            url, scanned, kept, status = fut.result()
            n += 1
            kept_total += kept
            gb += (futs[fut][1] or 0) / 1e9
            if status != "ok":
                log(f"  {url}: {status}")
            if n % 500 == 0:
                rate = n / (time.time() - t0)
                log(f"  {stream}: {n}/{len(todo)} files, {kept_total} rows kept, {gb:.1f} GB, "
                    f"{rate:.2f} files/s, about {(len(todo) - n) / rate / 3600:.1f} h left")
    bad = OUT / f"failed_{stream}.tsv"
    log(f"{stream}: finished, {kept_total} rows kept from {n} files; failures this run are in {bad.name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    workers = 3
    if "--workers" in args:
        i = args.index("--workers")
        workers = int(args[i + 1])
        del args[i:i + 2]
    OUT.mkdir(parents=True, exist_ok=True)
    for stream in args or ["gdelt1_gkg_daily", "gdelt1_events_daily", "gdelt2_gkg"]:
        run(stream, workers)
