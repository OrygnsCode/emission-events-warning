"""Hourly monitor data for check V1 (plan D6 item 7), in UTC, for monitors within 10 km of any D6 episode location.

AQS (data/slices/epa_aqs hourly files, matched on GMT date and time): SO2 42401, NO2 42602, NOx 42603, benzene 45201,
1,3-butadiene 43218, total non-methane organics 43102, resultant wind speed 61103 (knots -> m/s) and direction 61104.
TCEQ monthly report pages (data/external/tceq_monitors/monthly): the same pollutants plus H2S, and resultant wind
speed (mph -> m/s) and direction; times are local standard time as stated on each page (CST = UTC-6, MST = UTC-7);
flagged hours (calibration, span, power failure and so on) are left out.
Monitor locations: the AQS site list. When AQS and TCEQ both have a site-hour of the same quantity, AQS is used.

Output: data/derived/vchecks/hourly_<family>.parquet (site, utc, value, src) and hourly_wind.parquet
(site, utc, ws_ms, wd, src); monitor_sites.csv
"""
import gzip
import html
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vchecks_common as vc  # noqa: E402

AQS = vc.ROOT / "data" / "slices" / "epa_aqs"
TCEQ = vc.ROOT / "data" / "external" / "tceq_monitors" / "monthly"
AQS_CODES = {42401: "so2", 42602: "nox", 42603: "nox_total", 45201: "benzene", 43218: "butadiene", 43102: "voc",
             61103: "ws", 61104: "wd"}
GROUPS = {"42401": [42401], "42602": [42602], "NONOxNOy": [42603], "VOCS": [45201, 43218, 43102],
          "HAPS": [45201, 43218], "WIND": [61103, 61104]}
TCEQ_NAMES = {"Sulfur Dioxide": "so2", "Hydrogen Sulfide": "h2s", "Nitrogen Dioxide": "nox",
              "Oxides of Nitrogen": "nox_total", "Benzene": "benzene", "1,3 Butadiene": "butadiene",
              "1,3-Butadiene": "butadiene", "Total Non-Methane Organic Compounds": "voc",
              "Resultant Wind Speed": "ws", "Resultant Wind Direction": "wd"}
AGC = vc.ROOT / "data" / "external" / "tceq_monitors" / "agc"
# AQS reports hourly benzene and butadiene in parts per billion carbon; TCEQ pages in parts per billion by volume.
# ppbC = ppbV x carbon atoms (benzene C6H6: 6; 1,3-butadiene C4H6: 4); checked on hours both sources report.
CARBON = {"benzene": 6.0, "butadiene": 4.0}
AGC_HEAD = re.compile(r"^(\w+ \d{4})\.\s+(Benzene|1,3-Butadiene) \(POC (\d+)\) measured in (.+?)\.\s+Local Standard Time")
HEAD = re.compile(r"CAMS (\d+) Monthly (.+?) Summary Report for (\w+ \d{4})\s*\n.*?- EPA Site: (\S+)\s*\n"
                  r".*? \(POC (\d+)\) measured in (.+?)\n(?:.*\n)*?(Central|Mountain) Standard Time")


def sites():
    z = zipfile.ZipFile(vc.ROOT / "data/external/epa_aqs/aqs_sites.zip")
    s = pd.read_csv(z.open("aqs_sites.csv"), dtype=str)
    s = s[s["State Code"] == "48"]
    s["site"] = "48_" + s["County Code"].str.zfill(3) + "_" + s["Site Number"].str.zfill(4)
    s["lat"] = pd.to_numeric(s.Latitude, errors="coerce")
    s["lon"] = pd.to_numeric(s.Longitude, errors="coerce")
    return s.dropna(subset=["lat"]).set_index("site")[["lat", "lon"]]


def near_sites(S, ep):
    loc = ep.dropna(subset=["lat"])[["lat", "lon"]].drop_duplicates()
    keep = []
    for site, r in S.iterrows():
        if (vc.km(r.lat, r.lon, loc.lat.values, loc.lon.values) <= 10.0).any():
            keep.append(site)
    return set(keep)


