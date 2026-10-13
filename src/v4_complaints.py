"""Check V4 (plan D6 item 10): complaints after reported events.

(a) TCEQ air complaints (open data), received date and county, June 2003 to 2021. Unit: county-day over every county
    that has at least one air complaint or one D6 episode in the period. Exposure: a D6 episode started (local date) in
    the county on that day or the 2 days before. Poisson with county-by-year-by-month and day-of-week effects,
    county-clustered errors. The complaint's RN field is not used.
(b) Houston 311 "Air Pollution" cases, 2011 to 2021, within 5 km of an event RN (coordinates of 0 dropped). Unit:
    RN-day for RNs with at least one case within 5 km over the period. Exposure: a D6 episode started at the RN on
    that day or the 2 days before. Poisson with RN-by-year-by-month and day-of-week effects, plant-clustered errors.

Output: data/derived/vchecks/v4_result.json
"""
import csv
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vchecks_common as vc  # noqa: E402

D0, D1 = pd.Timestamp("2003-06-01"), pd.Timestamp("2021-12-31")
# RUNNING: days on which an episode that started more than 2 days earlier is still running. "start" (primary, the D6
# rule) leaves them as unexposed; "drop" removes them; "exposed" counts them as exposed (sensitivity checks, plan D7
# addendum)
RUNNING = "start"


def running_days(ep_k, days_index):
    """1 on each local day from an episode's start date to its end date (valid ends only)."""
    s = pd.Series(0, index=days_index)
    for a, b in zip(ep_k.start_local.dt.normalize(), (ep_k.start_local + (ep_k.end_utc - ep_k.start_utc)).dt.normalize()):
        if b > a:
            s.loc[a:b] = 1
    return s


def apply_running(df, run):
    """Apply the RUNNING rule to a frame with columns x (exposure) given the running-day indicator."""
    only = (run == 1) & (df.x == 0)
    if RUNNING == "drop":
        return df[~only.values]
    if RUNNING == "exposed":
        df = df.copy()
        df.loc[only.values, "x"] = 1
    return df


def exposure(days_index, starts):
    """1 if any start on the day or the 2 days before."""
    s = pd.Series(0, index=days_index)
    for k in range(3):
        s = s | starts.reindex(days_index - pd.Timedelta(days=k), fill_value=0).values
    return s.astype(int)


def fit(df, fe, cluster):
    m = pf.fepois(f"y ~ x | {fe}", data=df, vcov={"CRV1": cluster})
    b, se = float(m.coef()["x"]), float(m.se()["x"])
    return {"rate_ratio": round(np.exp(b), 3), "ci95": [round(np.exp(b - 1.96 * se), 3), round(np.exp(b + 1.96 * se), 3)],
            "p": round(float(m.pvalue()["x"]), 4), "obs_used": int(m._N)}


def part_a(ep):
    c = pd.read_csv(vc.ROOT / "data/external/tceq_open_data/complaints_tdzs-qqjn.csv",
                    usecols=["Complaint Tracking Number", "Media", "County", "Complaint Received Date"], low_memory=False)
    c = c[c.Media.eq("AIR")].copy()
    # the file has one row per complaint and NAICS code; date and county never differ within a complaint (plan D7)
    n_rows = len(c)
    c = c.drop_duplicates("Complaint Tracking Number")
    c["day"] = pd.to_datetime(c["Complaint Received Date"], format="%b %d, %Y", errors="coerce")
    c["county"] = c.County.str.upper().str.strip()
    log = {"air_complaint_rows": n_rows, "air_complaints": len(c), "no_county": int(c.county.isna().sum())}
    c = c.dropna(subset=["county", "day"])
    c = c[c.day.between(D0, D1)]
    log["air_complaints_in_window_with_county"] = len(c)
    ep = ep[ep.start_local.between(D0, D1 + pd.Timedelta(days=1))]
    counties = sorted(set(c.county) | set(ep.county[ep.county != ""]))
    days = pd.date_range(D0, D1, freq="D")
    y = c.groupby(["county", "day"]).size()
    st = ep.assign(day=ep.start_local.dt.normalize()).groupby(["county", "day"]).size().clip(upper=1)
    frames = []
    for k in counties:
        yk = y.get(k, pd.Series(dtype=int)).reindex(days, fill_value=0)
        sk = st.get(k, pd.Series(dtype=int))
        fk = pd.DataFrame({"county": k, "day": days, "y": yk.values, "x": exposure(days, sk).values})
        if RUNNING != "start":
            fk = apply_running(fk, running_days(ep[ep.county == k], days).values)
        frames.append(fk)
    d = pd.concat(frames)
    d["cym"] = d.county + "_" + d.day.dt.strftime("%Y-%m")
    d["dow"] = d.day.dt.dayofweek
    log.update({"counties": len(counties), "county_days": len(d), "exposed_county_days": int(d.x.sum())})
    res = fit(d, "cym + dow", "county")
    res["complaints_per_exposed_day"] = round(float(d[d.x == 1].y.mean()), 4)
    res["complaints_per_unexposed_day_same_counties"] = round(float(
        d[(d.x == 0) & d.county.isin(set(d[d.x == 1].county))].y.mean()), 4)
    return {"log": log, "result": res}


