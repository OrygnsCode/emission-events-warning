"""Cross-check downloaded pages against independent sources.

For every incident that has both a detail page and a contaminant export:
  1. header fields on the detail page vs the official search list
  2. contaminant rows on the detail page vs the per-incident export
Prints agreement counts and the first few disagreements of each kind.

Usage: python3 src/verify.py [--show 5]
"""
import argparse
import base64
import collections
import gzip
import io
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_detail import parse  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def shards(endpoint):
    for f in sorted((DATA / "raw" / endpoint).glob("shard_*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                yield rec["incident"], base64.b64decode(rec["body_b64"])


def norm_s(x):
    return "" if pd.isna(x) else str(x).strip()


def norm_f(x):
    try:
        v = float(str(x).replace(",", ""))
    except (ValueError, TypeError):
        return None
    return None if v != v else round(v, 6)


def blankish(x):
    """Filers type N/A, NA or None for 'nothing'; the export leaves those cells empty."""
    x = " ".join(str(x).split())  # the page collapses runs of spaces; the export keeps them
    return "" if x.upper() in ("N/A", "NA", "NONE", "") else x


def drop_blank(rows):
    """A row with nothing but an emission point number is a placeholder, not a contaminant."""
    return [r for r in rows if any(v not in ("", None) for v in r[1:])]


def search_index():
    frames = [pd.read_excel(f) for f in sorted((DATA / "raw" / "search_exports").glob("*.xls"))]
    df = pd.concat(frames).drop_duplicates("INCIDENT NO.").set_index("INCIDENT NO.")
    return df


def detail_rows(p):
    rows = []
    for ep in p["emission_points"]:
        for c in ep["contaminants"]:
            rows.append((blankish(ep["epn"]), c["description"], norm_f(c["quantity_text"]), c["units"],
                         norm_f(c["limit_text"]), c["limit_units"], blankish(c["authorization"])))
    return sorted(drop_blank(rows), key=str)


def export_rows(body):
    df = pd.read_excel(io.BytesIO(body))
    rows = []
    for _, r in df.iterrows():
        rows.append((blankish(norm_s(r["EPN"])), norm_s(r["CONTAMINANT"]), norm_f(r["EST QUANTITY/OPACITY"]),
                     norm_s(r["UNITS"]), norm_f(r["EMISSION LIMIT"]), norm_s(r["LIMIT UNITS"]),
                     blankish(norm_s(r["AUTHORIZATION COMMENT"]))))
    return sorted(drop_blank(rows), key=str), df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=5)
    args = ap.parse_args()

    search = search_index()
    details = {n: parse(b) for n, b in shards("details")}
    exports = dict(shards("export"))
    both = sorted(set(details) & set(exports))
    print(f"details parsed: {len(details)}, exports: {len(exports)}, both: {len(both)}")

    hdr_fields = {
        "rn": ("RN", lambda p: p["rn"]),
        "county": ("COUNTY", lambda p: p["county"]),
        "event_type": ("EVENT TYPE", lambda p: p["event_type"]),
        "report_type": ("REPORT TYPE", lambda p: p["report_type"]),
        "report_date": ("REPORT DATE", lambda p: p["report_date"]),
        "start": ("START DATE/TIME", lambda p: p["start_text"]),
        "end": ("END DATE/TIME", lambda p: p["end_text"]),
        "re_name": ("RE NAME", lambda p: p["regulated_entity_name"]),
        "customer": ("ASSOCIATED CUSTOMER", lambda p: f"{p['cn']} {p['owner_operator']}".strip()),
    }
    bad = collections.defaultdict(list)
    for n, p in details.items():
        if n not in search.index:
            bad["not_in_search_list"].append((n,))
            continue
        for name, (col, fn) in hdr_fields.items():
            a, b = norm_s(fn(p)).upper(), norm_s(search.loc[n, col]).upper()
            if a != b:
                bad[f"header:{name}"].append((n, a, b))
    print("\nHEADER vs official search list")
    for name in hdr_fields:
        k = f"header:{name}"
        print(f"  {name:12s} mismatches: {len(bad[k])} of {len(details)}")
    print(f"  incidents missing from search list: {len(bad['not_in_search_list'])}")

    flags = collections.Counter()
    for n in both:
        d = detail_rows(details[n])
        e, df = export_rows(exports[n])
        if d != e:
            bad["contaminants"].append((n, d, e))
        for col in ("ESTIMATED IND", "AMOUNT UNK IND"):
            for v in df[col].fillna("(blank)"):
                flags[(col, v)] += 1
    print(f"\nCONTAMINANT rows, detail page vs export: "
          f"{len(bad['contaminants'])} of {len(both)} incidents differ")
    print(f"  flag values in export (not on detail page): {dict(flags)}")

    warn = collections.Counter(w.split(":")[0] for p in details.values() for w in p["warnings"])
    print(f"\nPARSER warnings across detail pages: {dict(warn) or 'none'}")
    for n, p in details.items():
        for w in p["warnings"][:1]:
            bad["parser_warning"].append((n, w))

    for key, items in bad.items():
        for it in items[:args.show]:
            print(f"  [{key}] {it}")


if __name__ == "__main__":
    main()
