"""Link Texas RMP facilities to TCEQ regulated entities (RNs) by the frozen rules in rules/linking_rules.json.

Uses only names, IDs, addresses and coordinates. Emission events are used for one thing only: knowing which RNs
report any events, because only those pairs are sent to hand review (plan D3). Accidents are never read.

Outputs (data/derived/):
  link_pairs.csv          every candidate pair with its evidence and the rule's decision
  link_review_queue.csv   pairs that need a person's decision (input to tools/link_review.html)
  plant_members_v2.csv    final plant groups (after review decisions, if any are present)
  plants_v2.csv           one row per plant, with member counts and how each link was made
  plant_chain_checks.csv  plants whose members lie more than 5 km apart or hold more than 10 RNs
Review decisions are read from data/manual/link_review_decisions.json if it exists.

Usage: python3 src/link_plants_v2.py
"""
import collections
import json
import math
import re
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SL = ROOT / "data" / "slices"
EXT = ROOT / "data" / "external"
OUT = ROOT / "data" / "derived"
MAN = ROOT / "data" / "manual"
RULES = json.loads((ROOT / "rules" / "linking_rules.json").read_text())
READ = dict(dtype=str, keep_default_na=False)
TX = (25.5, 36.6, -106.7, -93.4)
SUFFIX = r"\b(ROAD|RD|STREET|ST|AVENUE|AVE|AV|DRIVE|DR|HIGHWAY|HWY|BOULEVARD|BLVD|LANE|LN|PARKWAY|PKWY|FREEWAY|FWY|NORTH|SOUTH|EAST|WEST|N|S|E|W)\b"


