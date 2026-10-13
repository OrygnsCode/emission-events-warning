"""Download raw hourly TCEQ monitor data for hydrogen sulfide (H2S, parameter 42402).

EPA AQS pre-generated hourly files do not carry H2S, and many TCEQ CAMS H2S monitors are
non-regulatory, so the hourly values come from TCEQ's own public report pages
(https://www.tceq.texas.gov/airquality/monops/data-reports). Three phases, each resumable:

1. discover  "Hourly Air Pollution Data by Pollutant" (daily_average.pl): one page per
             parameter per day with the hourly values for every site that measured it.
             It is fetched for sample days (default the 15th of each month) to find
             which CAMS sites ran an H2S monitor and roughly when. These pages are kept,
             since they are hourly H2S data for those days.
2. inventory "Yearly Summary Report" form (yearly_summary.pl) per site and year. The form
             lists every parameter the site measured that year with its start and end
             month, which gives the exact H2S months and the list of other parameters.
3. data      "Monthly Summary Report", comma-delimited (monthly_summary.pl): one page per
             site per month with the hourly values (24 columns per day, flags such as
             CAL/SPN/PMA in place of values) for H2S and for every other parameter the
             site measured that month (SO2, wind, temperature, and so on).

All times in the reports are local standard time (no daylight saving shift). Recent
months can still change when TCEQ validates them; months not yet finished are skipped.

Every page is stored gzip-compressed under data/external/tceq_monitors/ and recorded in
data/external/MANIFEST.jsonl (URL, bytes, SHA-256) by fetch_external.download, which skips
pages already recorded. One connection, at most one request per second.

Usage:
  python3 src/fetch_tceq_monitors.py                       # all phases, 1996 to last month
  python3 src/fetch_tceq_monitors.py --phase discover      # only find the sites
  python3 src/fetch_tceq_monitors.py --plan                # inventory, then count data pages
  python3 src/fetch_tceq_monitors.py --start 2015-07 --end 2015-07 --sites 147 --max-requests 10
"""
import argparse
import csv
import datetime as dt
import gzip
import html
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_external as fx  # noqa: E402

SOURCE = "tceq_monitors"
OUT = fx.EXT / SOURCE
CGI = "https://www.tceq.texas.gov/cgi-bin/compliance/monops/"
MIN_GAP = 1.0      # seconds between request starts
FIRST_YEAR = 1996  # earliest year the TCEQ report pages offer
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


INV_NAME = "inventory_site_years.csv"


class Budget(Exception):
    pass


_last = [0.0]
_count = [0]
_max = [None]
_workers = [1]
_lock = threading.Lock()
_tls = threading.local()


def session():
    """One session per thread, so form cookies never leak between parallel requests."""
    if not hasattr(_tls, "s"):
        import requests
        _tls.s = requests.Session()
        _tls.s.headers["User-Agent"] = fx.UA
    return _tls.s


def url_for(script, params):
    return CGI + script + "?" + urlencode(params, quote_via=quote, safe="")


def fetch(url, name):
    """Polite wrapper: skip if already recorded, otherwise wait so requests are >= 1 s apart."""
    dest = OUT / (name + ".gz")
    if url in fx.done_urls() and dest.exists():
        return dest
    with _lock:
        if _max[0] is not None and _count[0] >= _max[0]:
            raise Budget()
        if _workers[0] == 1:
            wait = _last[0] + MIN_GAP - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.monotonic()
        _count[0] += 1
        n = _count[0]
    s = session()
    path = fx.download(SOURCE, url, name, gz=True, quiet=True, session=s)
    _last[0] = time.monotonic()  # retries inside download sleep on their own; restart the gap after
    s.cookies.clear()  # the site remembers form choices in a cookie; keep every request self-contained
    if n % 50 == 0 or not path:
        fx.log(f"{'ok' if path else 'FAILED'} [{n}] {name}")
    return path


def pmap(fn, items):
    """Run fn over items with the configured number of parallel workers; results in input order."""
    if _workers[0] == 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(_workers[0]) as ex:
        return list(ex.map(fn, items))


