"""Phase 5 diagnostic (D9, exploratory, found after seeing the multiverse): planned work (TCEQ maintenance, startup
and shutdown reports) in the week before an accident. phase5_diag_lastweek.py found 1.65 per doubling for planned
reports starting in days -7 to -1, and about 1.0 for unplanned ones. Before saying anything, this checks:

  base         full links, window ending 2021 (the primary period) and 2023; planned and unplanned last-week counts
               each with their own statewide control
  by_type      maintenance, startup and shutdown as separate terms
  by_days      days -3 to -1 and days -7 to -4 as separate terms; gap 1 (days -8 to -2)
  notified     only planned reports whose initial notification came before the work started (filed in advance, so
               they cannot be a report about the accident); and the rest
  finished     planned work that ended before the day (start in days -7 to -1, end before day 0) against work still
               going on that day
  storms       the three storm rules of the robustness checks (R5 NOAA storm records, R22 FEMA declarations, R23
               hurricane tracks within 150 km), days dropped
  counts       accidents and plants with at least one planned report in the week before (plan D4 item 6: 5 or more)
  fake_dates   200 redraws of each accident to a random at-risk day of the same plant-year (no real accidents):
               the code and design should give about 1
  leave_one_out  the planned term with each plant left out in turn (smallest and largest)

Times come from the report's start, end and initial-notification fields; a report with an unreadable time is left out
of the parts that need it and counted. Output: data/manifests/phase5_diag_planned.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402
import phase5_robust as RB  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "phase5_diag_planned.json"
PLANNED = ("MAINTENANCE", "AIR STARTUP", "AIR SHUTDOWN")
UNPLANNED = ("EMISSIONS EVENT", "EXCESS OPACITY")
FMT = "%m/%d/%Y %I:%M %p"


def term(r, t):
    x = r["terms"][t]
    return {"rr": round(x["rr_doubling"], 3), "ci": [round(c, 3) for c in x["ci"]], "p": round(x["p"], 5)}


def planned_reports(ev):
    """Kept planned reports (same filters as the event counts) with start, end and initial-notification times."""
    excl = P.exclusion("primary")
    e = ev[ev.event_type.isin(PLANNED) & ev.date_source.ne("none") & ev.plant_id.notna() & ~ev.incident.isin(excl)
           & ~ev.is_duplicate].copy()
    d = pd.read_parquet(ROOT / "data/derived/details_table.parquet",
                        columns=["incident", "start_text", "end_text", "initial_notification"])
    d["incident"] = d.incident.astype(e.incident.dtype)
    e = e.merge(d.drop_duplicates("incident"), on="incident", how="left")
    for c in ("start_text", "end_text", "initial_notification"):
        e[c[:5]] = pd.to_datetime(e[c], format=FMT, errors="coerce")
    e["day"] = e.event_datetime.dt.normalize()
    return e


def counts(e, mask=None):
    e = e if mask is None else e[mask]
    return e.groupby(["plant_id", "day"]).size()


def finished_split(pan, e, window=7):
    """Per panel row: planned reports starting in days -window..-1 that ended before the day, and those not ended."""
    fin = np.zeros(len(pan))
    ong = np.zeros(len(pan))
    by_plant = {p: g for p, g in e.dropna(subset=["end_t"]).groupby("plant_id")}
    for p, idx in pan.groupby("plant_id").indices.items():
        g = by_plant.get(p)
        if g is None:
            continue
        t = pan.day.values[idx].astype("datetime64[D]").astype(np.int64)[:, None]
        s = g.day.values.astype("datetime64[D]").astype(np.int64)[None, :]
        en = g.end_t.dt.normalize().values.astype("datetime64[D]").astype(np.int64)[None, :]
        inwin = (s >= t - window) & (s <= t - 1)
        fin[idx] = (inwin & (en < t)).sum(axis=1)
        ong[idx] = (inwin & (en >= t)).sum(axis=1)
    return fin, ong


def main():
    res = {"note": __doc__.split("Times come")[0].strip()}
    plants, ev, *_ = P.tables("v2")
    e = planned_reports(ev)
    cu = P.event_counts(ev, UNPLANNED)
    res["planned_reports"] = {"kept": len(e), "start_unreadable": int(e.start.isna().sum()),
                              "end_unreadable": int(e.end_t.isna().sum()),
                              "notification_unreadable": int(e.initi.isna().sum()),
                              "notified_before_start": int((e.initi < e.start).sum())}
    cp = counts(e)
    lw = lambda c, w=7, g=0: (c, w, g)  # noqa: E731

    def two(end, **kw):
        return P.h1_run(end=end, exposures={"planned": lw(cp), "unplanned": lw(cu)}, statewide_each=True, **kw)

    for end in ("2021-12-31", "2023-12-31"):
        r = two(end, keep_panel=True)
        res[f"base_{end[:4]}"] = {t: term(r, t) for t in ("planned", "unplanned")} | {"n_accidents": r["n_accidents"]}
        if end == "2021-12-31":
            pan0 = r["panel"]
    # counts of accidents and plants with planned work in the week before (primary period)
    acc_rows = pan0[pan0.y > 0]
    hit = acc_rows[acc_rows.E_planned > 0]
    res["counts_2021"] = {"accident_days": int(len(acc_rows)), "accident_days_with_planned_last_week": int(len(hit)),
                          "plants_with_such_accidents": int(hit.plant_id.nunique()),
                          "share_of_all_days_with_planned_last_week": round(float((pan0.E_planned > 0).mean()), 4),
                          "share_of_accident_days_with_planned_last_week": round(float((acc_rows.E_planned > 0).mean()), 4)}
    print(res["counts_2021"], flush=True)
    # by type
    ex = {t.split()[-1].lower(): lw(counts(e, e.event_type.eq(t))) for t in PLANNED} | {"unplanned": lw(cu)}
    r = P.h1_run(end="2021-12-31", exposures=ex, statewide_each=True)
    res["by_type"] = {t: term(r, t) for t in ex}
    # by days
    r = P.h1_run(end="2021-12-31", exposures={"planned_days_1_3": (cp, 3, 0), "planned_days_4_7": (cp, 4, 3),
                                              "unplanned": lw(cu)}, statewide_each=True)
    res["by_days"] = {t: term(r, t) for t in ("planned_days_1_3", "planned_days_4_7", "unplanned")}
    r = P.h1_run(end="2021-12-31", exposures={"planned": (cp, 7, 1), "unplanned": (cu, 7, 1)}, statewide_each=True)
    res["gap_1"] = {t: term(r, t) for t in ("planned", "unplanned")}
    # notified in advance or not
    adv = e.initi < e.start
    r = P.h1_run(end="2021-12-31", exposures={"planned_notified_before": lw(counts(e, adv)),
                                              "planned_other": lw(counts(e, ~adv)), "unplanned": lw(cu)},
                 statewide_each=True)
    res["notified"] = {t: term(r, t) for t in ("planned_notified_before", "planned_other", "unplanned")}
    # finished before the day or still going on
    pan = pan0.copy()
    fin, ong = finished_split(pan, e)
    pan["planned_finished"], pan["planned_ongoing"] = np.log1p(fin), np.log1p(ong)
    terms = ["planned_finished", "planned_ongoing", "unplanned", "xs_planned", "xs_unplanned"]
    r = P.fit(pan, terms, "plant_year + moy", "poisson")
    res["finished"] = {t: term(r, t) for t in ("planned_finished", "planned_ongoing", "unplanned")} | {
        "accident_days_with_finished": int(((fin > 0) & (pan.y > 0)).sum()),
        "accident_days_with_ongoing": int(((ong > 0) & (pan.y > 0)).sum())}
    print("finished", res["finished"], flush=True)
    # storms
    m5, _ = RB.r5_mask_fn()
    m22, _ = RB.r22_mask_fn()
    m23, _ = RB.r23_mask_fn()
    for name, m in (("R5_noaa", m5), ("R22_fema", m22), ("R23_hurdat", m23)):
        r = two("2021-12-31", drop_days=m)
        res[f"storms_{name}"] = {t: term(r, t) for t in ("planned", "unplanned")} | {"n_accidents": r["n_accidents"]}
        print(name, res[f"storms_{name}"], flush=True)
    both = lambda pan: m5(pan) | m22(pan) | m23(pan)  # noqa: E731
    r = two("2021-12-31", drop_days=both)
    res["storms_all_three"] = {t: term(r, t) for t in ("planned", "unplanned")} | {"n_accidents": r["n_accidents"]}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    # fake dates within plant-year
    rng = np.random.default_rng(11)
    terms0 = ["planned", "unplanned", "xs_planned", "xs_unplanned"]
    k = pan0.groupby("plant_year").y.sum()
    idx = pan0.groupby("plant_year").indices
    fake = []
    for i in range(200):
        y = np.zeros(len(pan0), dtype=int)
        for py, rows in idx.items():
            np.add.at(y, rng.choice(rows, size=int(k[py]), replace=True), 1)
        rf = P.fit(pan0.assign(y=y), terms0, "plant_year + moy", "poisson")
        fake.append((rf["terms"]["planned"]["rr_doubling"], rf["terms"]["planned"]["p"]))
    f = np.array(fake)
    res["fake_dates"] = {"draws": len(f), "median_rr": round(float(np.median(f[:, 0])), 3),
                         "share_p_below_0.05": round(float((f[:, 1] < 0.05).mean()), 3),
                         "share_rr_at_least_real": round(float((f[:, 0] >= res["base_2021"]["planned"]["rr"]).mean()), 4)}
    print("fake", res["fake_dates"], flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    # leave one plant out
    loo = []
    for p in sorted(pan0.plant_id.unique()):
        sub = pan0[pan0.plant_id.ne(p)]
        rl = P.fit(sub, terms0, "plant_year + moy", "poisson")
        loo.append((p, rl["terms"]["planned"]["rr_doubling"], rl["terms"]["planned"]["p"]))
    lo = pd.DataFrame(loo, columns=["plant", "rr", "p"])
    res["leave_one_out"] = {"plants": len(lo), "min_rr": round(lo.rr.min(), 3), "max_rr": round(lo.rr.max(), 3),
                            "max_p": round(lo.p.max(), 5)}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "note"}, indent=1))



def chains():
    """Added check: an accident, then a restart (startup report), then a second accident would count as planned work
    before an accident. Drop accidents within 120 days after an earlier one at the plant (R15), or all days within
    120 days after an accident (R16)."""
    plants, ev, *_ = P.tables("v2")
    e = planned_reports(ev)
    ex = {"planned": (counts(e), 7, 0), "unplanned": (P.event_counts(ev, UNPLANNED), 7, 0)}
    res = json.loads(OUT.read_text())
    for name, kw in (("chains_R15_drop_120", dict(drop_chain_cases=120)), ("chains_R16_post_120", dict(post_excl=120))):
        r = P.h1_run(end="2021-12-31", exposures=ex, statewide_each=True, **kw)
        res[name] = {t: term(r, t) for t in ("planned", "unplanned")} | {"n_accidents": r["n_accidents"]}
        print(name, res[name], flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    chains() if "--chains" in sys.argv else main()
