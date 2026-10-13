"""Apply the written cause and unit-type rules (rules/cause_rules.json) to TCEQ events.

No machine learning: each category is a list of regular expressions. A cause
gets a yes/no flag for every category it matches; its primary cause is the
first match in the fixed order in the rules file, or "unknown" if none match.
Unit types are yes/no flags from emission point, facility and process unit names.

Usage:
  python3 src/classify_causes.py dev       # summary and examples on the development sample
  python3 src/classify_causes.py all       # classify every saved page -> data/derived/causes.csv.gz
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RULES = json.loads((ROOT / "rules" / "cause_rules.json").read_text())
COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in RULES["cause"].items()}
UNKNOWN = [re.compile(p, re.I) for p in RULES["unknown_phrases"]]
UNITS = {k: [re.compile(p, re.I) for p in v] for k, v in RULES["unit"].items()}
STATUS = {k: [re.compile(p, re.I) for p in v] for k, v in RULES["report_status"].items()}


def classify_text(text):
    text = text or ""
    flags = {k: any(p.search(text) for p in pats) for k, pats in COMPILED.items()}
    primary = next((k for k in RULES["cause_order"] if flags[k]), "unknown")
    flags["says_unknown"] = any(p.search(text) for p in UNKNOWN)
    return primary, flags


def classify_units(names):
    joined = " | ".join(n for n in names if n)
    return {k: any(p.search(joined) for p in pats) for k, pats in UNITS.items()}


def row_for(incident, page):
    primary, flags = classify_text(page.get("cause", ""))
    names = (page.get("process_units", []) + [f["name"] for f in page.get("facilities", [])]
             + [e["name"] for e in page.get("emission_points", [])])
    units = classify_units(names)
    text = page.get("cause", "") or ""
    out = {"incident": incident, "primary_cause": primary}
    out.update({f"status_{k}": any(p.search(text) for p in pats) for k, pats in STATUS.items()})
    out.update({f"cause_{k}": v for k, v in flags.items()})
    out.update({f"unit_{k}": v for k, v in units.items()})
    return out


def main():
    sys.path.insert(0, str(ROOT / "src"))
    from details_store import iter_details
    mode = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if mode == "dev":
        wanted = {int(x) for x in (ROOT / "data/samples/cause_dev_sample.txt").read_text().split()}
        rows, texts = [], {}
        for n, p in iter_details(wanted):
            rows.append(row_for(n, p))
            texts[n] = p.get("cause", "")
        df = pd.DataFrame(rows)
        print("primary cause shares:", df.primary_cause.value_counts(normalize=True).round(3).to_dict())
        print("flag shares:", {c[6:]: round(df[c].mean(), 3) for c in df if c.startswith("cause_")})
        print("report status shares:", {c[7:]: round(df[c].mean(), 3) for c in df if c.startswith("status_")})
        print("unit flag shares:", {c[5:]: round(df[c].mean(), 3) for c in df if c.startswith("unit_")})
        df["text"] = df.incident.map(texts)
        df.to_csv(ROOT / "data/derived/causes_dev.csv", index=False)
    else:
        rows = [row_for(n, p) for n, p in iter_details()]
        pd.DataFrame(rows).to_csv(ROOT / "data/derived/causes.csv.gz", index=False)
        print(f"classified {len(rows)} pages")


if __name__ == "__main__":
    main()
