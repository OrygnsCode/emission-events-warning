"""Polite, resumable, adaptive crawler for TCEQ emission event pages.

Two endpoints per incident:
  details  incident detail page (HTML)
  export   per-incident contaminant spreadsheet (carries the "estimated" and
           "amount unknown" flags that the detail page does not show)

Every response is stored byte for byte in gzip JSONL shards, with its SHA-256,
so parsing can be redone without downloading again. A SQLite manifest records
one row per (endpoint, incident). A row only reads 'done' after its shard is
safely on disk, so a crash at any point just means a few pages are fetched
again. Run the same command again to resume.

The request rate adapts: it starts low, climbs toward --max-rate while the
server answers quickly, and halves (with a pause on throttling) when latency
rises or errors appear.

Usage:
    python3 src/crawl.py --endpoint details
    python3 src/crawl.py --endpoint export
    python3 src/crawl.py --endpoint details --sample 200 --seed 1   # test run
"""
import argparse
import base64
import collections
import datetime as dt
import gzip
import hashlib
import json
import os
import queue
import random
import re
import signal
import sqlite3
import statistics
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_detail import parse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE_DB = DATA / "state" / "crawl.sqlite"
EXPORTS = DATA / "raw" / "search_exports"
BASE = "https://www2.tceq.texas.gov/oce/eer/index.cfm"
FUSE = {"details": "main.getDetails", "export": "main.emissiondwnld"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SHARD_SIZE = 250
MAX_TRIES = 5
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def now_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- state
def open_db():
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STATE_DB)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (incident INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS fetch (
            endpoint TEXT, incident INTEGER, status TEXT, attempts INTEGER DEFAULT 0,
            http_status INTEGER, bytes INTEGER, sha256 TEXT, fetched_utc TEXT,
            latency_ms INTEGER, shard TEXT, note TEXT,
            PRIMARY KEY (endpoint, incident));
    """)
    return db


def load_master(db):
    """Union of every incident number in the saved search exports."""
    nums = set()
    for f in sorted(EXPORTS.glob("*.xls")):
        df = pd.read_excel(f, usecols=["INCIDENT NO."])
        nums.update(int(x) for x in df["INCIDENT NO."].dropna())
    db.executemany("INSERT OR IGNORE INTO incidents VALUES (?)", [(n,) for n in sorted(nums)])
    db.commit()
    return len(nums)


def pending(db, endpoint):
    rows = db.execute("""
        SELECT i.incident FROM incidents i
        LEFT JOIN fetch f ON f.incident = i.incident AND f.endpoint = ?
        WHERE f.status IS NULL OR f.status NOT IN ('done', 'not_found')
        ORDER BY i.incident""", (endpoint,)).fetchall()
    return [r[0] for r in rows]


# ------------------------------------------------------------ rate control
class Limiter:
    """Shared pacing: spaces request starts 1/rate apart; supports global pauses."""

    def __init__(self, rate):
        self.rate = rate
        self.next = time.monotonic()
        self.pause_until = 0.0
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            t = max(self.next, now, self.pause_until)
            self.next = t + 1.0 / self.rate
        if t > now:
            time.sleep(t - now)

    def pause(self, seconds):
        with self.lock:
            self.pause_until = max(self.pause_until, time.monotonic() + seconds)


class Controller:
    """Additive increase, multiplicative decrease, driven by latency and errors."""

    def __init__(self, limiter, start_rate, max_rate):
        self.lim, self.max_rate = limiter, max_rate
        self.lim.rate = start_rate
        self.recent = collections.deque(maxlen=40)   # latencies (ms)
        self.baseline = None
        self.base_samples = []
        self.since = 0
        self.bad = 0
        self.cooldown_until = 0.0
        self.lock = threading.Lock()
        self.backoffs = 0

    def record(self, latency_ms, kind):
        with self.lock:
            if kind == "ok":
                self.recent.append(latency_ms)
                if self.baseline is None:
                    self.base_samples.append(latency_ms)
                    if len(self.base_samples) >= 60:
                        self.baseline = statistics.median(self.base_samples)
            else:
                self.bad += 1
            self.since += 1
            if kind == "throttle":
                self.lim.pause(30)
            if self.since < 20:
                return
            self.since = 0
            med = statistics.median(self.recent) if self.recent else None
            slow = self.baseline and med and med > 2.0 * self.baseline
            if self.bad or slow:
                old = self.lim.rate
                # real failures halve the rate; mere latency creep trims it by 30%
                self.lim.rate = max(1.0, self.lim.rate * (0.5 if self.bad else 0.7))
                self.cooldown_until = time.monotonic() + (60 if self.bad else 30)
                self.backoffs += 1
                self.recent.clear()  # judge the new rate on fresh samples, not the slow ones
                print(f"{now_utc()} BACKOFF {old:.1f} -> {self.lim.rate:.1f}/s: window median "
                      f"{med and int(med)} ms, baseline {self.baseline and int(self.baseline)} ms, "
                      f"failed requests in window {self.bad}", flush=True)
            elif time.monotonic() > self.cooldown_until and (
                    self.baseline is None or (med and med < 1.5 * self.baseline)):
                self.lim.rate = min(self.max_rate, self.lim.rate + 0.5)
            self.bad = 0

    def median_ms(self):
        with self.lock:
            return statistics.median(self.recent) if self.recent else None


# ------------------------------------------------------------------ fetching
def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


def classify(endpoint, incident, r):
    """Return (status, note). status is done, not_found, or error."""
    if r.status_code == 302:
        loc = r.headers.get("Location", "")
        if "message=badincid" in loc:
            return "not_found", None
        return "error", f"unexpected redirect {loc[:120]}"
    if r.status_code != 200:
        return "error", f"http {r.status_code}"
    body = r.content
    if endpoint == "details":
        got = parse(body)
        if got.get("incident") != str(incident):
            return "error", f"page incident {got.get('incident')!r} != {incident}"
        return "done", ("; ".join(got["warnings"]) or None)
    if not body.startswith(OLE_MAGIC):
        return "error", "export is not an xls file"
    if f"incident_{incident}_" not in r.headers.get("Content-Disposition", ""):
        return "error", f"export filename mismatch: {r.headers.get('Content-Disposition')}"
    return "done", None


def fetch(sess, endpoint, incident, limiter, ctl, stop):
    url = f"{BASE}?fuseaction={FUSE[endpoint]}&target={incident}"
    note = None
    for attempt in range(1, MAX_TRIES + 1):
        if stop.is_set():
            return {"incident": incident, "status": "error", "attempts": attempt - 1,
                    "note": "stopped", "http": None, "body": None, "ms": None, "headers": {}}
        limiter.acquire()
        t0 = time.monotonic()
        try:
            r = sess.get(url, allow_redirects=False, timeout=(10, 60))
        except requests.Timeout as e:  # a slow server is a real warning sign
            ms = int((time.monotonic() - t0) * 1000)
            ctl.record(ms, "error")
            note = f"{type(e).__name__}: {str(e)[:100]}"
            print(f"{now_utc()} request problem: incident {incident} attempt {attempt}: {note}",
                  flush=True)
            time.sleep(min(60, 2 ** attempt + random.random()))
            continue
        except requests.ConnectionError as e:
            # The network proxy drops long-lived connections after 20 to 35 minutes; that says
            # nothing about TCEQ's load, so retry on a fresh connection without slowing down.
            note = f"{type(e).__name__}: {str(e)[:100]}"
            print(f"{now_utc()} connection dropped: incident {incident} attempt {attempt}: {note}",
                  flush=True)
            time.sleep(1 + random.random())
            continue
        ms = int((time.monotonic() - t0) * 1000)
        if r.status_code in (403, 407):
            stop.set()  # policy or access denial: do not push on
            return {"incident": incident, "status": "error", "attempts": attempt,
                    "note": f"http {r.status_code} (stopping)", "http": r.status_code,
                    "body": None, "ms": ms, "headers": {}}
        status, note = classify(endpoint, incident, r)
        if status in ("done", "not_found"):
            ctl.record(ms, "ok")
            return {"incident": incident, "status": status, "attempts": attempt, "note": note,
                    "http": r.status_code, "body": r.content if status == "done" else b"",
                    "ms": ms,
                    "headers": {"content_disposition": r.headers.get("Content-Disposition")}}
        throttled = r.status_code in (429, 503)
        print(f"{now_utc()} request problem: incident {incident} attempt {attempt} "
              f"http {r.status_code}: {note}", flush=True)
        ctl.record(ms, "throttle" if throttled else "error")
        time.sleep(min(120, (2 ** attempt) * (3 if throttled else 1) + random.random()))
    return {"incident": incident, "status": "error", "attempts": MAX_TRIES, "note": note,
            "http": None, "body": None, "ms": None, "headers": {}}


SESSION_MAX_AGE = 600  # seconds; well under the proxy's 20 to 35 minute connection lifetime


def worker(endpoint, todo, out, limiter, ctl, stop):
    sess, born = make_session(), time.monotonic()
    while not stop.is_set():
        try:
            incident = todo.get_nowait()
        except queue.Empty:
            return
        if time.monotonic() - born > SESSION_MAX_AGE:
            sess.close()
            sess, born = make_session(), time.monotonic()
        out.put(fetch(sess, endpoint, incident, limiter, ctl, stop))


# ------------------------------------------------------------------ storage
def write_shard(endpoint, items):
    d = DATA / "raw" / endpoint
    d.mkdir(parents=True, exist_ok=True)
    name = f"shard_{time.time_ns()}.jsonl.gz"
    tmp = d / (name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps({
                "incident": it["incident"], "endpoint": endpoint,
                "fetched_utc": it["fetched_utc"], "http_status": it["http"],
                "sha256": it["sha256"], "headers": it["headers"],
                "body_b64": base64.b64encode(it["body"]).decode("ascii"),
            }) + "\n")
    tmp.rename(d / name)
    return name


def save(db, endpoint, results):
    """Write a shard for finished pages, then update the manifest in one commit."""
    done = [r for r in results if r["status"] == "done"]
    for r in results:
        r["fetched_utc"] = now_utc()
        r["sha256"] = hashlib.sha256(r["body"]).hexdigest() if r["body"] else None
    shard = write_shard(endpoint, done) if done else None
    rows = []
    for r in results:
        rows.append((endpoint, r["incident"], r["status"], r["attempts"], r["http"],
                     len(r["body"]) if r["body"] else 0, r["sha256"], r["fetched_utc"],
                     r["ms"], shard if r["status"] == "done" else None, r["note"]))
    db.executemany("""INSERT OR REPLACE INTO fetch
        (endpoint, incident, status, attempts, http_status, bytes, sha256, fetched_utc,
         latency_ms, shard, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows)
    db.commit()


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", choices=list(FUSE), required=True)
    ap.add_argument("--max-rate", type=float, default=10.0, help="ceiling, requests/second")
    ap.add_argument("--start-rate", type=float, default=2.0)
    ap.add_argument("--inflight", type=int, default=16, help="max simultaneous requests")
    ap.add_argument("--sample", type=int, help="test on a random sample of this size")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--incidents-file", help="only fetch the incident numbers listed in this file")
    args = ap.parse_args()

    db = open_db()
    total = load_master(db)
    todo_list = pending(db, args.endpoint)
    if args.incidents_file:
        wanted = {int(x) for x in Path(args.incidents_file).read_text().split()}
        todo_list = [n for n in todo_list if n in wanted]
    if args.sample:
        random.Random(args.seed).shuffle(todo_list)
        todo_list = sorted(todo_list[:args.sample])
    print(f"{now_utc()} master list {total} incidents; {len(todo_list)} to fetch "
          f"from {args.endpoint}", flush=True)
    if not todo_list:
        return

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    todo, out = queue.Queue(), queue.Queue()
    for n in todo_list:
        todo.put(n)
    limiter = Limiter(args.start_rate)
    ctl = Controller(limiter, args.start_rate, args.max_rate)
    threads = [threading.Thread(target=worker, args=(args.endpoint, todo, out, limiter, ctl, stop),
                                daemon=True) for _ in range(args.inflight)]
    for t in threads:
        t.start()

    buf, got, errors = [], 0, 0
    t_start = last_print = time.monotonic()
    while got < len(todo_list):
        try:
            res = out.get(timeout=1)
        except queue.Empty:
            if stop.is_set() and not any(t.is_alive() for t in threads) and out.empty():
                break
            continue
        got += 1
        errors += res["status"] == "error"
        buf.append(res)
        if len(buf) >= SHARD_SIZE:
            save(db, args.endpoint, buf)
            buf = []
        if time.monotonic() - last_print > 30:
            last_print = time.monotonic()
            elapsed = last_print - t_start
            rate = got / elapsed
            eta = (len(todo_list) - got) / rate / 3600 if rate else float("inf")
            med = ctl.median_ms()
            print(f"{now_utc()} {got}/{len(todo_list)} fetched, {errors} errors, "
                  f"target {limiter.rate:.1f}/s, actual {rate:.1f}/s, median "
                  f"{med and int(med)} ms, backoffs {ctl.backoffs}, eta {eta:.1f} h",
                  flush=True)
    if buf:
        save(db, args.endpoint, buf)
    counts = db.execute("SELECT status, COUNT(*) FROM fetch WHERE endpoint=? GROUP BY status",
                        (args.endpoint,)).fetchall()
    print(f"{now_utc()} finished pass. manifest for {args.endpoint}: {dict(counts)}", flush=True)
    if stop.is_set():
        print("stopped early; run the same command to resume", flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
