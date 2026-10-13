"""Cut a Texas window out of Sentinel-5P TROPOMI SO2 and NO2 Level-2 orbits, 2018 to latest.

Source: the AWS open-data bucket meeo-s5p (https://meeo-s5p.s3.amazonaws.com/, no account).
Its COGT/ tree holds every L2 orbit regridded to a lat/long grid (EPSG:4326, 0.035 degree
cells) as Cloud-Optimized GeoTIFFs, one file per variable ("layer"):

  COGT/{OFFL|RPRO}/L2__SO2___/YYYY/MM/DD/<granule>_PRODUCT_sulfurdioxide_total_vertical_column_4326.tif
  COGT/{OFFL|RPRO}/L2__SO2___/YYYY/MM/DD/<granule>_PRODUCT_qa_value_4326.tif
  COGT/{OFFL|RPRO}/L2__NO2___/.../<granule>_PRODUCT_nitrogendioxide_tropospheric_column_4326.tif
  COGT/{OFFL|RPRO}/L2__NO2___/.../<granule>_PRODUCT_SUPPORT_DATA_DETAILED_RESULTS_nitrogendioxide_summed_total_column_4326.tif
  COGT/{OFFL|RPRO}/L2__NO2___/.../<granule>_PRODUCT_qa_value_4326.tif
  COGT/{OFFL|RPRO}/L2__NO2___/.../<granule>_utctime_4326.tif   (OFFL NO2 only)

Column layers are float32 in mol/m2 (nodata -9999), qa_value is uint8 0..100 (the L2 qa_value
times 100, nodata 255), utctime is uint32 Unix seconds (nodata 0). No scale or offset.

Every orbit file spans the whole globe in longitude (day and night side), so the GeoTIFF bounds
cannot tell which orbits see Texas. Instead: TROPOMI crosses the equator northbound at 13:30
local solar time, so Texas (lon -107 to -93) is seen between about 18:50 and 21:30 UTC. Only
orbits whose start/end times overlap 18:15-22:00 UTC (a wide margin) are opened; their main
layer is read over the Texas box and the orbit is kept only if that window has valid pixels.
That is normally one orbit a day, sometimes two. --all-orbits skips the time filter (to check it).

For each kept orbit, all layers are read over the Texas box (lon -107.2 to -93.0,
lat 25.4 to 36.9) by HTTP range reads, and saved as one compressed .npz under
data/external/tropomi/{SO2,NO2}/YYYY/<granule>.npz with keys:
  <layer name>        2-D array, native dtype (e.g. sulfurdioxide_total_vertical_column, qa_value)
  nodata_<layer name> that layer's nodata value
  geotransform        GDAL order (x0, dx, 0, y0, 0, dy) of the window, EPSG:4326, cell edges
  meta                JSON string: granule, stream, collection, processor, layer URLs, box
Each saved window is recorded in data/external/MANIFEST.jsonl in the same format as
fetch_external.download() (url = the main layer URL; bytes and sha256 are of the saved .npz).
Re-running skips orbits already in the manifest and orbits already found to miss Texas
(data/state/tropomi/no_texas.txt). Month listings older than 60 days are cached in
data/state/tropomi/listings/.

Streams: OFFL is the default; an orbit missing from OFFL is filled from RPRO (OFFL SO2 starts
2018-11, OFFL NO2 starts 2018-06 and lacks 2018-09). NOTE: in this bucket, OFFL before late 2022
is product collection 01 (processor 1.x) while RPRO 2018-2022 is collection 03 (2.4+), which is
the consistent reprocessing. For long-term averages, --prefer rpro gives a more uniform series.

Usage:
  python3 src/fetch_tropomi.py                                  # SO2 and NO2, 2018-04-30 to today
  python3 src/fetch_tropomi.py --start 2019-06-15 --end 2019-06-16 --products SO2
  python3 src/fetch_tropomi.py --prefer rpro --workers 4
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_external import EXT, MANIFEST, ROOT, S, done_urls, log  # noqa: E402

BUCKET = "https://meeo-s5p.s3.amazonaws.com/"
SOURCE = "tropomi"
OUT = EXT / SOURCE
STATE = ROOT / "data" / "state" / "tropomi"
NO_TEXAS = STATE / "no_texas.txt"
LISTINGS = STATE / "listings"

# lon_min, lat_min, lon_max, lat_max
BOX = (-107.2, 25.4, -93.0, 36.9)
# Orbits overlapping this UTC time-of-day range are opened (Texas is seen about 18:50-21:30 UTC).
PASS_UTC = (dt.timedelta(hours=18, minutes=15), dt.timedelta(hours=22))
MAIN_LAYER = {"SO2": "PRODUCT_sulfurdioxide_total_vertical_column",
              "NO2": "PRODUCT_nitrogendioxide_tropospheric_column"}
FIRST_DAY = dt.date(2018, 4, 30)

KEY_RE = re.compile(
    r"^COGT/(?P<stream>OFFL|RPRO)/L2__(?P<prod>SO2|NO2)___/\d{4}/\d\d/\d\d/"
    r"(?P<gran>S5P_(?:OFFL|RPRO)_L2__\w{6}_(?P<start>\d{8}T\d{6})_(?P<end>\d{8}T\d{6})_"
    r"(?P<orbit>\d{5})_(?P<coll>\d\d)_(?P<proc>\d{6})_(?P<ptime>\d{8}T\d{6}))_(?P<layer>.+)_4326\.tif$")

CA = next((p for p in (os.environ.get("CURL_CA_BUNDLE"), os.environ.get("REQUESTS_CA_BUNDLE"))
           if p and os.path.exists(p)), None)
GDAL_OPTS = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    GDAL_HTTP_MAX_RETRY="4",
    GDAL_HTTP_RETRY_DELAY="3",
    GDAL_HTTP_TIMEOUT="120",
)
if CA:
    # rasterio's bundled GDAL does not pick up CURL_CA_BUNDLE from the environment by itself.
    GDAL_OPTS.update(GDAL_CURL_CA_BUNDLE=CA, CURL_CA_BUNDLE=CA)

_lock = threading.Lock()
_no_texas = None


def no_texas():
    global _no_texas
    if _no_texas is None:
        _no_texas = set(NO_TEXAS.read_text().split()) if NO_TEXAS.exists() else set()
    return _no_texas


def ts(s):
    return dt.datetime.strptime(s, "%Y%m%dT%H%M%S")


# ---------------------------------------------------------------- listing

def list_prefix(prefix):
    """All objects under prefix as [(key, size, last_modified)], via S3 ListObjectsV2 pages."""
    out, token = [], None
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        for attempt in range(1, 6):
            try:
                r = S.get(BUCKET, params=params, timeout=(20, 120))
                r.raise_for_status()
                break
            except Exception as e:
                log(f"list retry {attempt} {prefix}: {type(e).__name__}: {str(e)[:100]}")
                time.sleep(5 * attempt)
        else:
            raise RuntimeError(f"listing failed: {prefix}")
        root = ET.fromstring(r.content)
        for c in root.findall("s3:Contents", ns):
            out.append((c.findtext("s3:Key", namespaces=ns), int(c.findtext("s3:Size", namespaces=ns)),
                        c.findtext("s3:LastModified", namespaces=ns)))
        if root.findtext("s3:IsTruncated", namespaces=ns) != "true":
            return out
        token = root.findtext("s3:NextContinuationToken", namespaces=ns)


def list_month(stream, prod, year, month):
    """GeoTIFF keys for one stream/product/month; cached once the month is 60+ days old."""
    cache = LISTINGS / f"{stream}_{prod}_{year}-{month:02d}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    items = [it for it in list_prefix(f"COGT/{stream}/L2__{prod}___/{year}/{month:02d}/")
             if it[0].endswith("_4326.tif")]
    month_end = (dt.date(year + month // 12, month % 12 + 1, 1))
    if (dt.date.today() - month_end).days > 60:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(items))
    return items


def orbits_for_month(prod, year, month, prefer, start, end, all_orbits):
    """One entry per orbit: the preferred stream, then the newest collection/processor/production."""
    found = defaultdict(lambda: defaultdict(dict))   # orbit -> version tuple -> layer -> (url, lastmod)
    info = {}
    for stream in ("OFFL", "RPRO"):
        for key, size, lastmod in list_month(stream, prod, year, month):
            m = KEY_RE.match(key)
            if not m:
                continue
            g = m.groupdict()
            day = ts(g["start"]).date()
            if not (start <= day <= end):
                continue
            rank = (g["stream"] == prefer, g["coll"], g["proc"], g["ptime"])
            found[g["orbit"]][rank][g["layer"]] = (BUCKET + key, lastmod)
            info[(g["orbit"], rank)] = g
    orbits = []
    for orbit, versions in found.items():
        rank = max(versions)
        g = info[(orbit, rank)]
        t0, t1 = ts(g["start"]), ts(g["end"])
        if not all_orbits and not overlaps_pass(t0, t1):
            continue
        layers = versions[rank]
        if MAIN_LAYER[prod] not in layers:
            log(f"no main layer for {g['gran']}, skipped (layers: {sorted(layers)})")
            continue
        orbits.append({"prod": prod, "gran": g["gran"], "stream": g["stream"], "coll": g["coll"],
                       "proc": g["proc"], "orbit": orbit, "start": t0, "layers": layers})
    return sorted(orbits, key=lambda o: o["start"])


def overlaps_pass(t0, t1):
    d = dt.datetime.combine(t0.date(), dt.time())
    for day in (d - dt.timedelta(days=1), d, d + dt.timedelta(days=1)):
        if t0 < day + PASS_UTC[1] and t1 > day + PASS_UTC[0]:
            return True
    return False


# ---------------------------------------------------------------- window reads

def box_window(transform):
    """Pixel window that fully covers BOX on this grid (north-up grid assumed)."""
    a, c, e, f = transform.a, transform.c, transform.e, transform.f
    col0 = math.floor((BOX[0] - c) / a + 1e-9)
    col1 = math.ceil((BOX[2] - c) / a - 1e-9)
    row0 = math.floor((BOX[3] - f) / e + 1e-9)
    row1 = math.ceil((BOX[1] - f) / e - 1e-9)
    return Window(col0, row0, col1 - col0, row1 - row0)


def read_layer(url):
    last = None
    for attempt in range(1, 4):
        try:
            with rasterio.open("/vsicurl/" + url) as ds:
                w = box_window(ds.transform)
                nodata = ds.nodata
                arr = ds.read(1, window=w, boundless=True,
                              fill_value=nodata if nodata is not None else 0)
                return arr, nodata, ds.window_transform(w)
        except Exception as e:
            last = e
            time.sleep(5 * attempt)
    raise last


def short(layer):
    return layer.replace("PRODUCT_SUPPORT_DATA_DETAILED_RESULTS_", "").replace("PRODUCT_", "")


def process(o):
    """Read the Texas window of one orbit; save and record it if it has valid data."""
    main_url = o["layers"][MAIN_LAYER[o["prod"]]][0]
    if main_url in done_urls() or main_url in no_texas():
        return "skip", 0
    t_begin = time.time()
    with rasterio.Env(**GDAL_OPTS):
        arr, nodata, tr = read_layer(main_url)
        valid = int(np.count_nonzero(arr != nodata)) if nodata is not None else arr.size
        if nodata is not None and np.issubdtype(arr.dtype, np.floating):
            valid = int(np.count_nonzero((arr != nodata) & np.isfinite(arr)))
        if valid == 0:
            with _lock:
                NO_TEXAS.parent.mkdir(parents=True, exist_ok=True)
                with open(NO_TEXAS, "a") as fh:
                    fh.write(main_url + "\n")
                no_texas().add(main_url)
            return "miss", time.time() - t_begin
        data = {short(MAIN_LAYER[o["prod"]]): arr, f"nodata_{short(MAIN_LAYER[o['prod']])}": np.array(nodata)}
        gt = np.array(tr.to_gdal(), dtype="float64")
        data["geotransform"] = gt
        for layer, (url, _) in sorted(o["layers"].items()):
            if layer == MAIN_LAYER[o["prod"]]:
                continue
            a, nd, t = read_layer(url)
            name = short(layer)
            data[name] = a
            data[f"nodata_{name}"] = np.array(nd if nd is not None else np.nan)
            if not np.allclose(t.to_gdal(), gt):
                data[f"geotransform_{name}"] = np.array(t.to_gdal(), dtype="float64")
    meta = {"granule": o["gran"], "product": o["prod"], "stream": o["stream"], "collection": o["coll"],
            "processor": o["proc"], "orbit": o["orbit"], "box_lon_lat": BOX, "crs": "EPSG:4326",
            "units": "columns mol/m2; qa_value 0-100; utctime unix seconds",
            "layer_urls": {short(k): v[0] for k, v in o["layers"].items()}}
    data["meta"] = np.array(json.dumps(meta))

    buf = io.BytesIO()
    np.savez_compressed(buf, **data)
    blob = buf.getvalue()
    rel = f"{SOURCE}/{o['prod']}/{o['start']:%Y}/{o['gran']}.npz"
    dest = EXT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(blob)
    tmp.rename(dest)
    rec = {"source": SOURCE, "url": main_url, "file": rel, "bytes": len(blob),
           "sha256": hashlib.sha256(blob).hexdigest(), "stored": "texas window",
           "last_modified": o["layers"][MAIN_LAYER[o["prod"]]][1],
           "downloaded_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "layer_urls": sorted(v[0] for k, v in o["layers"].items() if k != MAIN_LAYER[o["prod"]]),
           "valid_pixels": valid}
    with _lock:
        with open(MANIFEST, "a") as m:
            m.write(json.dumps(rec) + "\n")
        done_urls().add(main_url)
    return "saved", time.time() - t_begin


# ---------------------------------------------------------------- main

def months(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", type=dt.date.fromisoformat, default=FIRST_DAY)
    ap.add_argument("--end", type=dt.date.fromisoformat, default=dt.datetime.now(dt.timezone.utc).date())
    ap.add_argument("--products", nargs="+", default=["SO2", "NO2"], choices=["SO2", "NO2"])
    ap.add_argument("--prefer", default="OFFL", type=str.upper, choices=["OFFL", "RPRO"],
                    help="stream to use when an orbit is in both (default OFFL)")
    ap.add_argument("--workers", type=int, default=4, help="parallel orbits (max 4)")
    ap.add_argument("--all-orbits", action="store_true", help="open every orbit, not just the Texas pass times")
    args = ap.parse_args()
    workers = max(1, min(4, args.workers))
    EXT.mkdir(parents=True, exist_ok=True)
    # load both skip lists here, before the threads start: their lazy loaders are not thread-safe
    done_urls()
    no_texas()
    log(f"TROPOMI Texas windows {args.start} to {args.end}, {args.products}, prefer {args.prefer}, "
        f"{workers} workers, CA bundle {CA}")
    totals = defaultdict(int)
    t_run = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for y, m in months(args.start, args.end):
            orbits = []
            for prod in args.products:
                orbits += orbits_for_month(prod, y, m, args.prefer, args.start, args.end, args.all_orbits)
            futs = {pool.submit(process, o): o for o in orbits}
            counts = defaultdict(int)
            for f in as_completed(futs):
                o = futs[f]
                try:
                    status, secs = f.result()
                except Exception as e:
                    status, secs = "failed", 0
                    log(f"FAILED {o['gran']}: {type(e).__name__}: {str(e)[:150]}")
                counts[status] += 1
                if status in ("saved", "miss"):
                    log(f"{status} {o['prod']} {o['gran']} ({secs:.1f} s)")
            for k, v in counts.items():
                totals[k] += v
            log(f"{y}-{m:02d}: {len(orbits)} candidate orbits, " +
                ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    log(f"all done in {time.time() - t_run:.0f} s: " + ", ".join(f"{k} {v}" for k, v in sorted(totals.items())))


if __name__ == "__main__":
    main()