def aqs(keep):
    out = {}
    for g, codes in GROUPS.items():
        for y in range(2002, 2022):
            f = AQS / f"hourly_{g}_{y}_tx.csv.gz"
            if not f.exists():
                continue
            for ch in pd.read_csv(f, usecols=["State Code", "County Code", "Site Num", "Parameter Code", "POC",
                                              "Date GMT", "Time GMT", "Sample Measurement"],
                                  dtype={"State Code": str, "County Code": str, "Site Num": str}, chunksize=2_000_000):
                ch = ch[ch["Parameter Code"].isin(codes)]
                ch["site"] = ch["State Code"] + "_" + ch["County Code"] + "_" + ch["Site Num"]
                ch = ch[ch.site.isin(keep)]
                if ch.empty:
                    continue
                ch["utc"] = pd.to_datetime(ch["Date GMT"] + " " + ch["Time GMT"], format="%Y-%m-%d %H:%M")
                for code, q in AQS_CODES.items():
                    sub = ch[ch["Parameter Code"] == code]
                    if len(sub):
                        out.setdefault(q, []).append(sub[["site", "POC", "utc", "Sample Measurement"]]
                                                     .rename(columns={"Sample Measurement": "value", "POC": "poc"}))
            print("aqs", g, y, flush=True)
    res = {}
    for q, parts in out.items():
        d = pd.concat(parts)
        # one value per site-hour: the lowest POC (the primary instrument)
        d = d.sort_values("poc").drop_duplicates(["site", "utc"])
        res[q] = d.drop(columns="poc").assign(src="aqs")
    return res


def tceq(keep):
    out = {}
    for f in sorted(TCEQ.glob("*/*.html.gz")):
        t = gzip.open(f, "rt", errors="replace").read()
        for blk in re.findall(r"<pre[^>]*>(.*?)</pre>", t, flags=re.S | re.I):
            b = html.unescape(re.sub("<[^>]+>", "", blk))
            for sec in re.split(r"(?=CAMS \d+ Monthly )", b):
                m = HEAD.search(sec)
                if not m:
                    continue
                q = TCEQ_NAMES.get(m.group(2).strip())
                site = m.group(4)
                if q is None or site not in keep:
                    continue
                offset = 6 if m.group(7) == "Central" else 7
                units = m.group(6).strip()
                rows = []
                for line in sec.splitlines():
                    if not re.match(r"\d\d/\d\d/\d{4},", line):
                        continue
                    p = line.split(",")
                    day = pd.Timestamp(p[0])
                    for h, v in enumerate(p[1:25]):
                        v = v.strip()
                        if re.fullmatch(r"-?\d+(\.\d+)?", v):
                            rows.append((day + pd.Timedelta(hours=h + offset), float(v)))
                if not rows:
                    continue
                d = pd.DataFrame(rows, columns=["utc", "value"])
                if q == "ws":
                    d["value"] = d.value * (0.44704 if "miles per hour" in units else 1.0)
                if q in CARBON and "carbon" not in units.lower():
                    d["value"] = d.value * CARBON[q]
                d["site"], d["poc"], d["units"] = site, int(m.group(5)), units
                out.setdefault(q, []).append(d)
    res = {}
    for q, parts in out.items():
        d = pd.concat(parts).sort_values("poc").drop_duplicates(["site", "utc"])
        res[q] = d[["site", "utc", "value"]].assign(src="tceq")
        print("tceq", q, len(d), d.units.value_counts().to_dict(), flush=True)
    return res


