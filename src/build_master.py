"""Build the master incident list from the saved search exports.

The 16 by-region exports hold every incident in the database whatever its
dates. They are the base. This script asserts that every incident found by the
date-based lists is also in the region lists, then writes one compact file.

Output: data/master/incidents.csv.gz
Usage:  python3 src/build_master.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "search_exports"
OUT = ROOT / "data" / "master" / "incidents.csv.gz"


def read(pattern):
    frames = [pd.read_excel(f) for f in sorted(SRC.glob(pattern))]
    return pd.concat(frames, ignore_index=True)


def main():
    region = read("region_*.xls")
    if region["INCIDENT NO."].duplicated().any():
        sys.exit("an incident appears in more than one region list")
    dates = pd.concat([read("start_*.xls"), read("end_*.xls")])
    missing = set(dates["INCIDENT NO."]) - set(region["INCIDENT NO."])
    if missing:
        sys.exit(f"{len(missing)} incidents in date lists are not in the region lists: {sorted(missing)[:10]}")
    region = region.sort_values("INCIDENT NO.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    region.to_csv(OUT, index=False, compression="gzip")
    print(f"wrote {len(region)} incidents to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