def read(path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        return f.read()


def ym_range(start, end):
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def last_full_month():
    t = dt.date.today().replace(day=1) - dt.timedelta(days=1)
    return t.year, t.month


# ---------- site list ----------

def site_options():
    """CAMS -> 'site|NAME|AQS|CAMS' option values from the monthly summary form (one request)."""
    p = fetch(CGI + "monthly_summary.pl", "forms/monthly_summary_form.html")
    if not p:
        sys.exit("could not fetch the monthly summary form (site list)")
    opts = re.findall(r"<option value='(site\|[^']*)'", read(p))
    by_cams = {}
    for o in (html.unescape(x) for x in opts):
        cams = o.rsplit("|", 1)[-1]
        by_cams.setdefault(cams, o)
    return by_cams


# ---------- phase 1: discover ----------

def discover(params, start, end, days, months):
    """Return {(param, cams): set of (y, m) seen} from the by-pollutant daily pages."""
    seen = {}
    tasks = []
    for param in params:
        for y, m in ym_range(start, end):
            if months and m not in months:
                continue
            for d in days:
                try:
                    day = dt.date(y, m, d)
                except ValueError:
                    continue
                if day < dt.date.today():
                    tasks.append((param, y, m, d, day))

    def one(t):
        param, y, m, d, day = t
        q = [("select_date", "user"), ("user_month", m - 1), ("user_day", d), ("user_year", y),
             ("user_param", param), ("time_format", "24hr"), ("region_crit", "all"),
             ("first_look", "no"), ("highlight_validated", "1")]
        return fetch(url_for("daily_average.pl", q), f"by_parameter/{param}/{param}_{day}.html")

    for (param, y, m, d, day), p in zip(tasks, pmap(one, tasks)):
        if p:
            for cams in sites_on_daily_page(read(p)):
                seen.setdefault((param, cams), set()).add((y, m))
    return seen


def sites_on_daily_page(text):
    i = text.find("<table", text.find("name='user_param'"))
    j = text.find("</table>", i)
    if i < 0 or j < 0:
        return []
    return sorted(set(re.findall(r"fuseaction=report\.view_site&amp;CAMS=(\d+)", text[i:j])), key=int)


# ---------- phase 2: inventory ----------

FORM_LINE = re.compile(r"name='user_param' value='(\d+)'\s*/>\s*([^<]*?)\s*--\s*available\s+"
                       r"(?:from\s+)?(\w{3}) (\d{4}) to (\w{3}) (\d{4})")


def yearly_form(site_opt, cams, year):
    q = [("select_site", site_opt), ("user_year", year), ("first_look", "no"), ("submitted", "0")]
    p = fetch(url_for("yearly_summary.pl", q), f"site_years/{cams}/{cams}_{year}_form.html")
    if not p:
        return None
    out = {}
    for code, label, m0, y0, m1, y1 in FORM_LINE.findall(read(p)):
        out[code] = (html.unescape(label), (int(y0), MONTHS[m0]), (int(y1), MONTHS[m1]))
    return out


def inventory(seen, params, start, end, opts, only_sites):
    """Return rows: one per (site, year) with the target-parameter months and all parameters."""
    rows = []
    by_site = {}
    for (param, cams), yms in seen.items():
        by_site.setdefault(cams, set()).update(y for y, _ in yms)
    for cams in sorted(by_site, key=int):
        if only_sites and cams not in only_sites:
            continue
        opt = opts.get(cams)
        if not opt:
            fx.log(f"CAMS {cams}: not in the site list of the monthly form, skipped")
            continue
        years = by_site[cams]
        lo, hi = max(FIRST_YEAR, start[0], min(years) - 1), min(end[0], max(years) + 1)
        ys = list(range(lo, hi + 1))
        forms = pmap(lambda y: yearly_form(opt, cams, y), ys)
        for y, form in zip(ys, forms):
            if form is None:
                continue
            for param in params:
                if param not in form:
                    continue
                _, a, b = form[param]
                m_lo = max((y, 1), a, start)
                m_hi = min((y, 12), b, end)
                if m_lo > m_hi:
                    continue
                rows.append({"cams": cams, "site": opt, "year": y, "param": param,
                             "first": m_lo, "last": m_hi, "form": form})
    return rows


def write_inventory(rows):
    path = OUT / INV_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cams", "site_name", "aqs_site", "year", "param", "first_month", "last_month",
                    "n_params_that_year", "param_codes_that_year"])
        for r in rows:
            _, name, aqs, _ = r["site"].split("|")
            w.writerow([r["cams"], name, aqs, r["year"], r["param"], "%d-%02d" % r["first"],
                        "%d-%02d" % r["last"], len(r["form"]), " ".join(sorted(r["form"]))])
    fx.log(f"inventory written: {path} ({len(rows)} site-years)")


