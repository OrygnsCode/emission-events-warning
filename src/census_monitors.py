"""Monitor and wind census for the warning-sign check V1 (data dossier, no accident data).

Summarizes, by code, every hourly row of the sources V1 would use, 2002 to 2026:
  EPA AQS hourly files (data/slices/epa_aqs): SO2, NO2, NOx/NOy, VOC and HAP species, wind
  TCEQ CAMS monthly hourly pages (data/external/tceq_monitors/monthly): H2S and every other parameter on the page
  IEM ASOS airport weather (data/external/iem_asos): wind direction and speed
and counts how many V1-eligible events (unplanned emissions events at plants with an RMP risk period, 2003 to 2021,
after the same-start merge) have a monitor of the reported pollutant family within 10 km with data on the event day.

Outputs (data/derived/monitors/): aqs_monitor_years.csv, tceq_monitor_months.csv, asos_station_years.csv,
v1_coverage.json
Usage: python3 src/census_monitors.py [aqs|tceq|asos|coverage|all]
"""
import gzip
import warnings
import html
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="This pattern is interpreted")
ROOT = Path(__file__).resolve().parent.parent
DER = ROOT / "data" / "derived"
OUT = DER / "monitors"
AQS = ROOT / "data" / "slices" / "epa_aqs"
TCEQ = ROOT / "data" / "external" / "tceq_monitors" / "monthly"
ASOS = ROOT / "data" / "external" / "iem_asos"
YEARS = range(2002, 2027)

# pollutant families used by V1, as AQS parameter codes; contaminant names map to the same families
FAMILY_CODES = {
    "so2": {42401}, "nox": {42602, 42603, 42601, 42600}, "benzene": {45201}, "butadiene": {43218},
    "h2s": {42402}, "voc": {43102, 43000},
}
WIND_CODES = {61101, 61102, 61103, 61104}
KEEP = set().union(*FAMILY_CODES.values()) | WIND_CODES
GROUPS = ["42401", "42602", "NONOxNOy", "VOCS", "HAPS", "WIND"]
# D7 (2026-10-04): spelling variants added after a full sweep of contaminant names; "NITROUS OXIDES" (NOx or N2O)
# and "SULFUR OXIDES"/"SOX" (a group, not SO2 alone) stay out because they are ambiguous
CONTAM_FAMILY = {
    "so2": r"^(SULFUR DIOXIDE|SULFER DIOXIDE|SO2|SULFUR DIOXIDE \(ANHYDROUS\))$",
    "h2s": r"^(HYDROGEN SULFIDE|H2S|HYDROGEN SULPHIDE|HYDROGEN SULFIDE \(H2S\)|DIHYDROGEN SULFIDE|HPV HYDROGEN SULFIDE)$",
    "nox": r"^(NITROGEN OXIDES?|NOX|NITROGEN DIOXIDE|NO2|NITRIC OXIDE|NO|OXIDES OF NITROGEN|NITROGEN OXIDES \(NOX\)|OXIDES OF NITROGEN \(NOX\)|NOX \(STARTUP/SHUTDOWN\)|NITROGEN MONOXIDE)$",
    "benzene": r"^BENZENE$",
    "butadiene": r"^(1,3-BUTADIENE|BUTADIENE 1-3|BUTADIENE, 1-3|1,3 BUTADIENE|BUTADIENE)$",
    "voc": r"^(VOC|VOCS|VOLATILE ORGANIC COMPOUNDS?|VOC - UNCLASSIFIED|TOTAL VOC)",
}


def km(a, b, c, d):
    x = np.radians(d - b) * np.cos(np.radians((a + c) / 2))
    return 6371.0 * np.hypot(x, np.radians(c - a))


