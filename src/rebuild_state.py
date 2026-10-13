"""Rebuild the crawl manifest from saved shards, so the crawler can resume on a fresh machine.

Restore flow on a new machine:
  1. git clone the repo, then unpack the archive of TCEQ pages that comes with the paper (Zenodo) in its folder,
     which gives data/raw/details and data/raw/export
  2. python3 src/rebuild_state.py        (marks every saved page as done)
  3. python3 src/crawl.py --endpoint details   (fetches only what is still missing)

Usage: python3 src/rebuild_state.py [--db path]   (default: data/state/crawl.sqlite)
"""
import argparse
import base64
import gzip
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl import STATE_DB, DATA, open_db  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(STATE_DB))
    args = ap.parse_args()

    import crawl
    crawl.STATE_DB = Path(args.db)
    db = open_db()
    added = bad = 0
    for endpoint in ("details", "export"):
        for shard in sorted((DATA / "raw" / endpoint).glob("shard_*.jsonl.gz")):
            rows = []
            with gzip.open(shard, "rt", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    body = base64.b64decode(rec["body_b64"])
                    if hashlib.sha256(body).hexdigest() != rec["sha256"]:
                        bad += 1
                        continue
                    rows.append((endpoint, rec["incident"], "done", 1, rec["http_status"], len(body),
                                 rec["sha256"], rec["fetched_utc"], None, shard.name,
                                 "rebuilt from shard"))
            db.executemany("""INSERT OR IGNORE INTO fetch (endpoint, incident, status, attempts,
                http_status, bytes, sha256, fetched_utc, latency_ms, shard, note)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows)
            added += len(rows)
    db.commit()
    print(f"rebuilt {added} rows into {args.db}; {bad} records failed their hash check")


if __name__ == "__main__":
    main()
