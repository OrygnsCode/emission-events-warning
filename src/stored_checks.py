"""Stored versions of checks whose numbers were first reported from console output (found by the report audit,
2026-10-06). Each part recomputes and saves its numbers:
  planned_reports_by_year  planned-work reports per year at linked plants (filters as phase5_diag_planned)
  accident_day_reports     unplanned events on accident days and the 2 days after, against the number expected from
                           each plant's long-run daily average (primary accidents, June 2003 to 2021)
  exposure_recount         1,400 random plant-days of the primary panel: the 90-day event count recomputed directly
                           from the event table, compared with the panel value
  fake_dates_long_windows  accidents redrawn to random at-risk days of the same plant-year (no reports follow them);
                           90, 180 and 365-day windows; 30 draws each; median rate ratio
Output: data/manifests/stored_checks.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_planned as D  # noqa: E402
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "stored_checks.json"


def main():
    plants, ev, acc, *_ = P.tables("v2")
    linked = set(plants.loc[plants.linked, "plant_id"])
    res = {"note": __doc__.split("Output:")[0].strip()}
    e = D.planned_reports(ev)
    res["planned_reports_by_year_linked_plants"] = {int(k): int(v) for k, v in
                                                    e[e.plant_id.isin(linked)].groupby(e.day.dt.year).size().items() if k < 3000}
    # accident-day reports
    cnt = P.event_counts(ev)
    a = acc[acc.plant_id.isin(linked) & acc.date.between(P.h1.STUDY_START, "2021-12-31")]
    ad = a.assign(day=a.date.dt.normalize()).drop_duplicates(["plant_id", "day"])
    span_days = (pd.Timestamp("2021-12-31") - P.h1.STUDY_START).days + 1
    obs = {0: 0, 1: 0, 2: 0}
    exp = 0.0
    for p, g in ad.groupby("plant_id"):
        c = cnt[p] if p in cnt.index.get_level_values(0) else pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        c.index = pd.DatetimeIndex(c.index)
        rate = c[(c.index >= P.h1.STUDY_START) & (c.index <= pd.Timestamp("2021-12-31"))].sum() / span_days
        for d in g.day:
            for k in obs:
                obs[k] += int(c.get(d + pd.Timedelta(days=k), 0))
            exp += rate
    res["accident_day_reports"] = {"accident_days": len(ad), "events_on_day_0": obs[0], "events_days_0_to_2": sum(obs.values()),
                                   "expected_per_day_from_plant_average": round(exp, 1),
                                   "ratio_day_0": round(obs[0] / exp, 1), "ratio_days_0_to_2": round(sum(obs.values()) / (3 * exp), 1)}
    print(res["accident_day_reports"], flush=True)
    # exposure recount
    pan = P.h1_run(keep_panel=True)["panel"]
    rng = np.random.default_rng(1400)
    s = pan.iloc[rng.choice(len(pan), 1400, replace=False)]
    excl = P.exclusion("primary")
    raw = pd.read_csv(P.h1.DER / "events_v2.csv.gz")
    raw["event_datetime"] = pd.to_datetime(raw.event_datetime, errors="coerce")
    raw = raw[raw.event_type.eq("EMISSIONS EVENT") & raw.date_source.ne("none") & raw.plant_id.notna()
              & ~raw.incident.isin(excl) & ~raw.is_duplicate.astype(str).str.lower().eq("true")]
    raw["day"] = raw.event_datetime.dt.normalize()
    by = raw.groupby("plant_id").day.apply(lambda x: x.values)
    rec = []
    for p, d in zip(s.plant_id, s.day):
        v = by.get(p, np.array([], dtype="datetime64[ns]"))
        lo, hi = np.datetime64(d - pd.Timedelta(days=97)), np.datetime64(d - pd.Timedelta(days=8))
        rec.append(int(((v >= lo) & (v <= hi)).sum()))
    res["exposure_recount"] = {"plant_days": 1400, "differences": int((np.array(rec) != s.E_x.values).sum())}
    print(res["exposure_recount"], flush=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    # fake dates, long windows
    days_by_py = pan.groupby("plant_year").day.apply(lambda x: x.values)
    ap = a.assign(day=a.date.dt.normalize())
    ap = ap.assign(plant_year=ap.plant_id + "_" + ap.day.dt.year.astype(str))
    ap = ap[ap.plant_year.isin(days_by_py.index)]
    rng = np.random.default_rng(97)
    fake = {90: [], 180: [], 365: []}
    for i in range(30):
        fd = pd.to_datetime([days_by_py[py][rng.integers(len(days_by_py[py]))] for py in ap.plant_year])
        fa = ap.assign(date=fd)
        for w in fake:
            fake[w].append(P.h1_run(window=w, accidents=fa)["terms"]["x"]["rr_doubling"])
    res["fake_dates_long_windows"] = {f"window_{w}": {"draws": len(v), "median_rr": round(float(np.median(v)), 3)}
                                      for w, v in fake.items()}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(res["fake_dates_long_windows"], flush=True)


if __name__ == "__main__":
    main()