def aqs():
    cols = ["State Code", "County Code", "Site Num", "Parameter Code", "POC", "Latitude", "Longitude",
            "Parameter Name", "Date Local", "Sample Measurement", "Units of Measure", "MDL", "Method Name"]
    parts = []
    for g in GROUPS:
        for y in YEARS:
            f = AQS / f"hourly_{g}_{y}_tx.csv.gz"
            if not f.exists():
                continue
            for ch in pd.read_csv(f, usecols=cols, dtype={"State Code": str, "County Code": str, "Site Num": str},
                                  chunksize=2_000_000, low_memory=False):
                ch = ch[ch["Parameter Code"].isin(KEEP)]
                if ch.empty:
                    continue
                ch["site"] = ch["State Code"] + "_" + ch["County Code"] + "_" + ch["Site Num"]
                ch["year"] = y
                ch["group"] = g
                ch["below_mdl"] = ch["Sample Measurement"] < ch["MDL"]
                a = ch.groupby(["site", "Parameter Code", "POC", "year", "group"]).agg(
                    lat=("Latitude", "first"), lon=("Longitude", "first"), name=("Parameter Name", "first"),
                    units=("Units of Measure", "first"), method=("Method Name", "first"),
                    hours=("Sample Measurement", "size"), days=("Date Local", "nunique"),
                    below_mdl=("below_mdl", "sum"), first_day=("Date Local", "min"), last_day=("Date Local", "max"))
                parts.append(a.reset_index())
            print("aqs", g, y, flush=True)
    # the same species can sit in two file groups (benzene is in both VOCS and HAPS); sum chunks within a group, then
    # keep the group with the most hours so no hour is counted twice
    out = pd.concat(parts).groupby(["site", "Parameter Code", "POC", "year", "group"], as_index=False).agg(
        lat=("lat", "first"), lon=("lon", "first"), name=("name", "first"), units=("units", "first"),
        method=("method", "first"), hours=("hours", "sum"), days=("days", "sum"), below_mdl=("below_mdl", "sum"),
        first_day=("first_day", "min"), last_day=("last_day", "max"))
    out = out.sort_values("hours").drop_duplicates(["site", "Parameter Code", "POC", "year"], keep="last")
    out.to_csv(OUT / "aqs_monitor_years.csv", index=False)


HEAD = re.compile(r"CAMS (\d+) Monthly (.+?) Summary Report for (\w+ \d{4})\s*\n(.*?)- EPA Site: (\S+)\s*\n(.*?) \(POC (\d+)\) measured in (.+?)\n")


def tceq():
    rows = []
    for f in sorted(TCEQ.glob("*/*.html.gz")):
        t = gzip.open(f, "rt", errors="replace").read()
        for blk in re.findall(r"<pre[^>]*>(.*?)</pre>", t, flags=re.S | re.I):
            b = html.unescape(re.sub("<[^>]+>", "", blk))
            # one block holds several parameters, each starting with its own "CAMS n Monthly ..." header
            for sec in re.split(r"(?=CAMS \d+ Monthly )", b):
                m = HEAD.search(sec)
                if not m:
                    continue
                vals = [v.strip() for line in sec.splitlines() if re.match(r"\d\d/\d\d/\d{4},", line)
                        for v in line.split(",")[1:]]
                isnum = [bool(re.fullmatch(r"-?\d+(\.\d+)?", v)) for v in vals]
                flags = pd.Series([v for v, n in zip(vals, isnum) if not n], dtype=str).value_counts()
                rows.append({"cams": m.group(1), "param": m.group(2).strip(), "month": m.group(3),
                             "site_name": m.group(4).strip(), "aqs_site": m.group(5), "poc": int(m.group(7)),
                             "units": m.group(8).strip(), "hours_listed": len(vals), "hours_valid": sum(isnum),
                             "flags": ";".join(f"{k}:{v}" for k, v in flags.head(6).items())})
    pd.DataFrame(rows).to_csv(OUT / "tceq_monitor_months.csv", index=False)
    print("tceq pages", len(list(TCEQ.glob('*/*.html.gz'))), "blocks", len(rows))


def asos():
    rows = []
    for f in sorted(ASOS.glob("*.csv.gz")):
        d = pd.read_csv(f, usecols=["station", "valid", "lon", "lat", "drct", "sknt"], na_values=["M"], low_memory=False)
        d["year"] = d.valid.str[:4].astype(int)
        d["hour"] = d.valid.str[:13]
        g = d.groupby("year").agg(lat=("lat", "first"), lon=("lon", "first"), obs=("valid", "size"),
                                  hours=("hour", "nunique"))
        g["hours_with_dir"] = d.dropna(subset=["drct"]).groupby("year").hour.nunique()
        g["station"] = f.name.split(".")[0]
        rows.append(g.reset_index())
    pd.concat(rows).to_csv(OUT / "asos_station_years.csv", index=False)
    print("asos stations", len(rows))


