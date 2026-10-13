"""Phase 5 diagnostic (D9, exploratory): what the plants' own RMP accident records say about the accidents that had
planned work (maintenance, startup, shutdown reports to TCEQ) starting in the 7 days before, compared with the other
accidents. RMP has no field for the unit's operating state; the closest are the contributing-factor boxes
(maintenance, upset condition, improper procedure, human error and others) and the initiating event. The free-text
"other" fields are only searched for the words start-up, startup, shutdown, shut down, turnaround, restart and
commissioning, and only counts are kept (no text is stored or shown). Accidents: the primary H1 set (full links,
merged duplicates, at-risk days, June 2003 to 2021). Output: data/manifests/phase5_diag_planned_rmp.json
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_planned as D  # noqa: E402
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_planned_rmp.json"
CF = ["CF_EquipmentFailure", "CF_HumanError", "CF_ImproperProcedure", "CF_Overpressurization", "CF_UpsetCondition",
      "CF_BypassCondition", "CF_Maintenance", "CF_ProcessDesignFailure", "CF_UnsuitableEquipment", "CF_UnusualWeather",
      "CF_ManagementError"]
WORDS = re.compile(r"START[\s-]?UP|SHUT[\s-]?DOWN|TURN[\s-]?AROUND|RE[\s-]?START|COMMISSION", re.I)


def main():
    plants, ev, acc, *_ = P.tables("v2")
    pan = P.h1_run(keep_panel=True)["panel"]            # primary panel: at-risk days of plant-years with accidents
    at_risk = set(zip(pan.plant_id, pan.day))
    linked = set(plants.loc[plants.linked, "plant_id"])
    a = acc[acc.plant_id.isin(linked) & acc.date.between(P.h1.STUDY_START, "2021-12-31")].copy()
    a["day"] = a.date.dt.normalize()
    a = a[[(p, d) in at_risk for p, d in zip(a.plant_id, a.day)]]
    e = D.planned_reports(ev)
    starts = e.groupby("plant_id").day.apply(lambda s: s.values.astype("datetime64[D]").astype(np.int64))
    def n_before(p, d):
        s = starts.get(p)
        if s is None:
            return 0
        t = np.datetime64(d, "D").astype(np.int64)
        return int(((s >= t - 7) & (s <= t - 1)).sum())
    a["planned_before"] = [n_before(p, d) for p, d in zip(a.plant_id, a.day)]
    r = pd.read_csv(P.h1.ROOT / "data/slices/rmp_accidents_tx.csv.gz", dtype=str, keep_default_na=False,
                    usecols=["AccidentHistoryID", "InitiatingEvent", "CF_Other", "OtherReleaseSource"] + CF)
    r = r.drop_duplicates("AccidentHistoryID")
    m = a.merge(r, on="AccidentHistoryID", how="left")
    m["words"] = (m.CF_Other.fillna("") + " " + m.OtherReleaseSource.fillna("")).str.contains(WORDS)
    g = m.planned_before > 0
    res = {"note": __doc__.split("Output:")[0].strip(), "accidents": len(m), "with_planned_before": int(g.sum()),
           "plants_with_planned_before": int(m.loc[g, "plant_id"].nunique()),
           "records_not_found": int(m.InitiatingEvent.isna().sum()), "factors": {}}
    rows = {c: (m[c] == "Yes") for c in CF} | {"initiating_human_error": m.InitiatingEvent.eq("b"),
                                                 "initiating_weather": m.InitiatingEvent.eq("c"),
                                                 "other_text_mentions_startup_shutdown_turnaround": m.words}
    for k, y in rows.items():
        t = [[int((y & g).sum()), int((~y & g).sum())], [int((y & ~g).sum()), int((~y & ~g).sum())]]
        res["factors"][k] = {"with_planned_before": t[0][0], "share_with_planned_before": round(t[0][0] / max(g.sum(), 1), 3),
                             "share_others": round(t[1][0] / max((~g).sum(), 1), 3),
                             "fisher_p": round(float(fisher_exact(t)[1]), 4)}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "note"}, indent=1))


if __name__ == "__main__":
    main()
