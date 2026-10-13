"""Download TCEQ AutoGC hourly benzene and 1,3-butadiene, 2003 to 2021 (plan D6 item 4).

Source: TCEQ "AutoGC Monthly Summary Report" (www.tceq.texas.gov/cgi-bin/compliance/monops/agc_monthly_summary.pl,
allowed by the site's robots file, no crawl delay set). One POST per site and month, comma format, parts per billion
by volume, with benzene (45201), 1,3-butadiene (43218) and the site's resultant wind speed and direction (61103,
61104). Times on the page are local standard time. The site list is the 45 AutoGC sites on the form. TCEQ's newer
AQNet service only holds AutoGC data from October 2022, and the TAMIS system disallows robots, so neither is used.

Saved: data/external/tceq_monitors/agc/<site>/<site>_<YYYY>-<MM>.html.gz, each recorded in MANIFEST.jsonl with the
request as its URL key (POST body appended after '#').
Usage: python3 src/fetch_tceq_agc.py [--workers 6]
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_external as fx  # noqa: E402

URL = "https://www.tceq.texas.gov/cgi-bin/compliance/monops/agc_monthly_summary.pl"
OUT = fx.EXT / "tceq_monitors" / "agc"
CODES = ["45201", "43218", "61103", "61104"]
_tls = threading.local()
_lock = threading.Lock()


def sess():
    if not hasattr(_tls, "s"):
        _tls.s = requests.Session()
        _tls.s.headers["User-Agent"] = fx.UA
    return _tls.s


def sites():
    r = sess().get(URL, timeout=60)
    (OUT / "form.html.gz").parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT / "form.html.gz", "wt") as f:
        f.write(r.text)
    return re.findall(r"<option value='(48_\d{3}_\d{4})'", r.text)


def job(site, y, m):
    data = {"user_site": site, "user_month": str(m - 1), "user_year": str(y), "user_units": "ppb-v",
            "report_format": "comma", **{f"include{c}": "1" for c in CODES}}
    key = URL + "#" + urlencode(sorted(data.items()))
    dest = OUT / site / f"{site}_{y}-{m:02d}.html.gz"
    if key in fx.done_urls() and dest.exists():
        return "have"
    for attempt in range(1, 6):
        try:
            r = sess().post(URL, data=data, timeout=120)
            if r.status_code != 200:
                raise RuntimeError(f"http {r.status_code}")
            body = r.content
            dest.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(dest, "wb") as f:
                f.write(body)
            rec = {"source": "tceq_monitors", "url": key, "file": f"tceq_monitors/agc/{site}/{dest.name}",
                   "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "stored": "gzip",
                   "last_modified": r.headers.get("Last-Modified"),
                   "downloaded_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
            with _lock:
                with open(fx.MANIFEST, "a") as mf:
                    mf.write(json.dumps(rec) + "\n")
                fx.done_urls().add(key)
            return "ok"
        except Exception as e:  # noqa: BLE001
            fx.log(f"retry {attempt} {site} {y}-{m:02d}: {e}")
    return "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    S = sites()
    fx.log(f"AutoGC sites on the form: {len(S)}")
    jobs = [(s, y, m) for s in S for y in range(2003, 2022) for m in range(1, 13)]
    done = {"ok": 0, "have": 0, "failed": 0}
    with ThreadPoolExecutor(a.workers) as ex:
        for i, res in enumerate(ex.map(lambda j: job(*j), jobs), 1):
            done[res] += 1
            if i % 500 == 0:
                fx.log(f"{i}/{len(jobs)} {done}")
    fx.log(f"finished {done}")


if __name__ == "__main__":
    main()