def coverage():
    """How many V1-eligible events have a same-family monitor within 10 km reporting on the event day (by year)."""
    ev = pd.read_csv(DER / "events_v2.csv.gz", parse_dates=["event_datetime"])
    risk = set(pd.read_csv(DER / "plant_risk_v2.csv").plant_id)
    e = ev[ev.event_type.eq("EMISSIONS EVENT") & ev.plant_id.isin(risk) & ~ev.is_duplicate
           & ev.event_datetime.between("2003-06-01", "2021-12-31")].copy()
    pts = pd.read_parquet(DER / "tceq_rn_points_raw.parquet")
    pts = pts[pts.lat.between(25.5, 36.6) & pts.lon.between(-106.7, -93.4)].groupby("rn")[["lat", "lon"]].median()
    e = e.join(pts, on="rn")
    c = pd.read_csv(DER / "contaminants.csv.gz", usecols=["incident", "description"])
    c["desc"] = c.description.str.upper().str.strip()
    fam = {f: set(c.incident[c.desc.str.contains(p, regex=True, na=False)]) for f, p in CONTAM_FAMILY.items()}

    mon = pd.read_csv(OUT / "aqs_monitor_years.csv")
    mon["family"] = mon["Parameter Code"].map({c: f for f, cs in FAMILY_CODES.items() for c in cs})
    mon = mon[mon.family.notna() & mon.hours.ge(24 * 30)]
    tq = pd.read_csv(OUT / "tceq_monitor_months.csv")
    tq = tq[tq.param.str.contains("Hydrogen Sulfide", case=False)]
    tq["year"] = pd.to_datetime(tq.month, format="%B %Y").dt.year
    tq = tq.groupby(["aqs_site", "year"], as_index=False).hours_valid.sum()
    sites = mon.groupby("site")[["lat", "lon"]].first()
    tq = tq.join(sites, on="aqs_site").dropna(subset=["lat"]).assign(family="h2s")
    avail = pd.concat([mon[["site", "family", "year", "lat", "lon"]],
                       tq.rename(columns={"aqs_site": "site"})[["site", "family", "year", "lat", "lon"]]])
    wind_sites = set(pd.read_csv(OUT / "aqs_monitor_years.csv").query("`Parameter Code` in [61102, 61104]").site)

    res = {"v1_eligible_events": len(e), "events_with_location": int(e.lat.notna().sum()), "by_family": {}}
    yr = e.event_datetime.dt.year
    for f, incs in fam.items():
        sub = e[e.incident.isin(incs) & e.lat.notna()]
        av = avail[avail.family == f]
        hit, hit_wind, dists, cov_plants = 0, 0, [], set()
        for (y, la, lo, pid) in zip(sub.event_datetime.dt.year, sub.lat, sub.lon, sub.plant_id):
            a = av[av.year == y]
            if a.empty:
                continue
            dd = km(la, lo, a.lat.values, a.lon.values)
            if (dd <= 10).any():
                hit += 1
                cov_plants.add(pid)
                dists.append(float(dd.min()))
                if set(a.site.values[dd <= 10]) & wind_sites:
                    hit_wind += 1
        res["by_family"][f] = {"events_reporting_family": int(e.incident.isin(incs).sum()),
                               "with_location": len(sub), "monitor_within_10km_same_year": hit,
                               "of_which_wind_measured_at_monitor_site": hit_wind,
                               "median_km_to_nearest": round(float(np.median(dists)), 2) if dists else None,
                               "plants_reporting_family": int(sub.plant_id.nunique()),
                               "plants_with_covered_events": len(cov_plants)}
    (OUT / "v1_coverage.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in [("aqs", aqs), ("tceq", tceq), ("asos", asos), ("coverage", coverage)]:
        if step in (name, "all"):
            fn()
