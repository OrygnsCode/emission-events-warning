"""Texas slice of the raw EPA RMP database (RMPData.sqlite from the Data Liberation Project).

The processed RMP tables already in data/slices come from the project's cleaned CSVs. This slice keeps the
raw tables as EPA stores them, including every *_ChangeHistory table (they hold the corrections, for
example OldAccidentDate), so accident-date conflicts can be checked against what the plant first filed.

A table is cut to Texas through whichever key it has, in this order: FacilityID, EPAFacilityID,
AccidentChemicalID, AccidentHistoryID, ProcessChemicalID, Process_NAICS_ID, ProcessID, PreventionProgram3ID,
PreventionProgram2ID. Texas facilities are those whose row in tblS1Facilities (or its ChangeHistory) says
FacilityState = TX. Lookup tables (tlkp*) are copied whole. Values are written as stored in SQLite.

Output: data/slices/rmp_raw/<table>.csv.gz plus SLICES.jsonl records. Read-only on the database.

Usage: python3 src/slice_rmp_raw.py
"""
import csv
import gzip
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch_more import SLICES, log, record_slice, slice_done  # noqa: E402

DB = ROOT / "data/external/rmp_raw/RMPData.sqlite"
KEYS = [("FacilityID", "tx_fac"), ("EPAFacilityID", "tx_epa"), ("AccidentChemicalID", "tx_accchem"),
        ("AccidentHistoryID", "tx_acc"), ("ProcessChemicalID", "tx_pc"), ("Process_NAICS_ID", "tx_naics"),
        ("ProcessID", "tx_proc"), ("PreventionProgram3ID", "tx_pp3"), ("PreventionProgram2ID", "tx_pp2")]


def cols(c, t):
    return [r[1] for r in c.execute(f'pragma table_info("{t}")')]


def build_sets(c):
    def has(t):
        return bool(c.execute("select 1 from sqlite_master where name=?", (t,)).fetchone())

    def make(name, sql_parts):
        c.execute(f"create temp table {name} (id)")
        for sql in sql_parts:
            c.execute(f"insert into {name} {sql}")
        c.execute(f"create index temp.i_{name} on {name}(id)")
        n = c.execute(f"select count(distinct id) from {name}").fetchone()[0]
        log(f"  {name}: {n} ids")

    fac = ["select FacilityID from tblS1Facilities where FacilityState='TX'"]
    if "FacilityState" in cols(c, "tblS1Facilities_ChangeHistory"):
        fac.append("select FacilityID from tblS1Facilities_ChangeHistory where FacilityState='TX'")
    make("tx_fac", fac)
    make("tx_epa", ["select EPAFacilityID from tblS1Facilities where FacilityState='TX'",
                    "select EPAFacilityID from tblS1Facilities_ChangeHistory where FacilityID in (select id from tx_fac)"])
    make("tx_proc", ["select ProcessID from tblS1Processes where FacilityID in (select id from tx_fac)",
                     "select ProcessID from tblS1Processes_ChangeHistory where FacilityID in (select id from tx_fac)"])
    make("tx_pc", ["select ProcessChemicalID from tblS1ProcessChemicals where ProcessID in (select id from tx_proc)",
                   "select ProcessChemicalID from tblS1ProcessChemicals_ChangeHistory where ProcessID in (select id from tx_proc)"])
    make("tx_naics", ["select Process_NAICS_ID from tblS1Process_NAICS where ProcessID in (select id from tx_proc)",
                      "select Process_NAICS_ID from tblS1Process_NAICS_ChangeHistory where ProcessID in (select id from tx_proc)"])
    make("tx_acc", ["select AccidentHistoryID from tblS6AccidentHistory where FacilityID in (select id from tx_fac)",
                    "select AccidentHistoryID from tblS6AccidentHistory_ChangeHistory where FacilityID in (select id from tx_fac)"])
    make("tx_accchem", ["select AccidentChemicalID from tblS6AccidentChemicals where AccidentHistoryID in (select id from tx_acc)",
                        "select AccidentChemicalID from tblS6AccidentChemicals_ChangeHistory where AccidentHistoryID in (select id from tx_acc)"])
    make("tx_pp3", ["select PreventionProgram3ID from tblS7PreventionProgram3 where Process_NAICS_ID in (select id from tx_naics)",
                    "select PreventionProgram3ID from tblS7PreventionProgram3_ChangeHistory where Process_NAICS_ID in (select id from tx_naics)"
                    if "Process_NAICS_ID" in cols(c, "tblS7PreventionProgram3_ChangeHistory") else
                    "select PreventionProgram3ID from tblS7PreventionProgram3 where 0"])
    make("tx_pp2", ["select PreventionProgram2ID from tblS8PreventionProgram2 where Process_NAICS_ID in (select id from tx_naics)",
                    "select PreventionProgram2ID from tblS8PreventionProgram2_ChangeHistory where Process_NAICS_ID in (select id from tx_naics)"
                    if "Process_NAICS_ID" in cols(c, "tblS8PreventionProgram2_ChangeHistory") else
                    "select PreventionProgram2ID from tblS8PreventionProgram2 where 0"])
    del has


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    log("building Texas id sets")
    build_sets(c)
    tables = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
    src = "https://github.com/data-liberation-project/epa-rmp-spreadsheets (RMPData.sqlite, sha256 in data/manifests/rmp_source.json)"
    out_dir = SLICES / "rmp_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for t in tables:
        rel = f"rmp_raw/{t}.csv.gz"
        if slice_done(rel):
            continue
        cl = cols(c, t)
        key = next(((k, s) for k, s in KEYS if k in cl), None)
        if t.startswith("tlkp") or t == "tlkpAdminRefreshInfo":
            where, rule = "", "whole table (code list)"
        elif key:
            where, rule = f' where "{key[0]}" in (select id from {key[1]})', f"{key[0]} belongs to a Texas facility (via {key[1]})"
        else:
            raise SystemExit(f"no Texas key for {t}: columns {cl}")
        out = SLICES / rel
        n = 0
        with gzip.open(f"{out}.part", "wt", newline="") as g:
            w = csv.writer(g, lineterminator="\n")
            w.writerow(cl)
            for row in c.execute(f'select * from "{t}"{where}'):
                w.writerow(["" if v is None else v for v in row])
                n += 1
        Path(f"{out}.part").rename(out)
        record_slice(out, n, [src], rule)
        summary.append((t, n))
    log("done: " + ", ".join(f"{t}={n}" for t, n in summary if n))


if __name__ == "__main__":
    main()