# ---------- phase 3: monthly hourly data ----------

def month_jobs(rows):
    """(cams, site option, y, m, include codes) for every site-month with the target parameter."""
    jobs = {}
    for r in rows:
        for y, m in ym_range(r["first"], r["last"]):
            codes = sorted(c for c, (_, a, b) in r["form"].items() if a <= (y, m) <= b)
            key = (r["cams"], y, m)
            if key in jobs:
                codes = sorted(set(codes) | set(jobs[key][4]))
            jobs[key] = (r["cams"], r["site"], y, m, codes)
    return [jobs[k] for k in sorted(jobs, key=lambda k: (int(k[0]), k[1], k[2]))]


def monthly(job):
    cams, opt, y, m, codes = job
    q = [("select_site", opt), ("user_month", m - 1), ("user_year", y), ("first_look", "no"),
         ("submitted", "1"), ("report_format", "comma"), ("time_format", "24hr")]
    q += [(f"include{c}", "1") for c in codes]
    return fetch(url_for("monthly_summary.pl", q), f"monthly/{cams}/{cams}_{y}-{m:02d}.html")


def parse_ym(s):
    y, m = s.split("-")
    return int(y), int(m)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--params", default="42402", help="comma list of parameter codes to find sites for")
    ap.add_argument("--start", default=f"{FIRST_YEAR}-01", help="first month, YYYY-MM")
    ap.add_argument("--end", default=None, help="last month, YYYY-MM (default: last finished month)")
    ap.add_argument("--sites", default="", help="comma list of CAMS numbers to limit phases 2 and 3")
    ap.add_argument("--discover-days", default="15", help="days of the month sampled in phase 1")
    ap.add_argument("--discover-months", default="", help="limit phase 1 to these months, e.g. 1,7")
    ap.add_argument("--phase", choices=["discover", "inventory", "data", "all"], default="all")
    ap.add_argument("--plan", action="store_true", help="run phases 1 and 2, then only count phase 3 pages")
    ap.add_argument("--max-requests", type=int, default=None, help="stop after this many network requests")
    ap.add_argument("--workers", type=int, default=1, help="parallel connections (1 = one request per second)")
    ap.add_argument("--inventory-file", default="inventory_site_years.csv", help="name of the inventory CSV")
    a = ap.parse_args()

    params = [p.strip() for p in a.params.split(",") if p.strip()]
    start = parse_ym(a.start)
    end = parse_ym(a.end) if a.end else last_full_month()
    end = min(end, last_full_month())
    only = {s.strip().lstrip("0") for s in a.sites.split(",") if s.strip()}
    days = [int(d) for d in a.discover_days.split(",")]
    months = {int(m) for m in a.discover_months.split(",") if m.strip()}
    _max[0] = a.max_requests
    _workers[0] = max(1, a.workers)
    global INV_NAME
    INV_NAME = a.inventory_file
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        seen = discover(params, start, end, days, months)
        n_sites = len({c for _, c in seen})
        fx.log(f"phase 1: {n_sites} sites seen measuring {','.join(params)}")
        for (param, cams), yms in sorted(seen.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
            ys = sorted({y for y, _ in yms})
            fx.log(f"  {param} CAMS {cams}: seen in {len(yms)} sampled months, years {ys[0]}-{ys[-1]}")
        if a.phase == "discover":
            return
        rows = inventory(seen, params, start, end, site_options(), only)
        write_inventory(rows)
        jobs = month_jobs(rows)
        fx.log(f"phase 2: {len({r['cams'] for r in rows})} sites, {len(jobs)} site-months to fetch")
        if a.phase == "inventory" or a.plan:
            todo = sum(1 for j in jobs if not (OUT / f"monthly/{j[0]}/{j[0]}_{j[2]}-{j[3]:02d}.html.gz").exists())
            fx.log(f"plan: {todo} monthly pages not yet downloaded (about {todo * 1.6 / 3600:.1f} h at ~1.6 s each)")
            return
        pmap(monthly, jobs)
    except Budget:
        fx.log(f"stopped: reached --max-requests {a.max_requests}")
    finally:
        fx.log(f"{_count[0]} network requests in {time.monotonic() - t0:.0f} s")


if __name__ == "__main__":
    main()
