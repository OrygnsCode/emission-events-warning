"""Finish the GDELT strict-use collection (rules/gdelt_url_rules.json).

Reads data/external/gdelt/hits/<stream>/<YYYYMM>.tsv (raw, kept as written, never edited) and writes:
  data/external/gdelt/hits_manifest.tsv        rows and SHA-256 of every raw hits file
  data/derived/gdelt_hits_dedup.csv.gz         every hit once (stream, date, link, file) with the rule flags
  data/derived/gdelt_texas_candidates.csv.gz   the subset whose link has a Texas place word or comes from a
                                               Texas news website (flags txplace / txsite), still unchecked
  data/manifests/gdelt_summary.json            counts, coverage and gaps, for the report
Duplicates exist only because two copies of the downloader overlapped for a few minutes; a duplicate is a row
with the same stream, date, link and source file. Hand checks of the candidates come later.

Usage: python3 src/finalize_gdelt.py
"""
import collections
import csv
import datetime as dt
import glob
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G = ROOT / "data/external/gdelt"
OUT = ROOT / "data/derived"
OUT.mkdir(parents=True, exist_ok=True)
STREAMS = ("gdelt1_events_daily", "gdelt1_gkg_daily", "gdelt2_gkg")


def main():
    seen, rows, tx = set(), 0, 0
    per_year = collections.defaultdict(lambda: collections.Counter())
    with open(G / "hits_manifest.tsv", "w") as m, gzip.open(OUT / "gdelt_hits_dedup.csv.gz", "wt", newline="") as a, \
            gzip.open(OUT / "gdelt_texas_candidates.csv.gz", "wt", newline="") as b:
        m.write("file\trows\tsha256\n")
        wa, wb = csv.writer(a, lineterminator="\n"), csv.writer(b, lineterminator="\n")
        head = ["stream", "date", "collection", "website", "link", "rules", "source_file"]
        wa.writerow(head)
        wb.writerow(head)
        for s in STREAMS:
            for f in sorted(glob.glob(str(G / "hits" / s / "*.tsv"))):
                data = Path(f).read_bytes()
                lines = data.decode("utf-8", "replace").splitlines()[1:]
                m.write(f"{Path(f).relative_to(G)}\t{len(lines)}\t{hashlib.sha256(data).hexdigest()}\n")
                for l in lines:
                    p = l.split("\t")
                    k = (s, p[0], p[3], p[5])
                    if len(p) != 6 or k in seen:
                        continue
                    seen.add(k)
                    row = [s] + p
                    wa.writerow(row)
                    rows += 1
                    year = p[0][:4]
                    per_year[s][year] += 1
                    if "txplace" in p[4] or "txsite" in p[4]:
                        wb.writerow(row)
                        tx += 1
                        per_year[s + "_texas"][year] += 1
    summ = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "hits_after_dedup": rows,
            "texas_candidates": tx, "hits_per_year": {k: dict(sorted(v.items())) for k, v in per_year.items()}}
    for s in STREAMS:
        done = (G / f"done_{s}.tsv").read_text().splitlines()[1:]
        summ[s] = {"files_processed": len(done), "rows_scanned": sum(int(x.split("\t")[4]) for x in done),
                   "bytes_downloaded": sum(int(x.split("\t")[1]) for x in done)}
    miss = G / "missing_on_server_gdelt2_gkg.tsv"
    if miss.exists():
        urls = miss.read_text().splitlines()[1:]
        summ["gdelt2_gkg_files_not_on_server"] = len(urls)
        summ["gdelt2_gkg_missing_by_day"] = dict(collections.Counter(u.rsplit("/", 1)[1][:8] for u in urls).most_common(10))
    (ROOT / "data/manifests/gdelt_summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summ.items() if k != "hits_per_year"}, indent=1))


if __name__ == "__main__":
    main()