def read_311():
    rows = []
    for f in sorted((vc.ROOT / "data/external/houston_311").glob("311-CRIS-*YTD*.txt.gz")):
        with gzip.open(f, "rt", errors="replace") as fh:
            for i, line in enumerate(fh):
                if "Case Number" in line:
                    hdr = i
                    break
        d = pd.read_csv(f, sep="|", skiprows=hdr, dtype=str, quoting=csv.QUOTE_NONE, on_bad_lines="skip",
                        encoding_errors="replace", index_col=False)
        d.columns = [x.strip() for x in d.columns]
        d = d[d["Incident Case Type"].eq("Air Pollution")][["Case Number", "Latitude", "Longitude", "Created Date Local"]]
        rows.append(d)
    d = pd.concat(rows).drop_duplicates("Case Number")
    d["lat"] = pd.to_numeric(d.Latitude, errors="coerce")
    d["lon"] = pd.to_numeric(d.Longitude, errors="coerce")
    d["day"] = pd.to_datetime(d["Created Date Local"].str[:10], errors="coerce")
    return d


def part_b(ep):
    d = read_311()
    log = {"air_cases_2011_2026": len(d), "zero_or_missing_coordinates": int((~(d.lat.abs() > 1)).sum())}
    d = d[(d.lat.abs() > 1) & d.day.between("2011-01-01", D1)]
    log["air_cases_2011_2021_valid"] = len(d)
    pts = vc.rn_points()
    ev_rns = set(ep.rn)
    P = pts.loc[pts.index.intersection(ev_rns)]
    P = P[P.lat.between(29.3, 30.3) & P.lon.between(-95.9, -94.7)]
    days = pd.date_range("2011-01-01", D1, freq="D")
    frames, rn2plant = [], dict(zip(ep.rn, ep.plant_id))
    st_all = ep.assign(day=ep.start_local.dt.normalize()).groupby(["rn", "day"]).size().clip(upper=1)
    for rn, r in P.iterrows():
        near = d[vc.km(r.lat, r.lon, d.lat.values, d.lon.values) <= 5.0]
        if near.empty:
            continue
        yk = near.groupby("day").size().reindex(days, fill_value=0)
        sk = st_all.get(rn, pd.Series(dtype=int))
        fk = pd.DataFrame({"rn": rn, "plant": rn2plant[rn], "day": days, "y": yk.values,
                           "x": exposure(days, sk).values})
        if RUNNING != "start":
            fk = apply_running(fk, running_days(ep[ep.rn == rn], days).values)
        frames.append(fk)
    x = pd.concat(frames)
    x["rym"] = x.rn + "_" + x.day.dt.strftime("%Y-%m")
    x["dow"] = x.day.dt.dayofweek
    log.update({"houston_area_event_rns": len(P), "rns_with_a_case_within_5km": int(x.rn.nunique()),
                "rn_days": len(x), "exposed_rn_days": int(x.x.sum())})
    res = fit(x, "rym + dow", "plant")
    res["cases_per_exposed_rn_day"] = round(float(x[x.x == 1].y.mean()), 4)
    res["cases_per_unexposed_rn_day"] = round(float(x[x.x == 0].y.mean()), 4)
    return {"log": log, "result": res}


def main():
    ep = pd.read_pickle(vc.OUT / "episodes.pkl")
    out = {"rule": "plan D6 item 10", "a_tceq_complaints_county_day": part_a(ep), "b_houston_311_rn_day": part_b(ep)}
    tag = "" if RUNNING == "start" else f"_running_{RUNNING}"
    out["variant"] = {"running": RUNNING, "primary": tag == ""}
    (vc.OUT / f"v4_result{tag}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--running", choices=["start", "drop", "exposed"], default="start")
    RUNNING = ap.parse_args().running
    main()
