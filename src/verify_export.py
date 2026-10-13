"""Compare every per-incident contaminant export with the contaminant lines parsed from its detail page.

Detail side: data/derived/contaminants.csv.gz (built by quality_pass.py from the saved HTML pages).
Export side: every spreadsheet in data/raw/export/*.jsonl.gz, read with xlrd.
Also records the "estimated" and "amount unknown" flags that only the export carries
(data/derived/export_flags.csv.gz) and checks the export's own header fields.
Outputs: data/manifests/export_verification.json and data/derived/export_flags.csv.gz

Usage: python3 src/verify_export.py
"""
import base64
import collections
import gzip
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
import xlrd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from verify import blankish, norm_f  # noqa: E402

_D = {}
COLS = ["INCIDENT NO.", "RN", "EMISSION POINT NAME", "EPN", "CONTAMINANT", "EST QUANTITY/OPACITY",
        "ESTIMATED IND", "AMOUNT UNK IND", "UNITS", "EMISSION LIMIT", "LIMIT UNITS", "AUTHORIZATION COMMENT"]


def init(detail):
    _D["d"] = detail


def cell(v):
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return v
    return v


def txt(v):
    """The spreadsheet reader turns numbers like 19155 into 19155.0; the page prints 19155."""
    if isinstance(v, float) and v == v and v == int(v):
        return str(int(v))
    return "" if v is None else str(v)


def explain(t):
    """Undo the two known spreadsheet artifacts so rows can be compared."""
    epn, desc, qty, units, lim, lunits, auth = t
    try:
        # 44E08 on the page is read by the spreadsheet as the number 4400000000
        epn = str(float(epn)) if epn.replace(".", "", 1).isdigit() or "E" in epn.upper() and epn.upper().replace("E", "", 1).isdigit() else epn
    except ValueError:
        pass
    return (epn, desc, 0.0 if qty is None else qty, units, 0.0 if lim is None else lim, lunits, auth)


def tup(epn, desc, qty, units, lim, lunits, auth):
    return (blankish(txt(epn)), " ".join(txt(desc).split()), norm_f(qty), " ".join(txt(units).split()),
            norm_f(lim), " ".join(txt(lunits).split()), blankish(txt(auth)))


def one_shard(path):
    detail = _D["d"]
    res = collections.Counter()
    examples = collections.defaultdict(list)
    flags = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            n = rec["incident"]
            body = base64.b64decode(rec["body_b64"])
            res["exports"] += 1
            if hashlib.sha256(body).hexdigest() != rec["sha256"]:
                res["sha_mismatch"] += 1
            try:
                wb = xlrd.open_workbook(file_contents=body)
                ws = wb.sheet_by_index(0)
                head = [str(x).strip() for x in ws.row_values(0)]
                idx = {c: head.index(c) for c in COLS}
            except Exception as e:  # report, never hide
                res["unreadable"] += 1
                examples["unreadable"].append((n, str(e)[:80]))
                continue
            rows = []
            inc_ok = True
            for r in range(1, ws.nrows):
                v = ws.row_values(r)
                if str(int(float(v[idx["INCIDENT NO."]]))) != str(n):
                    inc_ok = False
                t = tup(v[idx["EPN"]], v[idx["CONTAMINANT"]], v[idx["EST QUANTITY/OPACITY"]], v[idx["UNITS"]],
                        v[idx["EMISSION LIMIT"]], v[idx["LIMIT UNITS"]], v[idx["AUTHORIZATION COMMENT"]])
                if any(x not in ("", None) for x in t[1:]):
                    rows.append(t)
                    flags.append((n, str(v[idx["CONTAMINANT"]]).strip(), str(v[idx["ESTIMATED IND"]]).strip(),
                                  str(v[idx["AMOUNT UNK IND"]]).strip()))
            if not inc_ok:
                res["export_wrong_incident"] += 1
            res["export_rows"] += len(rows)
            d = detail.get(n, [])
            if sorted(rows, key=str) == sorted(d, key=str):
                res["match"] += 1
            elif sorted(map(explain, rows), key=str) == sorted(map(explain, d), key=str):
                # differs only by a known spreadsheet artifact: EPNs like 44E08 read as numbers,
                # and a quantity the page prints as None that the spreadsheet shows as 0
                res["match_after_known_artifacts"] += 1
                res["differ"] += 0
            else:
                res["differ"] += 1
                if len(examples["differ"]) < 8:
                    only_e = [r for r in rows if r not in d][:2]
                    only_d = [r for r in d if r not in rows][:2]
                    examples["differ"].append((n, len(rows), len(d), only_e, only_d))
            if not rows and not d:
                res["both_empty"] += 1
    return dict(res), dict(examples), flags


def main():
    c = pd.read_csv(ROOT / "data/derived/contaminants.csv.gz", dtype=str, keep_default_na=False)
    detail = collections.defaultdict(list)
    for r in c.itertuples(index=False):
        detail[int(r.incident)].append(tup(r.epn, r.description, r.quantity_text, r.units, r.limit, r.limit_units,
                                          r.authorization))
    shards = sorted((ROOT / "data/raw/export").glob("shard_*.jsonl.gz"))
    print(f"{len(shards)} export shards; {len(detail)} incidents with detail contaminant lines", flush=True)
    total, ex, allflags = collections.Counter(), collections.defaultdict(list), []
    with Pool(3, initializer=init, initargs=(dict(detail),)) as pool:
        for i, (res, examples, flags) in enumerate(pool.imap(one_shard, shards), start=1):
            total.update(res)
            for k, v in examples.items():
                ex[k] += v
            allflags += flags
            if i % 50 == 0:
                print(f"  {i}/{len(shards)}", flush=True)
    fl = pd.DataFrame(allflags, columns=["incident", "contaminant", "estimated_ind", "amount_unknown_ind"])
    fl.to_csv(ROOT / "data/derived/export_flags.csv.gz", index=False)
    flagdist = {"estimated_ind": fl.estimated_ind.value_counts().to_dict(),
                "amount_unknown_ind": fl.amount_unknown_ind.value_counts().to_dict()}
    out = {"export_files": int(total["exports"]), "incidents_matching_detail_page": int(total["match"]),
           "incidents_differing": int(total["differ"]),
           "incidents_matching_after_known_artifacts": int(total["match_after_known_artifacts"]), "both_empty": int(total["both_empty"]),
           "export_contaminant_rows": int(total["export_rows"]),
           "detail_contaminant_rows": int(len(c)), "sha256_mismatches": int(total["sha_mismatch"]),
           "unreadable": int(total["unreadable"]), "export_wrong_incident": int(total["export_wrong_incident"]),
           "flag_values": flagdist, "examples_of_differences": ex.get("differ", [])[:8],
           "comparison": "emission point number, contaminant, quantity, units, limit, limit units, authorization; "
                         "blank placeholders (N/A, NA, None) and runs of spaces ignored"}
    (ROOT / "data/manifests/export_verification.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
