"""Power check for fresh test T2 of the planned-work lead in Louisiana (docs/planned_work_test.md), done before any
Louisiana outcome is looked at, and without any Louisiana accident data.

Exposure: the planned-work start dates read from LDEQ documents (data/louisiana/):
set A notices (sections 319 and 309) with a full scheduled start date, plus, as a generous addition, the set C test
variances whose planned work states a start day (word rule class "planned work"). One activity per AI number (as indexed by EDMS, the number the RMP link uses) and start day.
Plants: the AI numbers concerned; years 2009 to 2025 (set A covers 2009 to 2026; RMP data end in 2025).

Accidents are simulated, not observed. Two assumed accident rates, both taken from Texas, not Louisiana:
  typical   0.136 accidents per plant-year: the Texas primary panel's 545 accidents over 216 plants and 18.6 years
  generous  1 accident per plant-year at every plant, far above any Texas average
A planted rate ratio of 1.5 per doubling of planned-work reports in days -7 to -1 (the T2 rule) gives each day's
accident rate; the T2 model (conditional Poisson, plant-year strata, month of year) is fitted to each simulated data
set; power = share of draws whose 95% range lies above 1. 300 draws per scenario.
Rule (docs/planned_work_test.md, changes of 2026-10-05): below 20% power the test is not run.
Output: data/manifests/t2_louisiana_power.json
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
HE = ROOT / "data" / "louisiana"
OUT = ROOT / "data" / "manifests" / "t2_louisiana_power.json"
START, END = pd.Timestamp("2009-01-01"), pd.Timestamp("2025-12-31")


def exposure():
    rows = []
    for r in csv.DictReader(open(HE / "set_A_dates.csv", encoding="utf-8")):
        if r["scheduled_start_date"]:
            rows.append(("A", r["ai_numbers"].split(";")[0], r["scheduled_start_date"]))
    for r in csv.DictReader(open(HE / "set_C_test_dates.csv", encoding="utf-8")):
        if r["activity_start_date"] and r["word_rule_class"] == "planned work":
            rows.append(("C", r["ai_numbers"].split(";")[0], r["activity_start_date"]))
    e = pd.DataFrame(rows, columns=["set", "ai", "day"])
    e["day"] = pd.to_datetime(e.day, errors="coerce")
    e["ai"] = e.ai.str.strip()
    return e.dropna().drop_duplicates(["ai", "day"])


def main():
    e = exposure()
    e_in = e[e.day.between(START, END)]
    days = pd.date_range(START, END, freq="D")
    pan = pd.DataFrame([(a, d) for a in sorted(e.ai.unique()) for d in days], columns=["plant_id", "day"])
    cnt = e_in.groupby(["ai", "day"]).size()
    cnt.index = cnt.index.set_names(["plant_id", "day"])
    pan["E"] = P.windowed(cnt, pan[["plant_id", "day"]], 7, 0, 8)
    pan["planned"] = np.log1p(pan.E)
    pan["year"], pan["moy"] = pan.day.dt.year, pan.day.dt.month
    pan["plant_year"] = pan.plant_id + "_" + pan.year.astype(str)
    res = {"note": __doc__.split("Output:")[0].strip(),
           "activities": {"set_A_with_scheduled_start": int((e.set == "A").sum()),
                          "set_C_test_planned_with_start": int((e.set == "C").sum()),
                          "in_2009_to_2025": len(e_in), "ai_numbers": int(e.ai.nunique())},
           "exposed_plant_days": int((pan.E > 0).sum()), "plant_days": len(pan)}
    b = np.log2(1.5)
    rng = np.random.default_rng(2026)
    for name, per_year in (("typical", 545 / (216 * 18.58)), ("generous", 1.0)):
        base = per_year / 365.0
        lam = base * np.exp(b * pan.planned.values)
        lam *= base * len(pan) / lam.sum()          # keep the overall accident rate at the assumed level
        hits, n_exposed_acc, n_acc = [], [], []
        for i in range(300):
            y = rng.poisson(lam)
            n_acc.append(int(y.sum()))
            n_exposed_acc.append(int(y[pan.E.values > 0].sum()))
            sub = pan.assign(y=y)
            sub = sub[sub.groupby("plant_year").y.transform("sum") > 0]
            if sub.y.sum() == 0 or (sub.E > 0).sum() == 0:
                hits.append(False)
                continue
            try:
                r = P.fit(sub, ["planned"], "plant_year + moy", "poisson")
                t = r["terms"].get("planned")
                hits.append(bool(t and t["ci"][0] > 1))
            except Exception:  # noqa: BLE001  (a fit that cannot be made cannot confirm)
                hits.append(False)
        res[name] = {"accidents_per_plant_year": round(per_year, 3), "draws": 300,
                     "mean_simulated_accidents": round(float(np.mean(n_acc)), 1),
                     "mean_accidents_on_exposed_days": round(float(np.mean(n_exposed_acc)), 2),
                     "power": round(float(np.mean(hits)), 3)}
        print(name, res[name], flush=True)
    res["decision"] = ("not run: power below 20% in both scenarios" if max(res["typical"]["power"], res["generous"]["power"]) < 0.2
                       else "power check passed in at least one scenario: see the T2 note")
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(res["activities"], res["exposed_plant_days"], res["decision"])


if __name__ == "__main__":
    main()
