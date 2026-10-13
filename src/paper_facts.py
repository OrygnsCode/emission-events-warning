"""Descriptive counts the paper quotes that were not stored elsewhere (plan D16): reports and kept events at
RMP-linked plants, accidents that follow an earlier accident at the same plant within 120 days, and accidents at
plants that reported no unplanned event during their study period (the difference between the 545 accidents of the
main test and the 472 in the event-rate figure).
Output: data/manifests/paper_facts.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "paper_facts.json"


def main():
    plants, ev, acc, *_ = P.tables("v2")
    linked = set(plants.loc[plants.linked, "plant_id"])
    cnt = P.event_counts(ev)
    inc = pd.read_csv(ROOT / "data/master/incidents.csv.gz", dtype=str, usecols=["RN"])
    rn_plant = ev.dropna(subset=["plant_id"])[["rn", "plant_id"]].drop_duplicates().set_index("rn").plant_id
    a = acc[acc.plant_id.isin(linked)].sort_values(["plant_id", "date"])
    gap = (a.date - a.groupby("plant_id").date.shift(1)).dt.days
    inwin = a.date.between(P.h1.STUDY_START, "2021-12-31")
    pic = json.loads((ROOT / "data/manifests/h1_primary_result.json").read_text())["primary_end_2021"]
    res = {"note": __doc__.split("Output:")[0].strip(),
           "reports_total": len(inc),
           "reports_at_rmp_linked_plants": int(inc.RN.map(rn_plant).isin(linked).sum()),
           "events_in_exposure_series": int(cnt.sum()),
           "events_at_rmp_linked_plants": int(cnt[cnt.index.get_level_values(0).isin(linked)].sum()),
           "accidents_in_window": int(inwin.sum()),
           "accidents_within_120_days_after_earlier_at_plant": int((gap.between(1, 120) & inwin).sum()),
           "accidents_in_event_rate_figure": pic["picture"]["accidents_used"],
           "accidents_at_plants_without_events_in_study_period": int(inwin.sum()) - pic["picture"]["accidents_used"]}
    res["share_removed_of_linked_events_pct"] = round(269 / res["events_at_rmp_linked_plants"] * 100, 2)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(res)


if __name__ == "__main__":
    main()