def agc(keep):
    """TCEQ AutoGC monthly pages: benzene and 1,3-butadiene, local standard time, converted to ppbC."""
    out = {}
    for f in sorted(AGC.glob("48_*/*.html.gz")):
        site = f.parent.name
        if site not in keep:
            continue
        offset = 7 if site.startswith(("48_141_", "48_229_")) else 6
        t = gzip.open(f, "rt", errors="replace").read()
        for blk in re.findall(r"<pre[^>]*>(.*?)</pre>", t, flags=re.S | re.I):
            b = html.unescape(re.sub("<[^>]+>", "", blk))
            cur = None
            for line in b.splitlines():
                m = AGC_HEAD.match(line.strip())
                if m:
                    q = "benzene" if m.group(2) == "Benzene" else "butadiene"
                    month = pd.Timestamp(m.group(1))
                    units = m.group(4).lower()
                    factor = CARBON[q] if "volume" in units else (1.0 if "carbon" in units else np.nan)
                    cur = (q, month, int(m.group(3)), factor)
                    continue
                if cur and re.match(r"\d+,", line):
                    q, month, poc, factor = cur
                    p = line.split(",")
                    day = month + pd.Timedelta(days=int(p[0]) - 1)
                    for h, v in enumerate(p[1:25]):
                        v = v.strip()
                        if re.fullmatch(r"-?\d+(\.\d+)?", v):
                            out.setdefault(q, []).append((site, poc, day + pd.Timedelta(hours=h + offset),
                                                          float(v) * factor))
    res = {}
    for q, rows in out.items():
        d = pd.DataFrame(rows, columns=["site", "poc", "utc", "value"]).dropna()
        d = d.sort_values("poc").drop_duplicates(["site", "utc"])
        res[q] = d[["site", "utc", "value"]].assign(src="tceq_agc")
        print("agc", q, len(d), d.site.nunique(), flush=True)
    return res


def main():
    ep = pd.read_pickle(vc.OUT / "episodes.pkl")
    S = sites()
    keep = near_sites(S, ep)
    S.loc[sorted(keep)].to_csv(vc.OUT / "monitor_sites.csv")
    print("sites within 10 km of an episode location:", len(keep))
    cache = vc.OUT / "aqs_cache"
    if cache.exists() and any(cache.glob("*.parquet")):
        a = {f.stem: pd.read_parquet(f) for f in cache.glob("*.parquet")}
    else:
        a = aqs(keep)
        cache.mkdir(exist_ok=True)
        for q, d in a.items():
            d.to_parquet(cache / f"{q}.parquet", index=False)
    if len(sys.argv) > 1 and sys.argv[1] == "aqs-only":
        return
    t = tceq(keep)
    g = agc(keep)
    # unit check on hours where AQS and the AutoGC pages both report (after conversion to ppbC)
    check = {}
    for q in CARBON:
        if q in a and q in g:
            j = a[q].merge(g[q], on=["site", "utc"], suffixes=("_aqs", "_agc"))
            j = j[(j.value_aqs > 0.5) & (j.value_agc > 0.5)]
            check[q] = {"overlap_hours": len(j), "median_ratio_aqs_to_agc": round(float((j.value_aqs / j.value_agc).median()), 3),
                        "share_within_10pct": round(float(((j.value_aqs / j.value_agc - 1).abs() <= .1).mean()), 3)}
    print("unit check", check, flush=True)
    import json as _json
    (vc.OUT / "v1_unit_check.json").write_text(_json.dumps(check, indent=1) + "\n")
    for q in sorted(set(a) | set(t) | set(g)):
        parts = [x for x in (a.get(q), t.get(q), g.get(q)) if x is not None]
        d = pd.concat(parts)
        d = d.sort_values("src").drop_duplicates(["site", "utc"])   # "aqs" < "tceq" < "tceq_agc": AQS wins
        if q == "ws" and q in a:
            m = d.src.eq("aqs")
            d.loc[m, "value"] = d.loc[m, "value"] * 0.514444   # AQS resultant wind speed is in knots
        d.to_parquet(vc.OUT / f"hourly_{q}.parquet", index=False)
        print(q, len(d), d.src.value_counts().to_dict(), d.site.nunique(), flush=True)


if __name__ == "__main__":
    main()
