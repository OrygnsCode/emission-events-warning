"""Re-read every downloaded file and compare it with what the manifests say.

For each record in data/external/MANIFEST.jsonl:
  - file present? (national files that were cut down to Texas and then deleted are reported as "deleted
    after slicing", only if a slice that names that file exists)
  - stored "as served": SHA-256 of the file must equal the recorded one
  - stored "gzip": the file must decompress cleanly and the SHA-256 and size of the decompressed bytes
    must equal the recorded ones
For each slice in data/slices/SLICES.jsonl: file present, SHA-256 equal, gzip valid.
Also: files on disk that no record mentions, and manifest URLs recorded more than once.
Writes data/manifests/download_check.json and prints a summary per source. Exit code 1 if anything is wrong.

Usage: nice python3 src/check_downloads.py [--sources a,b] [--workers 3]
"""
import argparse
import collections
import gzip
import hashlib
import json
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "data" / "external"
SLICES = ROOT / "data" / "slices"
OUT = ROOT / "data" / "manifests" / "download_check.json"


def sha_plain(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest(), path.stat().st_size


def sha_gunzip(path):
    h, n = hashlib.sha256(), 0
    with gzip.open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def check_one(args):
    rel, stored, want_sha, want_bytes = args
    path = EXT / rel
    if not path.exists():
        return rel, "missing", ""
    try:
        sha, n = sha_gunzip(path) if stored == "gzip" else sha_plain(path)
    except (OSError, EOFError, zlib.error) as e:
        return rel, "unreadable", f"{type(e).__name__}: {e}"
    if sha != want_sha:
        return rel, "hash_differs", f"{n} bytes now, {want_bytes} recorded"
    if n != want_bytes:
        return rel, "size_differs", f"{n} vs {want_bytes}"
    return rel, "ok", ""


def check_slice(rec):
    path = SLICES / rec["slice"]
    if not path.exists():
        return rec["slice"], "missing", ""
    try:
        with gzip.open(path, "rb") as f:
            while f.read(1 << 22):
                pass
    except (OSError, EOFError, zlib.error) as e:
        return rec["slice"], "unreadable", str(e)
    sha, _ = sha_plain(path)
    return rec["slice"], "ok" if sha == rec["sha256"] else "hash_differs", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    only = set(filter(None, a.sources.split(",")))
    decided = json.loads((ROOT / "data/manifests/deleted_national_copies.json").read_text())["files"] \
        if (ROOT / "data/manifests/deleted_national_copies.json").exists() else {}
    recs = [json.loads(l) for l in (EXT / "MANIFEST.jsonl").read_text().splitlines() if l.strip()]
    seen, dup = {}, collections.Counter()
    for r in recs:
        dup[r["url"]] += 1
        seen[r["file"]] = r
    dups = {u: c for u, c in dup.items() if c > 1}
    slices = [json.loads(l) for l in (SLICES / "SLICES.jsonl").read_text().splitlines() if l.strip()]
    sliced_urls = {s for rec in slices for s in rec.get("sources", [])}
    jobs = [(r["file"], r.get("stored", "as served"), r["sha256"], r["bytes"]) for r in seen.values()
            if not only or r["source"] in only]
    res = collections.defaultdict(collections.Counter)
    bad, deleted = [], []
    with ProcessPoolExecutor(a.workers) as ex:
        for rel, status, note in ex.map(check_one, jobs, chunksize=8):
            src = rel.split("/", 1)[0]
            if status == "missing" and rel in decided:
                status = "deleted_by_decision"
                deleted.append(rel)
            elif status == "missing" and seen[rel]["url"] in sliced_urls:
                status = "deleted_after_slicing"
                deleted.append(rel)
            res[src][status] += 1
            if status not in ("ok", "deleted_after_slicing", "deleted_by_decision"):
                bad.append({"file": rel, "status": status, "note": note})
        for rel, status, note in ex.map(check_slice, slices, chunksize=4):
            res["slices"][status] += 1
            if status != "ok":
                bad.append({"file": "slices/" + rel, "status": status, "note": note})
    on_disk = {str(p.relative_to(EXT)) for p in EXT.rglob("*") if p.is_file()} - {"MANIFEST.jsonl"}
    on_disk = {p for p in on_disk if not p.startswith("gdelt/") and not p.endswith(".part")}
    unlisted = sorted(on_disk - set(seen))
    if only:
        unlisted = [u for u in unlisted if u.split("/", 1)[0] in only]
    report = {"records": len(recs), "unique_files": len(seen), "per_source": {k: dict(v) for k, v in sorted(res.items())},
              "problems": bad, "deleted_after_slicing": len(deleted), "urls_recorded_twice": len(dups),
              "files_on_disk_not_in_manifest": unlisted[:200], "n_unlisted": len(unlisted)}
    OUT.write_text(json.dumps(report, indent=1) + "\n")
    for k, v in report["per_source"].items():
        print(f"{k:22s} {dict(v)}")
    print(f"\n{len(bad)} problems, {len(unlisted)} unlisted files, {len(dups)} URLs recorded twice, "
          f"{len(deleted)} deleted after slicing (national copies; hashes kept)")
    for b in bad[:30]:
        print("  PROBLEM", b)
    for u in unlisted[:15]:
        print("  unlisted", u)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
