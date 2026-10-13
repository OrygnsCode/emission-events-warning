"""Exploratory test B (plan D14 item 4): satellite heat near a plant before its accidents. Unlike emission events,
this exposure is not reported by the company.

Exposure: for each plant and local calendar day (America/Chicago; America/Denver for El Paso and Hudspeth
counties is not needed here because the count is daily), whether NASA FIRMS VIIRS (Suomi NPP) recorded at least one
night detection within 1 km of any of the plant's event-reporting RNs (TCEQ coordinates, as in V2). x = log(1 +
number of such nights in days -97 to -8). Statewide count: the same at all other plants. Accidents from 2012-04-08
(first day with a full window) to 2021-12-31; days before 2012-04-08 are dropped. Model as H1. Shown as registered
and with detections on accident days and the 2 days after removed.
Output: data/manifests/phase5_satellite_heat.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_diag_own_reports as OR  # noqa: E402
import phase5_h1 as P  # noqa: E402
import vchecks_common as vc  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "phase5_satellite_heat.json"
FIRST = pd.Timestamp("2012-04-08")


def detections():
    det = []
    for f in sorted((ROOT / "data/slices/nasa_firms").glob("viirs-snpp_*_tx.csv.gz")):
        d = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time", "daynight"], dtype={"acq_time": str})
        d = d[d.daynight.eq("N")]
        utc = pd.to_datetime(d.acq_date + " " + d.acq_time.str.zfill(4), format="%Y-%m-%d %H%M")
        d["day"] = utc.dt.tz_localize("UTC").dt.tz_convert("America/Chicago").dt.tz_localize(None).dt.normalize()
        det.append(d[d.day.between("2012-01-01", "2021-12-31")])
    return pd.concat(det)


def main():
    plants, ev, acc, *_ = P.tables("v2")
    linked = set(plants.loc[plants.linked, "plant_id"])
    pts = vc.rn_points()
    rp = ev.dropna(subset=["plant_id"])[["rn", "plant_id"]].drop_duplicates()
    rp = rp[rp.plant_id.isin(linked) & rp.rn.isin(pts.index)]
    det = detections()
    lat, lon = det.latitude.values, det.longitude.values
    rows = []
    for p, g in rp.groupby("plant_id"):
        days = set()
        for rn in g.rn:
            la, lo = pts.at[rn, "lat"], pts.at[rn, "lon"]
            m = (np.abs(lat - la) < 0.012) & (np.abs(lon - lo) < 0.014)
            sub = det[m]
            sub = sub[vc.km(la, lo, sub.latitude.values, sub.longitude.values) <= 1.0]
            days |= set(sub.day)
        rows += [(p, d) for d in days]
    cnt = pd.DataFrame(rows, columns=["plant_id", "day"]).groupby(["plant_id", "day"]).size().clip(upper=1)
    cnt.index = cnt.index.set_names(["plant_id", "day"])
    res = {"note": __doc__.split("Output:")[0].strip(), "plants_with_located_rns": int(rp.plant_id.nunique()),
           "plants_with_any_detection_night": int(cnt.index.get_level_values(0).nunique()),
           "plant_nights_with_detection": int(cnt.sum()), "night_detections_used": len(det)}
    print({k: v for k, v in res.items() if k != "note"}, flush=True)
    a = acc[acc.plant_id.isin(linked) & acc.date.between(FIRST, "2021-12-31")]
    drop = lambda pan: (pan.day < FIRST).values  # noqa: E731
    for name, c in (("registered_design", cnt), ("own_detections_removed", None)):
        if c is None:
            c, removed = OR.remove_after(cnt, pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values}), 2)
            res["detection_nights_removed"] = removed
        r = P.h1_run(accidents=a, exposures={"x": c}, statewide_counts=cnt, drop_days=drop)
        t = r["terms"]["x"]
        res[name] = {"rr": round(t["rr_doubling"], 3), "ci": [round(v, 3) for v in t["ci"]], "p": round(t["p"], 4),
                     "n_accidents": r["n_accidents"], "n_plants": r["n_plants"]}
        print(name, res[name], flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
