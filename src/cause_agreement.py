"""Agreement between the frozen cause rules and the author's hand coding of 400 random events (plan section 4).

The author coded each event's cause text with the codebook (docs/cause_codebook.md) without seeing what the rules
said. Reported: percent agreement and Cohen's kappa for the primary cause (9 categories), for the three groups used
in the process-control contrast (plan D4: process control = equipment, instrument, upset or operator/procedure;
outside or planned = weather, third party, power or electrical, maintenance or startup; unknown), and for each
category tick and report-status flag separately.
Output: data/manifests/cause_agreement.json
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "manifests" / "cause_agreement.json"
GROUP = {"equipment": "process", "instrument": "process", "upset": "process", "operator": "process",
         "weather": "outside", "third_party": "outside", "power": "outside", "maintenance_startup": "outside",
         "unknown": "unknown"}
FLAGS = ["cause_weather", "cause_third_party", "cause_power", "cause_operator", "cause_instrument", "cause_equipment",
         "cause_upset", "cause_maintenance_startup", "status_duplicate", "status_not_reportable",
         "status_filed_in_error"]


def kappa(a, b):
    a, b = pd.Series(a).astype(str).values, pd.Series(b).astype(str).values
    po = (a == b).mean()
    cats = sorted(set(a) | set(b))
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return round(float(po), 3), round(float((po - pe) / (1 - pe)), 3) if pe < 1 else None


def main():
    hand = pd.read_csv(ROOT / "data/manual/cause_hand_coding_author.csv", dtype=str)
    rule = pd.read_csv(ROOT / "data/derived/causes.csv.gz", dtype={"incident": str})
    m = hand.merge(rule, on="incident", how="left", suffixes=("_hand", "_rule"))
    assert m.primary_cause_rule.notna().all() and len(m) == 400
    res = {"note": __doc__.split("Output:")[0].strip(), "n_events": len(m)}
    po, k = kappa(m.primary_cause_hand, m.primary_cause_rule)
    res["primary_cause"] = {"agreement": po, "kappa": k}
    po, k = kappa(m.primary_cause_hand.map(GROUP), m.primary_cause_rule.map(GROUP))
    res["three_groups"] = {"agreement": po, "kappa": k}
    res["confusion_primary"] = pd.crosstab(m.primary_cause_hand, m.primary_cause_rule).to_dict()
    flags = {}
    for f in FLAGS:
        rf = "cause_says_unknown" if f == "cause_unknown" else f
        h = m[f + "_hand"].str.lower().eq("true")
        r = m[rf + "_rule"].astype(str).str.lower().eq("true")
        po, k = kappa(h, r)
        flags[f] = {"agreement": po, "kappa": k, "hand_yes": int(h.sum()), "rules_yes": int(r.sum())}
    res["flags"] = flags
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("note", "confusion_primary")}, indent=1))


if __name__ == "__main__":
    main()
