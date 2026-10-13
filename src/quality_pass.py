"""One pass over every saved TCEQ detail page: integrity, parse, cross-checks, cause rules, tables.

For every page record in data/raw/details/*.jsonl.gz:
  - recompute SHA-256 of the stored bytes and compare with the recorded hash
  - parse the page; collect parser warnings
  - compare header fields with the official search list (data/master/incidents.csv.gz)
  - apply the frozen cause and unit rules (rules/cause_rules.json)
Outputs (data/derived/):
  page_checks.csv.gz   one row per saved page record, with every check result
  causes.csv.gz        cause and unit flags per incident
  contaminants.csv.gz  one row per contaminant line (incident, emission point, quantity, units, limit)
  emission_points.csv.gz  one row per emission point (incident, EPN, name, declared and parsed counts)
Does not touch accident data.

Usage: python3 src/quality_pass.py
"""
import base64
import gzip
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from classify_causes import row_for  # noqa: E402
from parse_detail import parse  # noqa: E402

OUT = ROOT / "data" / "derived"
_M = {}


def init(master):
    _M["m"] = master


def norm(x):
    return " ".join(str(x).split()).upper()


def one_shard(path):
    m = _M["m"]
    checks, causes, cont, eps = [], [], [], []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            n = rec["incident"]
            body = base64.b64decode(rec["body_b64"])
            row = {"incident": n, "shard": Path(path).name, "sha_ok": hashlib.sha256(body).hexdigest() == rec["sha256"],
                   "bytes": len(body)}
            p = parse(body)
            row["incident_matches"] = p.get("incident") == str(n)
            row["n_warnings"] = len(p["warnings"])
            row["warnings"] = "; ".join(p["warnings"])
            row["n_emission_points"] = len(p["emission_points"])
            row["n_contaminants"] = sum(len(e["contaminants"]) for e in p["emission_points"])
            if n in m.index:
                s = m.loc[n]
                pairs = {"rn": (p.get("rn"), s["RN"]), "county": (p.get("county"), s["COUNTY"]),
                         "event_type": (p.get("event_type"), s["EVENT TYPE"]),
                         "report_type": (p.get("report_type"), s["REPORT TYPE"]),
                         "report_date": (p.get("report_date"), s["REPORT DATE"]),
                         "start": (p.get("start_text"), s["START DATE/TIME"]), "end": (p.get("end_text"), s["END DATE/TIME"]),
                         "re_name": (p.get("regulated_entity_name"), s["RE NAME"]),
                         "customer": (f"{p.get('cn', '')} {p.get('owner_operator', '')}".strip(), s["ASSOCIATED CUSTOMER"])}
                for k, (a, b) in pairs.items():
                    row[f"mismatch_{k}"] = norm(a or "") != norm(b)
                row["in_master"] = True
            else:
                row["in_master"] = False
            checks.append(row)
            causes.append(row_for(n, p))
            for i, e in enumerate(p["emission_points"], start=1):
                eps.append({"incident": n, "ep_index": i, "epn": e["epn"], "name": e["name"],
                            "declared_total": e["declared_total"], "parsed": len(e["contaminants"])})
                for c in e["contaminants"]:
                    cont.append({"incident": n, "ep_index": i, "epn": e["epn"], "description": c["description"],
                                 "quantity": c["quantity"], "quantity_text": c["quantity_text"], "units": c["units"],
                                 "limit": c["limit"], "limit_units": c["limit_units"], "authorization": c["authorization"]})
    return checks, causes, cont, eps


def main():
    master = pd.read_csv(ROOT / "data/master/incidents.csv.gz", dtype=str, keep_default_na=False)
    master["INCIDENT NO."] = master["INCIDENT NO."].astype(int)
    master = master.set_index("INCIDENT NO.")
    shards = sorted((ROOT / "data/raw/details").glob("shard_*.jsonl.gz"))
    print(f"{len(shards)} shards, master {len(master)} incidents", flush=True)
    with Pool(3, initializer=init, initargs=(master,)) as pool:
        res = []
        for i, r in enumerate(pool.imap(one_shard, shards, chunksize=4), start=1):
            res.append(r)
            if i % 50 == 0:
                print(f"  {i}/{len(shards)} shards", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for idx, name in enumerate(("page_checks", "causes", "contaminants", "emission_points")):
        pd.DataFrame([row for r in res for row in r[idx]]).to_csv(OUT / f"{name}.csv.gz", index=False)
    print("tables written", flush=True)


if __name__ == "__main__":
    main()
