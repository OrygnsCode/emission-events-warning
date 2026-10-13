"""Completeness and dating check (plan D2 item 7, descriptive): serious events found in the National Response Center
(linked by the author's review) and OSHA (fatality or catastrophe investigations, severe injury reports) at RMP-linked
plants, compared with the RMP accident table: the share with an RMP accident at the same plant within 3 days (and
within 30 days), by source. Not every such event had to be reported to RMP (RMP covers releases of listed chemicals
from covered processes), so the share without an RMP record is an upper bound on what RMP misses.
CSB: the review of Chemical Safety Board investigations is summarized in docs/phase5_results.md, section 10. Output: data/manifests/completeness_check.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402
import phase5_h4_o6 as H  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "completeness_check.json"


def main():
    plants, ev, acc, *_ = P.tables("v2")
    acc_days = acc.groupby("plant_id").date.apply(lambda s: s.dt.normalize().values)
    rn_plant = ev.dropna(subset=["plant_id"]).drop_duplicates("rn").set_index("rn").plant_id
    linked_plants = set(plants.loc[plants.linked, "plant_id"])

    def gaps(plant_ids, days):
        out = []
        for p, d in zip(plant_ids, days):
            a = acc_days.get(p)
            out.append(np.nan if a is None else float(np.min(np.abs((a - np.datetime64(d)) / np.timedelta64(1, "D")))))
        return np.array(out)

    res = {"note": __doc__.split("Output:")[0].strip()}
    nrc = H.linked("nrc")
    nrc["plant_id"] = nrc.unit.map(rn_plant)
    for name, d in (("nrc_serious", nrc), ("osha_fatality_catastrophe", H.linked("osha").query("key.str.contains('-ACC-')", engine="python").rename(columns={"unit": "plant_id"})),
                    ("osha_severe_injury", H.linked("osha").query("key.str.contains('-SIR-')", engine="python").rename(columns={"unit": "plant_id"}))):
        d = d[d.plant_id.isin(linked_plants) & d.day.between(P.h1.STUDY_START, "2023-12-31")]
        d = d.drop_duplicates(["plant_id", "day"])
        g = gaps(d.plant_id, d.day)
        res[name] = {"plant_days": len(d), "plants": int(d.plant_id.nunique()),
                     "with_rmp_accident_within_3_days": int((g <= 3).sum()),
                     "with_rmp_accident_within_30_days": int((g <= 30).sum()),
                     "share_within_3_days": round(float((g <= 3).mean()), 3) if len(d) else None}
        if name == "nrc_serious":
            # material named in the NRC report: on the RMP regulated-substance list (by CAS number) or not
            # (CAS digits without leading zeros, or the material name equal to an RMP name before its bracket)
            mat = pd.read_csv(P.h1.ROOT / "data/slices/nrc_material_involved_tx.csv.gz", dtype=str, keep_default_na=False,
                              usecols=["SEQNOS", "CAS_NUMBER", "NAME_OF_MATERIAL"])
            ch = pd.read_csv(P.h1.ROOT / "data/slices/rmp_raw/tlkpChemicals.csv.gz", dtype=str, keep_default_na=False)
            digits = lambda x: x.str.replace(r"[^0-9]", "", regex=True).str.lstrip("0")  # noqa: E731
            cas = set(digits(ch.CASNumber)) - {""}
            names = set(ch.ChemicalName.str.split("[").str[0].str.strip().str.upper()) - {""}
            mat["listed"] = digits(mat.CAS_NUMBER).isin(cas) | mat.NAME_OF_MATERIAL.str.strip().str.upper().isin(names)
            listed = set(mat.loc[mat.listed, "SEQNOS"])
            seq = d.key.str.replace("NRC-", "", regex=False)
            m = seq.isin(listed).values
            res[name]["material_on_rmp_list"] = {"plant_days": int(m.sum()), "with_rmp_accident_within_3_days":
                                                 int((g[m] <= 3).sum())}
        print(name, res[name], flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