# ------------------------------------------------------------------ normalizers (as written in the rules file)
def norm_id(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def title_v(s):
    m = re.fullmatch(r"[O0]?0*(\d{1,5})", norm_id(s))
    return m.group(1) if m else None


def addr_key(a, z):
    a = " ".join(re.sub(r"[^A-Z0-9 ]", " ", str(a).upper()).split())
    z = re.sub(r"\D", "", str(z))[:5]
    m = re.match(r"(\d+)\s+(.*)", a)
    if not m or len(z) != 5:
        return None
    rest = " ".join(re.sub(SUFFIX, "", m.group(2)).split())
    return (m.group(1), rest, z) if rest else None


def words(s):
    return {w for w in re.split(r"[^A-Z0-9]+", str(s).upper()) if len(w) >= 3 and not w.isdigit()}


def km(a, b, c, d):
    return math.hypot((a - c) * 111.0, (b - d) * 111.0 * math.cos(math.radians((a + c) / 2)))


def in_tx(la, lo):
    return TX[0] <= la <= TX[1] and TX[2] <= lo <= TX[3]


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


# ------------------------------------------------------------------ inputs
def load():
    z = zipfile.ZipFile(EXT / "epa_frs/state_combined_tx.zip")
    prog = pd.read_csv(z.open("TX_PROGRAM_FILE.CSV"), usecols=["REGISTRY_ID", "PGM_SYS_ACRNM", "PGM_SYS_ID"],
                       encoding="latin-1", **READ)
    frs_fac = pd.read_csv(z.open("TX_FACILITY_FILE.CSV"), usecols=["REGISTRY_ID", "LATITUDE83", "LONGITUDE83"],
                          encoding="latin-1", **READ)
    cr = pd.read_parquet(OUT / "central_registry.parquet",
                         columns=["rn", "re_name", "customer", "addr", "city", "county", "zip", "naics", "program", "ai"])
    rmp = pd.read_csv(SL / "rmp_raw/tblS1Facilities.csv.gz", **READ)
    fips = pd.read_csv(SL / "rmp_raw/tlkpCountyFIPSCodes.csv.gz", **READ)
    sub = pd.read_csv(SL / "rmp_submissions_tx.csv.gz", usecols=["EPAFacilityID", "NAICSCodes"], **READ)
    pts = pd.read_parquet(OUT / "tceq_rn_points_raw.parquet")
    ev_rns = set(pd.read_csv(ROOT / "data/master/incidents.csv.gz", usecols=["RN"], **READ)["RN"])
    return prog, frs_fac, cr, rmp, fips, sub, pts, ev_rns


def main():
    prog, frs_fac, cr, rmp, fips, sub, pts, ev_rns = load()
    prog["PGM_SYS_ID"] = prog.PGM_SYS_ID.str.strip()
    rmp_ids = sorted(set(rmp.EPAFacilityID))
    county_name = dict(zip(fips.StateCounty_Code, fips.County_Name.str.strip().str.upper()))

    # ---------------- RN side
    acr = prog[prog.PGM_SYS_ACRNM == "TX-TCEQ ACR"]
    rn_reg = acr.groupby("PGM_SYS_ID").REGISTRY_ID.apply(set).to_dict()
    reg_rns = acr.groupby("REGISTRY_ID").PGM_SYS_ID.apply(set).to_dict()
    frs_fac["lat"] = pd.to_numeric(frs_fac.LATITUDE83, errors="coerce")
    frs_fac["lon"] = pd.to_numeric(frs_fac.LONGITUDE83, errors="coerce")
    reg_pt = {r: (a, b) for r, a, b in zip(frs_fac.REGISTRY_ID, frs_fac.lat, frs_fac.lon)
              if a == a and b == b and in_tx(a, b)}
    rn_pts = collections.defaultdict(set)
    for rn, a, b in zip(pts.rn, pts.lat, pts.lon):
        if in_tx(a, b):
            rn_pts[rn].add((round(a, 5), round(b, 5)))
    for rn, regs in rn_reg.items():
        for r in regs:
            if r in reg_pt:
                rn_pts[rn].add((round(reg_pt[r][0], 5), round(reg_pt[r][1], 5)))
    crd = cr.drop_duplicates(["rn", "re_name", "customer", "addr", "zip", "county", "naics"])
    rn_county = crd.groupby("rn").county.apply(lambda s: {x.strip().upper() for x in s if x.strip()}).to_dict()
    rn_addr = collections.defaultdict(set)
    for rn, a, zp in zip(crd.rn, crd.addr, crd.zip):
        k = addr_key(a, zp)
        if k:
            rn_addr[rn].add(k)
    rn_namestr = crd.groupby("rn").apply(lambda g: " | ".join(sorted(set(g.re_name) | set(g.customer)))).to_dict()
    # word frequency is counted over the same name strings that are compared (site names and customer names)
    df = collections.Counter(w for n in rn_namestr.values() for w in words(n))
    n_names = len(rn_namestr)
    generic = {w for w, c in df.items() if c / n_names > 0.005}
    # place words are judged per record: a word from a record's own city or county name is not evidence for that pair
    rn_place = collections.defaultdict(set)
    for rn, c1, c2 in zip(crd.rn, crd.city, crd.county):
        rn_place[rn] |= words(c1) | words(c2)
    rn_words = {rn: words(s) - generic for rn, s in rn_namestr.items()}
    ai_index = collections.defaultdict(set)
    tv_index = collections.defaultdict(set)
    for rn, program, ai in zip(cr.rn, cr.program, cr.ai):
        k = norm_id(ai)
        if len(k) >= 6:
            ai_index[k].add(rn)
        if program == "AIROP":
            m = re.fullmatch(r"O?0*(\d{1,5})", norm_id(ai))
            if m:
                tv_index[m.group(1)].add(rn)
    frs_id_index = collections.defaultdict(set)   # any EPA program ID -> RNs in the same registry
    for reg, pid in zip(prog.REGISTRY_ID, prog.PGM_SYS_ID):
        k = norm_id(pid)
        if len(k) >= 6 and reg in reg_rns:
            frs_id_index[k] |= reg_rns[reg]

    # ---------------- RMP side
    rmp["county"] = rmp.FacilityCountyFIPS.map(county_name).fillna("")
    g = rmp.groupby("EPAFacilityID")
    r_county = g.county.apply(lambda s: {x for x in s if x}).to_dict()
    r_addr = collections.defaultdict(set)
    r_pts = collections.defaultdict(set)
    r_ids = collections.defaultdict(set)
    r_tv = collections.defaultdict(set)
    for r in rmp.itertuples():
        k = addr_key(r.FacilityStr1, r.FacilityZipCode)
        if k:
            r_addr[r.EPAFacilityID].add(k)
        for la, lo in ((r.FacilityLatDecDegs, r.FacilityLongDecDegs), (r.FRS_Lat, r.FRS_Long)):
            try:
                la, lo = float(la), float(lo)
            except ValueError:
                continue
            lo = -abs(lo)
            if in_tx(la, lo):
                r_pts[r.EPAFacilityID].add((round(la, 5), round(lo, 5)))
        for t in re.split(r"[;,/&]|\bAND\b", r.OtherEPAFacilityID.upper()):
            k = norm_id(t)
            if len(k) >= 6:
                r_ids[r.EPAFacilityID].add(k)
        t = title_v(r.ClearAirOpPermitID)
        if t:
            r_tv[r.EPAFacilityID].add(t)
    r_namestr = g.apply(lambda d: " | ".join(sorted((set(d.FacilityName) | set(d.ParentCompanyName) | set(d.Company2Name)
                                                    | set(d.OperatorName)) - {""}))).to_dict()
    r_words = {r: words(s) - generic for r, s in r_namestr.items()}
    r_place = collections.defaultdict(set)
    for r, c1, c2 in zip(rmp.EPAFacilityID, rmp.FacilityCity, rmp.county):
        r_place[r] |= words(c1) | words(c2)

    def shared_words(r, rn):
        return (r_words.get(r, set()) & rn_words.get(rn, set())) - r_place.get(r, set()) - rn_place.get(rn, set())

    def dist(r, rn):
        best = None
        for a, b in r_pts.get(r, ()):
            for c, d in rn_pts.get(rn, ()):
                x = km(a, b, c, d)
                best = x if best is None or x < best else best
        return best

    # ---------------- registry links (rule: registry)
    uf_reg = UnionFind()
    for reg, acr_, pid in zip(prog.REGISTRY_ID, prog.PGM_SYS_ACRNM, prog.PGM_SYS_ID):
        if acr_ == "RMP":
            uf_reg.union("RMP:" + pid, "REG:" + reg)
        elif acr_ == "TX-TCEQ ACR":
            uf_reg.union("RN:" + pid, "REG:" + reg)
    comp = collections.defaultdict(set)
    for node in list(uf_reg.parent):
        comp[uf_reg.find(node)].add(node)
    registry_pairs = set()
    for nodes in comp.values():
        rm = [n[4:] for n in nodes if n.startswith("RMP:")]
        rns = [n[3:] for n in nodes if n.startswith("RN:")]
        for a in rm:
            for b in rns:
                registry_pairs.add((a, b))

    # ---------------- candidate pairs from the other routes
    cands = collections.defaultdict(set)   # (rmp, rn) -> routes
    for r in rmp_ids:
        for k in r_ids.get(r, ()):
            for rn in ai_index.get(k, ()):
                cands[(r, rn)].add("own_id_tceq")
            for rn in frs_id_index.get(k, ()):
                cands[(r, rn)].add("own_id_epa")
        for t in r_tv.get(r, ()):
            for rn in tv_index.get(t, ()):
                cands[(r, rn)].add("own_title_v")
    addr_index = collections.defaultdict(set)
    for rn, ks in rn_addr.items():
        for k in ks:
            addr_index[k].add(rn)
    for r in rmp_ids:
        for k in r_addr.get(r, ()):
            for rn in addr_index.get(k, ()):
                cands[(r, rn)].add("address")
    grid = collections.defaultdict(set)
    for rn, ps in rn_pts.items():
        if rn in ev_rns:
            for a, b in ps:
                grid[(int(a * 20), int(b * 20))].add(rn)
    for r in rmp_ids:
        near = set()
        for a, b in r_pts.get(r, ()):
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    near |= grid.get((int(a * 20) + di, int(b * 20) + dj), set())
        for rn in near:
            d = dist(r, rn)
            if d is not None and (d <= 0.25 or (d <= 1.0 and shared_words(r, rn))):
                cands[(r, rn)].add("location_name")
    for p in registry_pairs:
        cands[p].add("registry")

    # ---------------- decisions
    rows = []
    for (r, rn), routes in cands.items():
        d = dist(r, rn)
        same_county = bool(r_county.get(r, set()) & rn_county.get(rn, set()))
        same_addr = bool(r_addr.get(r, set()) & rn_addr.get(rn, set()))
        shared = sorted(shared_words(r, rn))
        own = bool(routes & {"own_id_tceq", "own_id_epa", "own_title_v"})
        if "registry" in routes:
            dec, why = "accept", "registry"
        elif own and not same_county:
            dec, why = "reject", "county_differs"
        elif own and (same_addr or (d is not None and d <= 1.0)):
            dec, why = "accept", "own_id"
        elif rn not in ev_rns:
            dec, why = "not_reviewed", "rn_has_no_events"
        else:
            dec, why = "review", "own_id_unconfirmed" if own else ("address_only" if "address" in routes else "location_name")
        rows.append({"rmp": r, "rn": rn, "routes": "+".join(sorted(routes)), "decision": dec, "rule": why,
                     "same_county": same_county, "same_address": same_addr,
                     "distance_km": None if d is None else round(d, 3), "shared_words": " ".join(shared),
                     "rn_reports_events": rn in ev_rns})
    pairs = pd.DataFrame(rows).sort_values(["rmp", "rn"])
    OUT.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(OUT / "link_pairs.csv", index=False)

    # ---------------- review queue (records only; no events, no accidents)
    has_event_site = set(pairs[(pairs.decision == "accept") & pairs.rn_reports_events].rmp)
    later = (pairs.decision == "review") & pairs.rmp.isin(has_event_site)
    pairs.loc[later, "decision"] = "not_reviewed"
    pairs.loc[later, "rule"] = pairs.loc[later, "rule"] + ";facility_already_has_event_site"
    pairs.to_csv(OUT / "link_pairs.csv", index=False)
    q = pairs[pairs.decision == "review"].copy()
    rsub = sub.groupby("EPAFacilityID").NAICSCodes.apply(lambda s: " ".join(sorted(set(" ".join(s).split())))).to_dict()
    rn_naics = crd.groupby("rn").naics.apply(lambda s: " | ".join(sorted({x for x in s if x}))).to_dict()
    rn_progs = cr.groupby("rn").program.apply(lambda s: " ".join(sorted(set(s)))).to_dict()
    rn_addr_text = crd.groupby("rn").apply(lambda g: " | ".join(sorted({f"{a} {c} {z}".strip() for a, c, z in
                                                                        zip(g.addr, g.city, g.zip) if a.strip()}))).to_dict()
    rmp_addr_text = g.apply(lambda d: " | ".join(sorted({f"{a} {c} {z}".strip() for a, c, z in
                                                         zip(d.FacilityStr1, d.FacilityCity, d.FacilityZipCode)}))).to_dict()
    q["rmp_names"] = q.rmp.map(r_namestr)
    q["rmp_address"] = q.rmp.map(rmp_addr_text)
    q["rmp_county"] = q.rmp.map(lambda r: " ".join(sorted(r_county.get(r, set()))))
    q["rmp_naics"] = q.rmp.map(rsub).fillna("")
    q["rmp_other_ids"] = q.rmp.map(lambda r: " ".join(sorted(r_ids.get(r, set()) | {"TitleV:" + t for t in r_tv.get(r, set())})))
    q["rn_names"] = q.rn.map(rn_namestr).fillna("")
    q["rn_address"] = q.rn.map(rn_addr_text).fillna("")
    q["rn_county"] = q.rn.map(lambda x: " ".join(sorted(rn_county.get(x, set()))))
    q["rn_naics"] = q.rn.map(rn_naics).fillna("")
    q["rn_programs"] = q.rn.map(rn_progs).fillna("")
    q.to_csv(OUT / "link_review_queue.csv", index=False)
    # records for the review page: identifying details only (no event counts, no accidents)
    def rmp_rec(r):
        return {"names": r_namestr.get(r, ""), "address": rmp_addr_text.get(r, ""), "county": " ".join(sorted(r_county.get(r, set()))),
                "naics": rsub.get(r, ""), "ids": " ".join(sorted(r_ids.get(r, set()) | {"TitleV:" + t for t in r_tv.get(r, set())})),
                "points": sorted(r_pts.get(r, set()))[:3]}

    def rn_rec(x):
        return {"names": rn_namestr.get(x, ""), "address": rn_addr_text.get(x, ""), "county": " ".join(sorted(rn_county.get(x, set()))),
                "naics": rn_naics.get(x, ""), "programs": rn_progs.get(x, ""), "points": sorted(rn_pts.get(x, set()))[:3]}
    records_needed = (set(q.rmp), set(q.rn))

    # ---------------- final groups
    decisions = {}
    dfile = MAN / "link_review_decisions.json"
    if dfile.exists():
        decisions = json.loads(dfile.read_text()).get("decisions", {})
    accepted = pairs[pairs.decision == "accept"][["rmp", "rn", "rule"]].values.tolist()
    removed = {tuple(k.split("|")) for k, ans in decisions.items() if ans == "different"}
    accepted = [a for a in accepted if (a[0], a[1]) not in removed]
    in_queue = set(zip(pairs[pairs.decision == "review"].rmp, pairs[pairs.decision == "review"].rn))
    for key, ans in decisions.items():
        r, rn = key.split("|")
        # a "same" answer adds a link only for a pair the current rules send to review
        if ans == "same" and (r, rn) in in_queue and not any(a[0] == r and a[1] == rn for a in accepted):
            accepted.append([r, rn, "hand_review"])
    uf = UnionFind()
    link_rule = collections.defaultdict(set)
    for r, rn, why in accepted:
        uf.union("RMP:" + r, "RN:" + rn)
        link_rule["RMP:" + r].add(why)
        link_rule["RN:" + rn].add(why)
    for r in rmp_ids:
        uf.find("RMP:" + r)
    for rn in ev_rns:
        uf.find("RN:" + rn)
    groups = collections.defaultdict(set)
    for node in list(uf.parent):
        groups[uf.find(node)].add(node)
    rmp_tx = set(rmp_ids)
    keep = [m for m in groups.values() if any(n[4:] in rmp_tx for n in m if n.startswith("RMP:"))
            or any(n[3:] in ev_rns for n in m if n.startswith("RN:"))]
    members, plants, checks = [], [], []
    for i, m in enumerate(sorted(keep, key=lambda m: min(m)), start=1):
        pid = f"Q{i:05d}"
        rms = sorted(n[4:] for n in m if n.startswith("RMP:"))
        rns = sorted(n[3:] for n in m if n.startswith("RN:"))
        for x in rms:
            members.append((pid, "RMP", x, "+".join(sorted(link_rule.get("RMP:" + x, set())))))
        for x in rns:
            members.append((pid, "RN", x, "+".join(sorted(link_rule.get("RN:" + x, set())))))
        rules_used = sorted({w for n in m for w in link_rule.get(n, set())})
        plants.append({"plant_id": pid, "n_rmp": len(rms), "n_rn": len(rns), "n_rn_with_events": sum(x in ev_rns for x in rns),
                       "linked": bool(rms) and bool(rns), "one_to_one": len(rms) == 1 and len(rns) == 1,
                       "registry_only": rules_used == ["registry"], "link_rules": "+".join(rules_used)})
        # chain check: the closest distance between each pair of members (any of their points), and counties
        mem = [("RMP", x) for x in rms] + [("RN", x) for x in rns]
        mpts = {mm: (r_pts.get(mm[1], set()) if mm[0] == "RMP" else rn_pts.get(mm[1], set())) for mm in mem}
        mcty = {mm: (r_county.get(mm[1], set()) if mm[0] == "RMP" else rn_county.get(mm[1], set())) for mm in mem}
        far = 0.0
        for i1 in range(len(mem)):
            for i2 in range(i1 + 1, len(mem)):
                a_, b_ = mpts[mem[i1]], mpts[mem[i2]]
                if a_ and b_:
                    dmin = min(km(x1, y1, x2, y2) for x1, y1 in a_ for x2, y2 in b_)
                    far = max(far, dmin)
        counties = set().union(*[c_ for c_ in mcty.values() if c_]) if any(mcty.values()) else set()
        if far > 5 or len(counties) > 1 or len(rns) > 10:
            checks.append({"plant_id": pid, "n_rmp": len(rms), "n_rn": len(rns), "members_apart_km": round(far, 1),
                           "counties": " | ".join(sorted(counties)), "link_rules": "+".join(rules_used)})
    pd.DataFrame(members, columns=["plant_id", "id_type", "id", "link_rules"]).to_csv(OUT / "plant_members_v2.csv", index=False)
    pl = pd.DataFrame(plants)
    pl.to_csv(OUT / "plants_v2.csv", index=False)
    pd.DataFrame(checks).to_csv(OUT / "plant_chain_checks.csv", index=False)
    flagged = {c["plant_id"] for c in checks}
    mem_by_plant = collections.defaultdict(list)
    for pid, t, x, lr in members:
        mem_by_plant[pid].append((t, x))
    chain_links = []
    accepted_set = {(a[0], a[1]): a[2] for a in accepted}
    for pid in sorted(flagged):
        rms_ = [x for t, x in mem_by_plant[pid] if t == "RMP"]
        rns_ = [x for t, x in mem_by_plant[pid] if t == "RN"]
        for r in rms_:
            for rn in rns_:
                if (r, rn) in accepted_set:
                    chain_links.append({"plant": pid, "rmp": r, "rn": rn, "rule": accepted_set[(r, rn)]})
    rm_need = set(records_needed[0]) | {c["rmp"] for c in chain_links}
    rn_need = set(records_needed[1]) | {c["rn"] for c in chain_links}
    dist_of = {(a, b): d for a, b, d in zip(pairs.rmp, pairs.rn, pairs.distance_km)}
    review = {"made": pd.Timestamp.now("UTC").isoformat(timespec="seconds"),
              "match_items": [{"rmp": r, "candidates": [{"rn": rn, "rule": rule, "distance_km": dk, "shared_words": sw,
                                                          "same_county": bool(sc), "same_address": bool(sa)}
                                                         for rn, rule, dk, sw, sc, sa in g_[["rn", "rule", "distance_km", "shared_words", "same_county", "same_address"]].values]}
                              for r, g_ in q.groupby("rmp")],
              "chain_items": [{"plant": pid, "links": [dict(c, distance_km=dist_of.get((c["rmp"], c["rn"]))) for c in chain_links if c["plant"] == pid]}
                              for pid in sorted(flagged)],
              "rmp_records": {r: rmp_rec(r) for r in sorted(rm_need)},
              "rn_records": {x: rn_rec(x) for x in sorted(rn_need)}}
    (OUT / "link_review_items.json").write_text(json.dumps(review, default=lambda o: None if o != o else o))

    # ---------------- summary
    print("generic words ignored as evidence:", len(generic), "(plus each record's own city and county words)")
    print("candidate pairs by decision:", pairs.decision.value_counts().to_dict())
    print("accepted by rule:", pairs[pairs.decision == "accept"].rule.value_counts().to_dict())
    print("review queue by rule:", q.rule.value_counts().to_dict(), "| RMP facilities in queue:", q.rmp.nunique())
    print("rejected:", int((pairs.decision == "reject").sum()), "| not reviewed (RN has no events):",
          int((pairs.decision == "not_reviewed").sum()))
    print(f"hand-review decisions applied: {len(decisions)}")
    lk = pl[pl.linked]
    print(f"plants: {len(pl)} | linked: {len(lk)} | linked with event RNs: {int((lk.n_rn_with_events > 0).sum())} | "
          f"one-to-one: {int(lk.one_to_one.sum())} | registry-only: {int(lk.registry_only.sum())}")
    in_linked = {x for pid, t, x, _ in members if t == "RMP" and pid in set(lk.plant_id)}
    in_ev = {x for pid, t, x, _ in members if t == "RMP" and pid in set(lk[lk.n_rn_with_events > 0].plant_id)}
    print(f"Texas RMP facilities in linked plants: {len(in_linked)} of {len(rmp_tx)}; in plants with event RNs: {len(in_ev)}")
    print(f"plants flagged for chain check: {len(checks)}")


if __name__ == "__main__":
    main()
