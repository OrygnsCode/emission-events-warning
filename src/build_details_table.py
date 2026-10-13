"""One row per saved TCEQ detail page, with every single-valued field the parser reads (data/raw/details).

List fields are kept as counts (facilities, emission points) or joined text (process units); parser warnings and
fields outside the template are kept as JSON text.

Output: data/derived/details_table.parquet
Usage:  python3 src/build_details_table.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from details_store import iter_details  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "derived" / "details_table.parquet"


def main():
    rows = []
    for _, p in iter_details():
        r = {k: v for k, v in p.items() if not isinstance(v, (list, dict))}
        r["n_facilities"] = len(p.get("facilities") or [])
        r["n_emission_points"] = len(p.get("emission_points") or [])
        pu = p.get("process_units")
        r["process_units"] = "; ".join(pu or []) if isinstance(pu, list) else str(p.get("process_units", ""))
        r["warnings"] = json.dumps(p.get("warnings")) if p.get("warnings") else ""
        r["extra"] = json.dumps(p.get("extra")) if p.get("extra") else ""
        rows.append(r)
    d = pd.DataFrame(rows)
    d.to_parquet(OUT, index=False)
    print(d.shape)


if __name__ == "__main__":
    main()
