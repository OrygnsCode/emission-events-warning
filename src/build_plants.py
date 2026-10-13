"""Link TCEQ RNs and RMP facility IDs into plants (analysis plan section 3.1).

A plant is a connected group of TCEQ RNs (FRS program TX-TCEQ ACR) and RMP
facility IDs (FRS program RMP) that share an FRS REGISTRY_ID, directly or
through a chain. RNs with emission events that FRS does not know, and Texas RMP
facilities with no TCEQ RN in FRS, become one-member plants so nothing is lost.

Outputs (data/derived/):
  plant_members.csv   one row per (plant_id, id_type, id)
  plants.csv          one row per plant with member counts and flags
Uses no accident information.
"""
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SL = ROOT / "data" / "slices"
OUT = ROOT / "data" / "derived"
READ = dict(dtype=str, keep_default_na=False)


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def main():
    prog = pd.read_csv(SL / "frs_program_tx_relevant.csv.gz", usecols=["PGM_SYS_ACRNM", "PGM_SYS_ID", "REGISTRY_ID"],
                       encoding="latin-1", **READ)
    links = prog[prog["PGM_SYS_ACRNM"].isin(["TX-TCEQ ACR", "RMP"])].copy()
    links["node"] = links["PGM_SYS_ACRNM"].map({"TX-TCEQ ACR": "RN", "RMP": "RMP"}) + ":" + links["PGM_SYS_ID"].str.strip()
    event_rns = set(pd.read_csv(ROOT / "data/master/incidents.csv.gz", usecols=["RN"], **READ)["RN"])
    rmp_tx = set(pd.read_csv(SL / "rmp_facilities_tx.csv.gz", usecols=["EPAFacilityID"], **READ)["EPAFacilityID"])

    uf = UnionFind()
    reg_of = defaultdict(set)
    for node, reg in zip(links["node"], links["REGISTRY_ID"]):
        uf.union(node, "REG:" + reg)
        reg_of[node].add(reg)
    for rn in event_rns:
        uf.find("RN:" + rn)
    for rid in rmp_tx:
        uf.find("RMP:" + rid)

    # keep only components that contain an RN with events or a Texas RMP facility
    members = defaultdict(set)
    for node in list(uf.parent):
        if node.startswith(("RN:", "RMP:")):
            members[uf.find(node)].add(node)
    keep = {root: m for root, m in members.items()
            if any(n[3:] in event_rns for n in m if n.startswith("RN:"))
            or any(n[4:] in rmp_tx for n in m if n.startswith("RMP:"))}

    rows, plants = [], []
    for i, (root, m) in enumerate(sorted(keep.items(), key=lambda kv: min(kv[1])), start=1):
        pid = f"P{i:05d}"
        rns = sorted(n[3:] for n in m if n.startswith("RN:"))
        rmps = sorted(n[4:] for n in m if n.startswith("RMP:"))
        regs = sorted({r for n in m for r in reg_of.get(n, ())})
        rows += [(pid, "RN", x) for x in rns] + [(pid, "RMP", x) for x in rmps] + [(pid, "REGISTRY_ID", x) for x in regs]
        plants.append({
            "plant_id": pid, "n_rn": len(rns), "n_rn_with_events": sum(r in event_rns for r in rns),
            "n_rmp": len(rmps), "n_rmp_tx": sum(r in rmp_tx for r in rmps), "n_registry_ids": len(regs),
            "linked": bool(rns) and bool(rmps),
            "one_to_one": len(rns) == 1 and len(rmps) == 1,
        })
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["plant_id", "id_type", "id"]).to_csv(OUT / "plant_members.csv", index=False)
    p = pd.DataFrame(plants)
    p.to_csv(OUT / "plants.csv", index=False)

    linked = p[p.linked]
    print(f"plants: {len(p)} | linked RN+RMP: {len(linked)} | one-to-one: {int(linked.one_to_one.sum())}")
    print(f"linked plants with at least one RN that has events: {int((linked.n_rn_with_events > 0).sum())}")
    print(f"RN-only plants with events: {int(((p.n_rmp == 0) & (p.n_rn_with_events > 0)).sum())}")
    print(f"RMP-only Texas plants (no TCEQ RN in FRS): {int(((p.n_rn == 0) & (p.n_rmp_tx > 0)).sum())}")
    print("linked plants by number of RNs:", linked.n_rn.clip(upper=5).value_counts().sort_index().to_dict(),
          "| by number of RMP IDs:", linked.n_rmp.clip(upper=5).value_counts().sort_index().to_dict())
    covered_rmp = set(x for pid, t, x in rows if t == "RMP" and pid in set(linked.plant_id))
    print(f"Texas RMP facilities inside linked plants: {len(covered_rmp & rmp_tx)} of {len(rmp_tx)}")


if __name__ == "__main__":
    main()
