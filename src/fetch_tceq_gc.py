"""Download TCEQ hourly organics (benzene 45201, 1,3-butadiene 43218, total non-methane organics 43102), plan D6 item 4.

The by-pollutant daily pages used to find H2S sites list no rows for these instruments, so discovery here reads the
yearly summary form of every site-instrument entry in the monthly report's site list (462 entries) for every year
2003 to 2021. Each form lists every parameter that entry measured that year with its months. Entries with any of the
three codes then get their monthly hourly pages (every parameter of the month, including on-site wind).
Same pages, storage and manifest as src/fetch_tceq_monitors.py; parallel connections.

Usage: python3 src/fetch_tceq_gc.py [--workers 6] [--plan]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_external as fx  # noqa: E402
import fetch_tceq_monitors as tm  # noqa: E402

PARAMS = ["45201", "43218", "43102"]
START, END = (2003, 1), (2021, 12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--plan", action="store_true")
    a = ap.parse_args()
    tm._workers[0] = a.workers
    tm.INV_NAME = "inventory_gc_site_years.csv"
    opts = tm.site_options()
    seen = {(p, cams): {(y, 1) for y in range(START[0], END[0] + 1)} for cams in opts for p in PARAMS[:1]}
    rows = tm.inventory(seen, PARAMS, START, END, opts, set())
    tm.write_inventory(rows)
    jobs = tm.month_jobs(rows)
    sites = sorted({r["cams"] for r in rows}, key=int)
    fx.log(f"organics: {len(sites)} site-instrument entries, {len(jobs)} site-months; CAMS {', '.join(sites)}")
    if a.plan:
        return
    tm.pmap(tm.monthly, jobs)
    fx.log(f"{tm._count[0]} network requests")


if __name__ == "__main__":
    main()
