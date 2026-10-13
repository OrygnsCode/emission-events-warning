"""How far the National Response Center replication (H4) overlaps the RMP accident data (plan D16 item 5): of the
sites and report days in the H4 panel (window ending 2021), how many are in RMP-linked plants, and how many report
days fall within 3 days of an RMP accident at the same plant.
Output: data/manifests/h4_overlap.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402
import phase5_h4_o6 as H  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "h4_overlap.json"


def main():
    plants, ev, acc, *_ = P.tables("v2")
    _, pan = H.h4(ev, H.linked("nrc"), "2021-12-31")
    od = pan[pan.y == 1][["plant_id", "day"]]
    rn_plant = ev.dropna(subset=["plant_id"])[["rn", "plant_id"]].drop_duplicates().set_index("rn").plant_id
    linked = set(plants.loc[plants.linked, "plant_id"])
    sites = pd.Series(od.plant_id.unique())
    a = acc[acc.plant_id.isin(linked)]
    near = {(p, d + pd.Timedelta(days=k)) for p, d in zip(a.plant_id, a.date.dt.normalize()) for k in range(-3, 4)}
    res = {"note": __doc__.split("Output:")[0].strip(),
           "sites": len(sites), "sites_in_rmp_linked_plants": int(sites.map(rn_plant).isin(linked).sum()),
           "report_days": len(od), "report_days_in_rmp_linked_plants": int(od.plant_id.map(rn_plant).isin(linked).sum()),
           "report_days_within_3_days_of_rmp_accident": int(sum((rn_plant.get(u), d) in near
                                                               for u, d in zip(od.plant_id, od.day)))}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(res)


if __name__ == "__main__":
    main()
