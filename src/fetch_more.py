"""Second round of outside data (plan Deviation D1), with a hash for every file.

Every file is recorded in data/external/MANIFEST.jsonl (URL, bytes, SHA-256 of the bytes as served,
time). Text files are stored gzip-compressed. National files that are only needed for Texas are cut
down to Texas right after download (rule written in data/slices/SLICES.jsonl with the slice's own
hash), and the national copy is then deleted to save disk; its hash stays in the manifest, so anyone
can download it again and check it is the same file.

Jobs run one host at a time and one request at a time per host, so no site sees more than one
connection from us. Different jobs (different hosts) can run in parallel.

Usage: python3 src/fetch_more.py JOB [JOB ...]      (see JOBS at the bottom)
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_external as fx  # noqa: E402
from fetch_external import EXT, S, download, log  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SLICES = ROOT / "data" / "slices"
TX_BOX = (-107.2, 25.4, -93.0, 36.9)  # lon/lat box around Texas with a small margin
csv.field_size_limit(1 << 30)


def links(url, pattern, **kw):
    """All hrefs on a page that match pattern, made absolute, in page order, no repeats."""
    r = S.get(url, timeout=60, **kw)
    r.raise_for_status()
    out = []
    for h in re.findall(r'href=["\']([^"\']+)["\']', r.text, re.I):
        a = urljoin(r.url, h)
        if re.search(pattern, a, re.I) and a not in out:
            out.append(a)
    return out


def record_slice(path, rows, sources, rule):
    rec = {"slice": str(path.relative_to(SLICES)), "rows": rows, "bytes": path.stat().st_size,
           "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "sources": sources, "rule": rule,
           "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(SLICES / "SLICES.jsonl", "a") as m:
        m.write(json.dumps(rec) + "\n")
    log(f"slice {rec['slice']}: {rows} rows, {rec['bytes'] / 1e6:.1f} MB")


def slice_done(rel):
    f = SLICES / "SLICES.jsonl"
    return f.exists() and any(json.loads(l)["slice"] == rel for l in f.read_text().splitlines() if l.strip())


def grep_zip_slice(zpath, rel, regex, url, rule):
    """Keep the header plus every line matching regex (C-speed awk), gzip it, record it."""
    out = SLICES / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    cnt = out.with_suffix(".count")
    cmd = (f"set -o pipefail; unzip -p '{zpath}' | LC_ALL=C awk 'NR==1 || /{regex}/' "
           f"| tee >(wc -l > '{cnt}') | pigz -6 > '{out}.part'")
    subprocess.run(["bash", "-c", cmd], check=True)
    time.sleep(0.5)
    rows = int(cnt.read_text().strip() or 1) - 1
    cnt.unlink()
    Path(f"{out}.part").rename(out)
    record_slice(out, rows, [url], rule)


def box_filter_csv(src_open, rel, url, latcol, loncol, rule, box=TX_BOX):
    """Stream a CSV and keep rows whose lat/lon fall in the Texas box."""
    out = SLICES / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with src_open() as f, gzip.open(f"{out}.part", "wt", newline="") as g:
        rd = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline=""))
        w = csv.writer(g, lineterminator="\n")
        head = next(rd)
        w.writerow(head)
        la, lo = head.index(latcol), head.index(loncol)
        for r in rd:
            try:
                y, x = float(r[la]), float(r[lo])
            except (ValueError, IndexError):
                continue
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                w.writerow(r)
                rows += 1
    Path(f"{out}.part").rename(out)
    record_slice(out, rows, [url], rule)


# ------------------------------------------------------------------ air monitors and weather
AQS = "https://aqs.epa.gov/aqsweb/airdata/"
AQS_HOURLY = r"hourly_(42401|44201|42602|42101|88101|88502|81102|86101|WIND|TEMP|PRESS|RH_DP|HAPS|VOCS|NONOxNOy|SPEC|PM10SPEC|LEAD)_\d{4}\.zip$"
AQS_OTHER = r"(daily_(HAPS|VOCS|SPEC|PM10SPEC|LEAD|NONOxNOy)_\d{4}\.zip|annual_conc_by_monitor_\d{4}\.zip|aqs_(sites|monitors)\.zip)$"


def aqs():
    page = AQS + "download_files.html"
    files = links(page, AQS_HOURLY) + links(page, AQS_OTHER)
    log(f"AQS: {len(files)} files listed")
    download("epa_aqs", page, "download_files.html")
    for url in files:
        name = url.rsplit("/", 1)[-1]
        rel = f"epa_aqs/{name[:-4]}_tx.csv.gz"
        if name.startswith("aqs_"):
            download("epa_aqs", url)
            continue
        if slice_done(rel):
            continue
        p = download("epa_aqs", url)
        if p is None:
            continue
        grep_zip_slice(p, rel, r'^"48",', url, 'State Code == "48" (Texas)')
        p.unlink()


def iem():
    gj = download("iem_asos", "https://mesonet.agron.iastate.edu/geojson/network/TX_ASOS.geojson")
    stations = json.loads(gj.read_text())["features"]
    log(f"IEM: {len(stations)} Texas ASOS stations")
    end = "2026-10-01T00:00:00Z"
    for f in stations:
        sid = f["id"]
        begin = (f["properties"].get("archive_begin") or "1928-01-01")[:10]
        params = [("station", sid), ("data", "all"), ("sts", begin + "T00:00:00Z"), ("ets", end),
                  ("tz", "Etc/UTC"), ("format", "onlycomma"), ("latlon", "yes"), ("elev", "yes"),
                  ("missing", "M"), ("trace", "T"), ("direct", "yes"), ("report_type", "3"), ("report_type", "4")]
        url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
        key = url + "?" + "&".join(f"{k}={v}" for k, v in params)
        if key in fx.done_urls():
            continue
        download("iem_asos", url, f"{sid}.csv", gz=True, params=params, key=key, timeout=900)
        time.sleep(2)  # IEM asks for no concurrent requests; leave a gap


def ghcn():
    base = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/"
    for n in ("ghcnd-stations.txt", "ghcnd-inventory.txt", "readme.txt", "ghcnd-version.txt"):
        download("noaa_ghcn", base + n)
    ids = [l[:11] for l in (EXT / "noaa_ghcn/ghcnd-stations.txt").read_text().splitlines()
           if l[38:40] == "TX" and l.startswith("US")]
    log(f"GHCN: {len(ids)} Texas stations")
    acc = "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/"
    for i, sid in enumerate(ids, 1):
        download("noaa_ghcn", acc + sid + ".csv", f"stations/{sid}.csv", gz=True, quiet=True)
        if i % 500 == 0:
            log(f"  GHCN {i}/{len(ids)}")


def noaa_misc():
    hd = links("https://www.nhc.noaa.gov/data/hurdat/", r"hurdat2-1851-\d{4}-\d+\.txt$|hurdat2-format.*\.pdf$")
    for u in hd:
        download("noaa_hurdat", u)
    base = "https://www.ncei.noaa.gov/pub/data/swdi/database-csv/v2/"
    for u in links(base, r"nldn-tiles-\d{4}(\d{2})?\.csv\.gz$"):
        name = u.rsplit("/", 1)[-1]
        rel = f"noaa_nldn/{name[:-7]}_tx.csv.gz"
        if slice_done(rel):
            continue
        p = download("noaa_nldn", u)
        if p is None:
            continue
        if b"ZDAY" not in _skip_comments(p).read(4096):
            # NOAA's own file is not lightning data (the 1986 file holds a directory listing); keep it as evidence
            log(f"WARNING: {name} on the NOAA server is not lightning data; kept as served, no slice made")
            continue
        box_filter_csv(lambda: _skip_comments(p), rel, u, "CENTERLAT", "CENTERLON", "cell centre inside Texas box")
        p.unlink()
    download("fema", "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries.csv",
             "DisasterDeclarationsSummaries.csv", gz=True)


def _skip_comments(p):
    """NLDN tile files start with '#' comment lines; the header itself is the comment '#ZDAY,...'."""
    raw = open(p, "rb").read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    lines = [l[1:] if l.startswith(b"#ZDAY") else l for l in raw.split(b"\n")
             if l.startswith(b"#ZDAY") or not l.startswith(b"#")]
    return io.BytesIO(b"\n".join(lines))


# ------------------------------------------------------------------ industry activity and plant size
def eia():
    xls = ["https://www.eia.gov/dnav/pet/xls/PET_PNP_WIUP_DCU_R30_W.xls",
           "https://www.eia.gov/dnav/pet/xls/PET_PNP_WIUP_DCU_NUS_W.xls",
           "https://www.eia.gov/dnav/pet/xls/PET_PNP_UNC_DCU_R30_M.xls",
           "https://www.eia.gov/dnav/pet/xls/PET_PNP_UNC_DCU_R3A_M.xls",
           "https://www.eia.gov/dnav/pet/xls/PET_PNP_UNC_DCU_R3B_M.xls",
           "https://www.eia.gov/dnav/pet/xls/PET_PNP_UNC_DCU_NUS_M.xls",
           "https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_D.xls",
           "https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_W.xls",
           "https://www.eia.gov/dnav/ng/hist_xls/RNGWHHDd.xls"]
    for u in xls:
        download("eia", u, f"series/{u.rsplit('/', 1)[-1]}")
    for n in ("manifest.txt", "PET.zip", "NG.zip", "TOTAL.zip", "ELEC.zip", "STEO.zip"):
        download("eia", "https://www.eia.gov/opendata/bulk/" + n, f"bulk/{n}")
    rc = "https://www.eia.gov/petroleum/refinerycapacity/"
    download("eia", rc + "refcap26.xlsx", "refcap/refcap26.xlsx")
    download("eia", rc + "table13.pdf", "refcap/table13.pdf")
    for y in range(1982, 2026):
        for ext in ("xls", "xlsx"):
            if download("eia", f"{rc}archive/{y}/refcap{y % 100:02d}.{ext}", f"refcap/refcap{y}.{ext}", quiet=True):
                break
    e860 = "https://www.eia.gov/electricity/data/eia860/"
    for u in [e860 + "xls/eia8602025.zip", e860 + "xls/eia8602025ER.zip"] + \
             [f"{e860}archive/xls/eia860{y}.zip" for y in range(2001, 2025)] + \
             [f"{e860}eia860a/eia860a{y}.zip" for y in range(1990, 2001)] + \
             [f"{e860}eia860b/eia860b{y}.zip" for y in range(1998, 2001)]:
        download("eia", u, f"eia860/{u.rsplit('/', 1)[-1]}", quiet=True)
    e923 = "https://www.eia.gov/electricity/data/eia923/"
    for u in [e923 + "xls/f923_2025.zip", e923 + "xls/f923_2026.zip"] + \
             [f"{e923}archive/xls/f923_{y}.zip" for y in range(2008, 2025)] + \
             [f"{e923}archive/xls/f906920_{y}.zip" for y in range(2001, 2008)] + \
             [f"{e923}archive/xls/f906nonutil{y}.zip" for y in (1989, 1999, 2000)]:
        download("eia", u, f"eia923/{u.rsplit('/', 1)[-1]}", quiet=True)
    for u in links("https://www.eia.gov/electricity/data/disturbance/disturb_events_archive.html", r"\.(xlsx?|pdf)$"):
        download("eia", u, f"oe417/{u.rsplit('/', 1)[-1]}")
    download("ornl_oe417", "https://openenergyhub.ornl.gov/api/explore/v2.1/catalog/datasets/"
             "oe-417-annual-summaries/exports/csv", "oe417_annual_summaries.csv", gz=True)
    # FRED (fred.stlouisfed.org) is refused by the proxy from this machine, so the same Federal Reserve Board
    # G.17 series are taken from the Board's own files (index, capacity), which hold every series FRED republishes
    for n in ("ip_sa.txt", "ip_nsa.txt", "cap_sa.txt"):
        download("fed_g17", f"https://www.federalreserve.gov/releases/g17/ipdisk/{n}", n)
    download("fed_g17", "https://www.federalreserve.gov/releases/g17/data/FRB_g17_xml.zip", "FRB_g17_xml.zip")
    log("EIA files whose names were tried but do not exist are logged as FAILED 404 above; that is expected")


def campd():
    b = "https://api.epa.gov/easey/bulk-files/"
    for y in range(1995, 2027):
        download("epa_campd", f"{b}facility/facility-{y}.csv", f"facility/facility-{y}.csv", gz=True, quiet=True)
        download("epa_campd", f"{b}emissions/daily/state/emissions-daily-{y}-tx.csv", f"daily/emissions-daily-{y}-tx.csv",
                 gz=True, quiet=True)
        download("epa_campd", f"{b}emissions/hourly/state/emissions-hourly-{y}-tx.csv",
                 f"hourly/emissions-hourly-{y}-tx.csv", gz=True, timeout=600)


def hifld():
    terms = ["petroleum refineries", "natural gas processing plants", "power plants", "risk management plan",
             "toxic release inventory", "ethanol plants", "liquefied natural gas", "petroleum terminals",
             "natural gas compressor stations", "chemical", "frs naics", "hazardous gas liquids pipelines",
             "crude oil pipelines", "petroleum products pipelines", "natural gas pipelines",
             "oil and natural gas platforms", "ports", "fire stations", "hospitals", "salt caverns",
             "strategic petroleum reserves", "petroleum product terminals", "biodiesel plants",
             "natural gas storage", "electric substations", "hazardous waste"]
    seen = set()
    for t in terms:
        r = S.get("https://hifld.publicenvirodata.org/api/datasets", params={"search": t}, timeout=60)
        if r.status_code != 200:
            log(f"HIFLD search '{t}': HTTP {r.status_code}")
            continue
        for d in r.json().get("datasets", []):
            self_href = next((l["href"] for l in d["links"] if l["rel"] == "self"), None)
            if not self_href or d["id"] in seen:
                continue
            seen.add(d["id"])
            for coll in _stac_collections(self_href):
                assets = S.get(coll, timeout=60).json().get("assets", {})
                for a in assets.values():
                    h = a["href"]
                    if h.endswith(".parquet"):
                        download("hifld_next", h, "/".join(h.split("/")[-4:]).replace("/", "__"))
            time.sleep(1)
    log(f"HIFLD: {len(seen)} datasets matched")
    download("eia_atlas", "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Power_Plants_in_the_US/"
             "FeatureServer/0/query?where=State%3D%27Texas%27&outFields=*&f=geojson", "power_plants_tx.geojson")


def _stac_collections(cat_url, depth=0):
    if depth > 4:
        return []
    d = S.get(cat_url, timeout=60).json()
    out = []
    latest = [l["href"] for l in d.get("links", []) if l["rel"] == "latest-version"]
    if latest:
        return latest
    if d.get("type") == "Collection":
        return [cat_url]
    for l in d.get("links", []):
        if l["rel"] == "child" and l["href"] not in out:
            out += _stac_collections(l["href"], depth + 1)
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------ satellite heat and flares
def firms():
    base = "https://firms.modaps.eosdis.nasa.gov/data/country/"
    for prod, years in (("modis", range(2000, 2026)), ("viirs-snpp", range(2012, 2026)),
                        ("viirs-jpss1", range(2018, 2026)), ("viirs-jpss2", range(2023, 2026))):
        for y in years:
            name = f"{prod}_{y}_United_States.csv"
            rel = f"nasa_firms/{prod}_{y}_tx.csv.gz"
            if slice_done(rel):
                continue
            url = f"{base}{prod}/{y}/{name}"
            p = download("nasa_firms", url, quiet=True)
            if p is None:
                continue
            box_filter_csv(lambda: open(p, "rb"), rel, url, "latitude", "longitude", "detection inside Texas box")
            p.unlink()
    for u in links("https://eogdata.mines.edu/products/vnf/global_gas_flare.html", r"\.(xlsx?|csv|pdf|zip)$"):
        download("eog_flares", u)
    download("worldbank_flares", "https://thedocs.worldbank.org/en/doc/b34e0c054bb3fe3695e70154c28eef3f-0400072026/"
             "related/Flare-Volume-Estimates-by-individual-Flare-Location-2012-2025.xlsx")


# ------------------------------------------------------------------ safety records
OSHA_TABLES = ["inspection", "violation", "violation_event", "violation_gen_duty_std", "accident", "accident_injury",
               "accident_abstract", "related_activity", "emphasis_codes", "optional_code_info", "accident_lookup2"]


def osha():
    sir = links("https://www.osha.gov/severe-injury-reports", r"\.(zip|csv|xlsx)$")
    for u in sir:
        download("osha", u, f"severe_injury/{u.rsplit('/', 1)[-1]}")
    for t in OSHA_TABLES:
        download("osha", f"https://data.dol.gov/data-catalog/OSHA/{t}/OSHA_{t}.zip", f"enforcement/OSHA_{t}.zip",
                 timeout=900)
    osha_slice()


def _zip_rows(zpath):
    """Yield (header, row) from every CSV member of a zip, checking all members share one header."""
    head0 = None
    with zipfile.ZipFile(zpath) as z:
        for m in sorted(z.namelist()):
            if not m.lower().endswith(".csv"):
                continue
            with z.open(m) as f:
                rd = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline=""))
                head = next(rd, None)
                if head is None:
                    continue
                if head0 is None:
                    head0 = head
                elif head != head0:
                    raise RuntimeError(f"{zpath.name}: member {m} has a different header")
                for r in rd:
                    yield head0, r


def _filter_zip(zpath, rel, keep, url, rule):
    out = SLICES / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, head_written = 0, False
    with gzip.open(f"{out}.part", "wt", newline="") as g:
        w = csv.writer(g, lineterminator="\n")
        for head, r in _zip_rows(zpath):
            if not head_written:
                w.writerow(head)
                head_written = True
                idx = {c: i for i, c in enumerate(head)}
            if keep(idx, r):
                w.writerow(r)
                rows += 1
    Path(f"{out}.part").rename(out)
    record_slice(out, rows, [url], rule)


def osha_slice():
    d = EXT / "osha/enforcement"
    u = "https://data.dol.gov/data-catalog/OSHA/{t}/OSHA_{t}.zip"
    tx = set()

    def insp(idx, r):
        if r[idx["SITE_STATE"]] == "TX":
            tx.add(r[idx["ACTIVITY_NR"]])
            return True
        return False
    _filter_zip(d / "OSHA_inspection.zip", "osha/inspection_tx.csv.gz", insp, u.format(t="inspection"),
                "SITE_STATE == TX")
    by_act = lambda idx, r: r[idx["ACTIVITY_NR"]] in tx  # noqa: E731
    for t in ("violation", "violation_event", "violation_gen_duty_std", "related_activity", "emphasis_codes",
              "optional_code_info"):
        _filter_zip(d / f"OSHA_{t}.zip", f"osha/{t}_tx.csv.gz", by_act, u.format(t=t),
                    "ACTIVITY_NR in Texas inspections")
    summ = set()

    def inj(idx, r):
        if r[idx["REL_INSP_NR"]] in tx:
            summ.add(r[idx["SUMMARY_NR"]])
            return True
        return False
    _filter_zip(d / "OSHA_accident_injury.zip", "osha/accident_injury_tx.csv.gz", inj, u.format(t="accident_injury"),
                "REL_INSP_NR in Texas inspections")
    by_sum = lambda idx, r: r[idx["SUMMARY_NR"]] in summ  # noqa: E731
    for t in ("accident", "accident_abstract"):
        _filter_zip(d / f"OSHA_{t}.zip", f"osha/{t}_tx.csv.gz", by_sum, u.format(t=t),
                    "SUMMARY_NR linked to a Texas inspection")
    _filter_zip(d / "OSHA_accident_lookup2.zip", "osha/accident_lookup2.csv.gz", lambda i, r: True,
                u.format(t="accident_lookup2"), "whole table (code list)")


def csb():
    seen = []
    for kind in ("completed-investigations", "current-investigations"):
        for pg in range(1, 40):
            url = f"https://www.csb.gov/investigations/{kind}/?pg={pg}"
            p = download("csb", url, f"lists/{kind}_{pg}.html", gz=True, quiet=True)
            time.sleep(1)
            if p is None:
                break
            html = gzip.open(p).read().decode("utf-8", "replace")
            new = [urljoin(url, h) for h in re.findall(r'href="(/[a-z0-9\-]+/)"', html)
                   if not re.match(r"/(investigations|news|about|recommendations|assets|videos|search|"
                                   r"resources|contact|careers|media|foia|safety-videos|newsroom)", h)]
            new = [n for n in new if n not in seen]
            if not new and pg > 1:
                break
            seen += new
    log(f"CSB: {len(seen)} candidate investigation pages")
    for u in seen:
        download("csb", u, "pages/" + u.rstrip("/").rsplit("/", 1)[-1] + ".html", gz=True, quiet=True)
        time.sleep(1)
    for u in links("https://www.csb.gov/news/incident-report-rule-form-/", r"\.(xlsx?|csv)$"):
        download("csb", u, "reporting_rule/" + u.rsplit("/", 1)[-1])


# ------------------------------------------------------------------ Texas and EPA records
TX_OPEN = {"central_registry_coastal_east": "tzyg-j7q4", "central_registry_north": "5eqq-7nad",
           "central_registry_dfw": "t34q-qzi3", "central_registry_central": "msah-s2rv",
           "central_registry_border_permian": "9iad-hrn8", "emergency_response_spills": "xagr-a3x2",
           "agreed_orders": "u66a-qggj", "civil_judgments": "7ift-kbgd", "seps": "8j6x-idf8",
           "compliance_history": "mich-cjem"}


def tceq_more():
    for name, ds in TX_OPEN.items():
        download("tceq_open_data", f"https://data.texas.gov/api/views/{ds}/rows.csv?accessType=DOWNLOAD",
                 f"{name}_{ds}.csv", gz=True, timeout=900)
        download("tceq_open_data", f"https://data.texas.gov/api/views/{ds}.json", f"{name}_{ds}_columns.json")
    for u in links("https://www.tceq.texas.gov/airquality/point-source-ei/point-source-emissions-data",
                   r"^https://www\.tceq\.texas\.gov/downloads/.*\.(xlsx?|pdf|zip|csv)$"):
        download("tceq_psei", u, timeout=900)
    download("tceq_rules", "https://www.tceq.texas.gov/downloads/rules/current/101_his.pdf")
    try:
        for u in links("https://www.tceq.texas.gov/rules/current", r"/downloads/rules/current/.*101.*\.pdf$"):
            download("tceq_rules", u)
    except Exception as e:  # the history PDF above is the key document; the index page has moved before
        log(f"TCEQ rules index not read: {type(e).__name__}: {str(e)[:100]}")
    download("tceq_gis", "https://gisweb.tceq.texas.gov/arcgis/rest/services/Public/AQS_Sites/MapServer/0/query"
             "?where=1%3D1&outFields=*&f=geojson", "aqs_sites_layer0.geojson")
    for u in ("https://www.law.cornell.edu/regulations/texas/30-Tex-Admin-Code-SS-101-201",
              "https://www.law.cornell.edu/regulations/texas/30-Tex-Admin-Code-SS-101-1",
              "https://www.law.cornell.edu/regulations/texas/30-Tex-Admin-Code-SS-101-222",
              "https://texas.public.law/statutes/tex._health_and_safety_code_section_382.0215",
              "https://texas.public.law/statutes/tex._health_and_safety_code_section_382.0216"):
        download("regulatory_text", u, u.rstrip("/").rsplit("/", 1)[-1] + ".html", gz=True)
        time.sleep(1)
    r = S.get("https://www.federalregister.gov/api/v1/documents.json",
              params={"conditions[cfr][title]": "40", "conditions[cfr][part]": "68", "per_page": "1000",
                      "fields[]": ["document_number", "publication_date", "title", "pdf_url", "type", "citation"]},
              timeout=120)
    (EXT / "regulatory_text").mkdir(parents=True, exist_ok=True)
    (EXT / "regulatory_text/fr_40cfr68_index.json").write_text(r.text)
    docs = r.json().get("results", [])
    log(f"Federal Register: {len(docs)} documents touching 40 CFR part 68")
    for d in docs:
        if d.get("pdf_url"):
            download("regulatory_text", d["pdf_url"], f"fr_40cfr68/{d['publication_date']}_{d['document_number']}.pdf",
                     quiet=True)
    download("regulatory_text", "https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-40.xml?part=68",
             "ecfr_40cfr68_2026-10-01.xml", gz=True)
    for u in ("https://environmentalintegrity.org/wp-content/uploads/2017/02/Breakdowns-in-Enforcement-Report.pdf",
              "https://environmentalintegrity.org/wp-content/uploads/2023/03/TX-Polluters-Playbook-final-report-3.23.23.pdf"):
        download("outside_tallies", u)


def echo_more():
    for n in ("case_downloads.zip", "afs_downloads.zip"):
        download("epa_echo", "https://echo.epa.gov/files/echodownloads/" + n, timeout=900)


def houston311():
    for u in links("https://my311.houstontx.gov/servicerequestdata.html", r"/311/.*\.txt"):
        name = u.split("?")[0].rsplit("/", 1)[-1]
        download("houston_311", u.split("?")[0], name, gz=True, timeout=1800)


def census_bls():
    for y in range(1986, 2025):
        download("census_cbp", f"https://www2.census.gov/programs-surveys/cbp/datasets/{y}/cbp{y % 100:02d}co.zip",
                 quiet=True)
    for y in range(1990, 2026):
        url = f"https://data.bls.gov/cew/data/files/{y}/csv/{y}_annual_by_industry.zip"
        rel = f"bls_qcew/{y}_annual_by_industry_tx.csv.gz"
        if slice_done(rel):
            continue
        p = download("bls_qcew", url, headers={"User-Agent": fx.UA}, quiet=True, timeout=900)
        if p is None:
            continue
        grep_zip_slice(p, rel, r'^"48', url, 'area_fips starts with "48" (Texas state and counties)')
        p.unlink()


def osm():
    """Industrial areas and works in Texas from an Overpass mirror, one query per tag."""
    ep = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    queries = {"landuse_industrial": 'nwr["landuse"="industrial"]',
               "man_made_works": 'nwr["man_made"="works"]',
               "industrial_any": 'nwr["industrial"]',
               "man_made_flare": 'nwr["man_made"~"flare|gasometer|storage_tank|chimney|pipeline"]',
               "power_plants": 'nwr["power"~"plant|generator"]["plant:source"]'}
    failed = []
    for name, q in queries.items():
        if not _osm_get(ep, name, q, '(area.a)'):
            failed.append(name)
    for name in failed:
        # whole-state query timed out: ask for 1 x 1 degree tiles instead (overlaps removed later by OSM id)
        log(f"OSM {name}: splitting Texas into 1 degree tiles")
        lo, la, hi, ha = TX_BOX
        for y in range(int(la), int(ha) + 1):
            for x in range(int(lo) - 1, int(hi) + 1):
                if not _osm_get(ep, f"{name}/tile_{y}_{x}", q, f"(area.a)({y},{x},{y + 1},{x + 1})", pause=5):
                    raise RuntimeError(f"OSM tile {name} {y} {x} failed")


def _osm_get(ep, name, q, filt, pause=30):
    body = f'[out:json][timeout:900];area["ISO3166-2"="US-TX"][admin_level=4]->.a;({q}{filt};);out tags center;'
    key = f"{ep}?{name}"
    if key in fx.done_urls():
        return True
    for attempt in range(1, 4):
        try:
            r = S.post(ep, data={"data": body}, timeout=1200)
        except Exception as e:
            log(f"OSM {name}: {type(e).__name__}")
            time.sleep(60)
            continue
        if r.status_code == 200 and r.content.lstrip().startswith(b"{") and b'"remark"' not in r.content[-2000:]:
            break
        log(f"OSM {name}: HTTP {r.status_code} (attempt {attempt}) {r.content[-300:]!r}")
        time.sleep(60 * attempt)
    else:
        return False
    dest = EXT / "osm" / f"{name}.json.gz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dest, "wb") as g:
        g.write(r.content)
    rec = {"source": "osm", "url": key, "query": body, "file": f"osm/{name}.json.gz", "bytes": len(r.content),
           "sha256": hashlib.sha256(r.content).hexdigest(), "stored": "gzip",
           "downloaded_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(fx.MANIFEST, "a") as m:
        m.write(json.dumps(rec) + "\n")
    fx.done_urls().add(key)
    log(f"ok osm/{name} ({len(r.content) / 1e6:.1f} MB)")
    time.sleep(pause)
    return True


JOBS = {"aqs": aqs, "iem": iem, "ghcn": ghcn, "noaa_misc": noaa_misc, "eia": eia, "campd": campd,
        "hifld": hifld, "firms": firms, "osha": osha, "osha_slice": osha_slice, "csb": csb,
        "tceq_more": tceq_more, "echo_more": echo_more, "houston311": houston311, "census_bls": census_bls,
        "osm": osm}

if __name__ == "__main__":
    EXT.mkdir(parents=True, exist_ok=True)
    SLICES.mkdir(parents=True, exist_ok=True)
    failed = []
    for name in sys.argv[1:]:
        log(f"=== {name} ===")
        try:
            JOBS[name]()
            log(f"=== {name} finished ===")
        except Exception as e:
            failed.append(name)
            log(f"=== {name} FAILED: {type(e).__name__}: {e} ===")
    sys.exit(1 if failed else 0)
