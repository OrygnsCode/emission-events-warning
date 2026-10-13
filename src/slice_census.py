"""Texas rows (fipstate 48) of the Census County Business Patterns county files, 1986 to 2023.

Each file is one comma-separated table whose first column is the state FIPS code, quoted. The header and
every row starting with "48" are kept as they are. Recorded in data/slices/SLICES.jsonl with the SHA-256 of
the cut file; the national zips stay in the manifest with their own hashes.

Usage: python3 src/slice_census.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch_more import EXT, grep_zip_slice, log, slice_done  # noqa: E402

for z in sorted((EXT / "census_cbp").glob("cbp*co.zip")):
    yy = int(z.name[3:5])
    year = 1900 + yy if yy >= 80 else 2000 + yy
    rel = f"census_cbp/cbp_{year}_county_tx.csv.gz"
    if slice_done(rel):
        continue
    rec = next(json.loads(l) for l in (EXT / "MANIFEST.jsonl").read_text().splitlines()
               if f'/{z.name}"' in l and "census_cbp" in l)
    grep_zip_slice(z, rel, '^"48",', rec["url"], 'first column fipstate == "48" (Texas)')
log("census slices done")
