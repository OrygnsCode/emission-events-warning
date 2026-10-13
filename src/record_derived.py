"""Add manifest records for index files that our own scripts wrote while downloading (not downloaded as such).

Files: the fenceline reports index, the TCEQ monitor site-year inventory, the Federal Register index of
documents touching 40 CFR part 68. Each gets source "derived by script", a SHA-256 and the time. Skips files
already recorded. Usage: python3 src/record_derived.py
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

EXT = Path(__file__).resolve().parent.parent / "data/external"
M = EXT / "MANIFEST.jsonl"
FILES = {"epa_fenceline/reports_index.csv": "src/fetch_fenceline.py (search results table)",
         "tceq_monitors/inventory_site_years.csv": "src/fetch_tceq_monitors.py (site and year inventory)",
         "regulatory_text/fr_40cfr68_index.json": "src/fetch_more.py tceq_more (Federal Register API listing)"}
have = {json.loads(l)["file"] for l in M.read_text().splitlines() if l.strip()}
with open(M, "a") as m:
    for rel, how in FILES.items():
        p = EXT / rel
        if rel in have or not p.exists():
            continue
        b = p.read_bytes()
        m.write(json.dumps({"source": rel.split("/")[0], "url": f"derived by {how}", "file": rel, "bytes": len(b),
                            "sha256": hashlib.sha256(b).hexdigest(), "stored": "as served", "last_modified": None,
                            "downloaded_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
        print("recorded", rel)
