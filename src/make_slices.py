"""Make Texas-only slices of the outside datasets.

Each slice keeps every column and every row that belongs to Texas (or to the
plants we need), as gzip CSV in data/slices/, with all values kept as text so
nothing is rounded or reinterpreted. data/slices/SLICES.jsonl records, for each
slice, its rows, size, SHA-256, source files and the filter rule used.

Usage: python3 src/make_slices.py rmp frs echo icis poll noaa nrc
"""
import codecs
import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "data" / "external"
OUT = ROOT / "data" / "slices"
RMP = Path(os.environ.get("RMP_SPREADSHEETS", EXT / "epa-rmp-spreadsheets"))  # clone of data-liberation-project/epa-rmp-spreadsheets
CHUNK = 400_000
READ = dict(dtype=str, keep_default_na=False, na_filter=False)


def log(msg):
    print(f"{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {msg}", flush=True)


def detect_encoding(opener):
    with opener() as f:
        raw = f.read(2_000_000)
    try:
        codecs.getincrementaldecoder("utf-8")().decode(raw, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


class Out:
    def __init__(self, name, sources, rule, encoding="utf-8"):
        OUT.mkdir(parents=True, exist_ok=True)
        self.name, self.sources, self.rule = name, sources, rule
        self.path = OUT / f"{name}.csv.gz"
        self.fh = gzip.open(self.path, "wt", encoding=encoding, newline="")
        self.rows, self.first = 0, True

    def write(self, df):
        if df.empty and not self.first:
            return
        df.to_csv(self.fh, header=self.first, index=False, lineterminator="\n")
        self.first = False
        self.rows += len(df)

    def close(self):
        self.fh.close()
        rec = {"slice": self.path.name, "rows": self.rows, "bytes": self.path.stat().st_size,
               "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
               "sources": self.sources, "rule": self.rule,
               "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        with open(OUT / "SLICES.jsonl", "a") as m:
            m.write(json.dumps(rec) + "\n")
        log(f"wrote {self.path.name}: {self.rows} rows, {rec['bytes'] / 1e6:.1f} MB")


def zip_chunks(zpath, member, **kw):
    enc = detect_encoding(lambda: zipfile.ZipFile(zpath).open(member))
    with zipfile.ZipFile(zpath) as z, z.open(member) as f:
        for ch in pd.read_csv(f, chunksize=CHUNK, encoding=enc, **READ, **kw):
            yield ch, enc


def zip_all(zpath, member):
    parts, enc = [], "utf-8"
    for ch, enc in zip_chunks(zpath, member):
        parts.append(ch)
    return pd.concat(parts, ignore_index=True), enc


# ------------------------------------------------------------------ slices
def rmp():
    src = "data-liberation-project/epa-rmp-spreadsheets"
    commit = subprocess.run(["git", "-C", str(RMP), "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    fac = pd.read_csv(RMP / "data/output/facilities.csv", **READ)
    tx = fac[fac["State"] == "TX"]
    ids = set(tx["EPAFacilityID"])
    srcs = [f"{src}@{commit}"]
    rule = "State == TX in facilities.csv; other tables filtered by EPAFacilityID"
    o = Out("rmp_facilities_tx", srcs, rule); o.write(tx); o.close()
    for name in ("submissions", "accidents", "accidents-with-duplicates"):
        df = pd.read_csv(RMP / f"data/output/{name}.csv", **READ)
        o = Out(f"rmp_{name.replace('-', '_')}_tx", srcs, rule)
        o.write(df[df["EPAFacilityID"].isin(ids)]); o.close()
    shutil.copy(RMP / "data/output/naics-codes.csv", OUT / "rmp_naics_codes.csv")
    for name in ("facilities", "submissions", "accidents"):
        shutil.copy(RMP / f"data/dictionaries/{name}.csv", OUT / f"rmp_dictionary_{name}.csv")
    (OUT / "rmp_source.json").write_text(json.dumps(
        {"repo": src, "commit": commit, "license": "CC BY-SA 4.0 (data), MIT (code)"}, indent=2) + "\n")


FRS_ZIP = EXT / "epa_frs" / "state_combined_tx.zip"
KEEP_PROGRAMS = {"RMP", "TX-TCEQ ACR", "AIR", "AIRS/AFS", "ICIS"}


def frs():
    prog, enc = zip_all(FRS_ZIP, "TX_PROGRAM_FILE.CSV")
    ids = set(prog.loc[prog["PGM_SYS_ACRNM"].isin(KEEP_PROGRAMS), "REGISTRY_ID"])
    rule = f"REGISTRY_ID has a program in {sorted(KEEP_PROGRAMS)}"
    src = [FRS_ZIP.name]
    o = Out("frs_program_tx_relevant", src, rule, enc); o.write(prog[prog["REGISTRY_ID"].isin(ids)]); o.close()
    del prog
    for member, name in (("TX_FACILITY_FILE.CSV", "frs_facility"), ("TX_NAICS_FILE.CSV", "frs_naics"),
                         ("TX_SIC_FILE.CSV", "frs_sic")):
        df, enc = zip_all(FRS_ZIP, member)
        o = Out(f"{name}_tx_relevant", src, rule, enc); o.write(df[df["REGISTRY_ID"].isin(ids)]); o.close()
    log(f"FRS: {len(ids)} registry ids kept")


def echo():
    z = EXT / "epa_echo" / "echo_exporter.zip"
    o = None
    for ch, enc in zip_chunks(z, "ECHO_EXPORTER.csv"):
        o = o or Out("echo_exporter_tx", [z.name], "FAC_STATE == TX", enc)
        o.write(ch[ch["FAC_STATE"] == "TX"])
    o.close()


def icis():
    z = EXT / "epa_echo" / "ICIS-AIR_downloads.zip"
    fac, enc = zip_all(z, "ICIS-AIR_FACILITIES.csv")
    fac = fac[fac["STATE"] == "TX"]
    ids = set(fac["PGM_SYS_ID"])
    o = Out("icis_air_facilities_tx", [z.name], "STATE == TX", enc); o.write(fac); o.close()
    for member in ("PROGRAMS", "PROGRAM_SUBPARTS", "POLLUTANTS", "FCES_PCES", "STACK_TESTS",
                   "TITLEV_CERTS", "FORMAL_ACTIONS", "INFORMAL_ACTIONS", "VIOLATION_HISTORY"):
        o = None
        for ch, enc in zip_chunks(z, f"ICIS-AIR_{member}.csv"):
            o = o or Out(f"icis_air_{member.lower()}_tx", [z.name], "PGM_SYS_ID in Texas facilities", enc)
            o.write(ch[ch["PGM_SYS_ID"].isin(ids)])
        o.close()


def poll():
    fac, _ = zip_all(FRS_ZIP, "TX_FACILITY_FILE.CSV")
    ids = set(fac.loc[fac["STATE_CODE"] == "TX", "REGISTRY_ID"])
    del fac
    z = EXT / "epa_echo" / "POLL_RPT_COMBINED_EMISSIONS.zip"
    o = None
    for ch, enc in zip_chunks(z, "POLL_RPT_COMBINED_EMISSIONS.csv"):
        o = o or Out("poll_rpt_combined_emissions_tx", [z.name, FRS_ZIP.name],
                     "REGISTRY_ID of a Texas facility in the FRS Texas facility file", enc)
        o.write(ch[ch["REGISTRY_ID"].isin(ids)])
    o.close()


def noaa():
    d = EXT / "noaa_storm_events"
    outs = {k: Out(f"noaa_storm_events_{k}_tx", ["noaa_storm_events/*.csv.gz (2003-2026)"],
                   "details: STATE_FIPS == 48; locations and fatalities: EVENT_ID of a Texas event")
            for k in ("details", "locations", "fatalities")}
    for year in range(2003, 2027):
        ids = set()
        for kind in ("details", "locations", "fatalities"):
            files = sorted(d.glob(f"StormEvents_{kind}-ftp_v1.0_d{year}_c*.csv.gz"))
            if not files:
                log(f"WARNING no {kind} file for {year}")
                continue
            df = pd.read_csv(files[-1], encoding="latin-1", **READ)
            if kind == "details":
                df = df[df["STATE_FIPS"] == "48"]
                ids = set(df["EVENT_ID"])
            else:
                df = df[df["EVENT_ID"].isin(ids)]
            outs[kind].write(df)
        log(f"NOAA {year} done")
    for o in outs.values():
        o.close()


NRC_FILES = ["nrc/CYDECADE2000.xlsx", "nrc/CYDECADE2010FirstHalf.zip", "nrc/CYDECADE2010SecondHalf.zip",
             "nrc/CYDECADE2020.zip", "nrc/CY25.xlsx", "nrc/CY26.xlsx"]


def seq(x):
    try:
        return str(int(float(x)))
    except (ValueError, TypeError):
        return str(x)


def nrc():
    tmp = EXT / "nrc" / "_unzipped"
    tmp.mkdir(exist_ok=True)
    books = []
    for rel in NRC_FILES:
        p = EXT / rel
        if p.suffix == ".zip":
            with zipfile.ZipFile(p) as z:
                (name,) = z.namelist()
                z.extract(name, tmp)
                p = tmp / name
        books.append(p)
    keep, sheets_seen = {}, []
    for p in books:
        log(f"NRC reading {p.name}")
        x = pd.ExcelFile(p, engine="calamine")
        commons = x.parse("INCIDENT_COMMONS", dtype=str).fillna("")
        tx = commons[commons["LOCATION_STATE"].str.strip().str.upper() == "TX"]
        ids = {seq(s) for s in tx["SEQNOS"]}
        log(f"  {p.name}: {len(ids)} Texas incidents of {len(commons)}")
        for sheet in x.sheet_names:
            df = x.parse(sheet, dtype=str).fillna("")
            if "SEQNOS" not in df.columns:
                continue
            df = df[df["SEQNOS"].map(seq).isin(ids)]
            df.insert(0, "SOURCE_WORKBOOK", p.name)
            keep.setdefault(sheet, []).append(df)
        del x
    for sheet, parts in keep.items():
        df = pd.concat(parts, ignore_index=True)
        o = Out(f"nrc_{sheet.lower()}_tx", [Path(f).name for f in NRC_FILES],
                "INCIDENT_COMMONS.LOCATION_STATE == TX; other sheets by SEQNOS")
        o.write(df); o.close()
    shutil.rmtree(tmp, ignore_errors=True)


JOBS = {"rmp": rmp, "frs": frs, "echo": echo, "icis": icis, "poll": poll, "noaa": noaa, "nrc": nrc}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for job in sys.argv[1:] or list(JOBS):
        log(f"=== {job} ===")
        JOBS[job]()
    log("all done")
