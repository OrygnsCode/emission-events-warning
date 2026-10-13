"""Download TCEQ's own enforcement and complaint records from the Texas Open Data Portal.

Datasets (all Texas, September 2010 to present, updated quarterly):
  complaints            tdzs-qqjn
  notices of violation  mwzi-gyw7
  violation citations   gyd4-wuys
  notices of enforcement rua3-iswk
Each is saved with its column descriptions, and recorded with a SHA-256 in
data/external/MANIFEST.jsonl (same manifest as the other outside datasets).

Usage: python3 src/fetch_tceq_open_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_external as fx  # noqa: E402

DATASETS = {"complaints": "tdzs-qqjn", "notices_of_violation": "mwzi-gyw7",
            "violation_citations": "gyd4-wuys", "notices_of_enforcement": "rua3-iswk"}


def main():
    fx.EXT.mkdir(parents=True, exist_ok=True)
    for name, ds in DATASETS.items():
        fx.download("tceq_open_data", f"https://data.texas.gov/api/views/{ds}/rows.csv?accessType=DOWNLOAD",
                    f"{name}_{ds}.csv")
        fx.download("tceq_open_data", f"https://data.texas.gov/api/views/{ds}.json", f"{name}_{ds}_columns.json")


if __name__ == "__main__":
    main()
