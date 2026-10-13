"""Phase 5, part B: the robustness checks R1 to R30 of the primary H1 model (plan 6.2, D2, D4, D6, D7).

Each check changes one thing in the primary model (window end 2021, extended links, merged doubles, days -97 to -8,
unplanned events, statewide control, plant-year strata, month-of-year effects) and reports the rate ratio per
doubling with its 95% interval. Rules for data the plan names but does not spell out are in the D9 entry of the
plan and in the docstrings of storm_zones.py and plant_attributes.py.
Output: data/manifests/phase5_robustness.json
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h1_numpy  # noqa: E402
import phase5_h1 as P  # noqa: E402
import storm_zones  # noqa: E402

ROOT = P.h1.ROOT
DER = P.DER
SL = ROOT / "data" / "slices"
OUT = ROOT / "data" / "manifests" / "phase5_robustness.json"
R = dict(dtype=str, keep_default_na=False)


def attrs():
    return pd.read_csv(DER / "plant_attributes.csv").set_index("plant_id")


# ---------- day masks (which plant-days to drop) ----------

def window_overlaps(pan, periods_by_key, key_of_plant, lo_off=97, hi_off=8, include_day=False, after=0):
    """True where the plant-day's window (days -lo_off..-hi_off), or the day itself if include_day, overlaps a
    period [begin, end + after] listed for the plant's key (county)."""
    mask = np.zeros(len(pan), dtype=bool)
    keys = pan.plant_id.map(key_of_plant)
    for k, idx in pd.Series(np.arange(len(pan))).groupby(keys.values).indices.items():
        per = periods_by_key.get(k)
        if per is None or not len(per):
            continue
        d = pan.day.values[idx].astype("datetime64[D]").astype(np.int64)
        b = per[:, 0]
        e = per[:, 1] + after
        lo, hi = d - lo_off, d - hi_off
        hit = ((lo[:, None] <= e[None, :]) & (hi[:, None] >= b[None, :])).any(axis=1)
        if include_day:
            hit |= ((d[:, None] >= b[None, :]) & (d[:, None] <= e[None, :])).any(axis=1)
        mask[idx] = hit
    return mask


def to_days(s):
    return pd.to_datetime(s).values.astype("datetime64[D]").astype(np.int64)


def r5_mask_fn():
    d, log = storm_zones.storm_county_days(["Hurricane (Typhoon)", "Tropical Storm", "Winter Storm", "Ice Storm",
                                            "Extreme Cold/Wind Chill"])
    per = {c: np.column_stack([to_days(g.begin), to_days(g.end)]) for c, g in d.groupby("counties")}
    county = attrs().county
    return (lambda pan: window_overlaps(pan, per, county)), log


def r22_mask_fn():
    f = pd.read_csv(ROOT / "data/external/fema/DisasterDeclarationsSummaries.csv.gz", low_memory=False)
    f = f[f.state.eq("TX") & f.declarationType.isin(["DR", "EM"])].copy()
    title = f.declarationTitle.fillna("").str.upper()
    keep = (f.incidentType.isin(["Hurricane", "Severe Storm", "Flood", "Severe Ice Storm", "Winter Storm", "Fire",
                                 "Freezing"])
            | title.str.contains("TROPICAL STORM") | (f.incidentType.eq("Tornado") & title.str.contains("STORM")))
    f = f[keep]
    f["b"] = to_days(f.incidentBeginDate.str[:10])
    f["e"] = to_days(f.incidentEndDate.str[:10])
    cf = pd.read_csv(SL / "rmp_raw/tlkpCountyFIPSCodes.csv.gz", **R)
    name = dict(zip(cf[cf.State_Code == "TX"].County_Code.astype(int), cf[cf.State_Code == "TX"].County_Name.str.upper()))
    f["county"] = f.fipsCountyCode.map(name)
    statewide = f[f.fipsCountyCode.eq(0)]
    per = {}
    for c in set(name.values()):
        g = pd.concat([f[f.county.eq(c)], statewide])
        per[c] = np.column_stack([g.b.values, g.e.values])
    county = attrs().county
    log = {"declarations": int(f.disasterNumber.nunique()), "statewide_rows": len(statewide)}
    return (lambda pan: window_overlaps(pan, per, county, include_day=True, after=7)), log


def hurdat_points():
    f = sorted((ROOT / "data/external/noaa_hurdat").glob("hurdat2-1851-*.txt"))[-1]
    rows, sid = [], None
    for line in open(f):
        p = [x.strip() for x in line.split(",")]
        if p[0].startswith("AL") and len(p) >= 3 and not p[1].isdigit():
            sid = p[0]
            continue
        t = pd.Timestamp(p[0] + p[1].zfill(4))
        lat = float(p[4][:-1]) * (1 if p[4].endswith("N") else -1)
        lon = float(p[5][:-1]) * (-1 if p[5].endswith("W") else 1)
        rows.append((sid, t, p[3], lat, lon))
    d = pd.DataFrame(rows, columns=["sid", "t", "status", "lat", "lon"])
    d = d[d.t.dt.year.between(2002, 2026)]
    # hourly points between consecutive fixes of the same storm where both fixes are HU or TS
    out = []
    for sid, g in d.groupby("sid"):
        g = g.sort_values("t").reset_index(drop=True)
        for i in range(len(g)):
            if g.status[i] in ("HU", "TS"):
                out.append((g.t[i], g.lat[i], g.lon[i]))
            if i + 1 < len(g) and g.status[i] in ("HU", "TS") and g.status[i + 1] in ("HU", "TS"):
                h = int((g.t[i + 1] - g.t[i]) / pd.Timedelta(hours=1))
                for k in range(1, h):
                    w = k / h
                    out.append((g.t[i] + pd.Timedelta(hours=k), g.lat[i] + w * (g.lat[i + 1] - g.lat[i]),
                                g.lon[i] + w * (g.lon[i + 1] - g.lon[i])))
    return pd.DataFrame(out, columns=["t", "lat", "lon"]), f.name


def r23_mask_fn():
    pts, fname = hurdat_points()
    a = attrs()
    per = {}
    for p, r in a.dropna(subset=["lat"]).iterrows():
        near = pts[_km(r.lat, r.lon, pts.lat.values, pts.lon.values) <= 150]
        if len(near):
            dd = np.unique(near.t.values.astype("datetime64[D]").astype(np.int64))
            per[p] = np.column_stack([dd, dd])
    def mask(pan):
        # drop days within 7 days (either side) of a passage: the day itself within [passage - 7, passage + 7]
        m = np.zeros(len(pan), dtype=bool)
        for p, idx in pan.groupby("plant_id").indices.items():
            pr = per.get(p)
            if pr is None:
                continue
            d = pan.day.values[idx].astype("datetime64[D]").astype(np.int64)
            m[idx] = (np.abs(d[:, None] - pr[None, :, 0]) <= 7).any(axis=1)
        return m
    return mask, {"hurdat_file": fname, "plants_with_a_passage": len(per)}


def _km(lat1, lon1, lat2, lon2):
    x = np.radians(np.asarray(lon2) - lon1) * np.cos(np.radians((np.asarray(lat2) + lat1) / 2))
    return 6371.0 * np.hypot(x, np.radians(np.asarray(lat2) - lat1))


def r24_mask(pan):
    return pan.day.between("2020-03-01", "2020-12-31").values


def r28_mask_fn():
    f = pd.read_csv(SL / "rmp_raw/tblS1Facilities.csv.gz", usecols=["EPAFacilityID", "ParentCompanyName",
                                                                   "OperatorName", "ReceiptDate"], **R)
    pm = pd.read_csv(DER / "plant_members_v2.csv", **R)
    plant_of = dict(zip(pm[pm.id_type == "RMP"].id, pm[pm.id_type == "RMP"].plant_id))
    legal = r"\b(INC|INCORPORATED|LLC|L L C|LP|L P|LTD|LIMITED|CO|COMPANY|CORP|CORPORATION|LLP|PLC|NA|USA|US)\b"

    def norm(s):
        s = re.sub(r"[^A-Z0-9 ]", " ", s.upper())
        s = re.sub(legal, " ", s)
        return re.sub(r"\s+", " ", s).strip()

    f["parent"] = f.ParentCompanyName.map(norm)
    f["oper"] = f.OperatorName.map(norm)
    f = f.sort_values(["EPAFacilityID", "ReceiptDate"])
    changes = []
    for fac, g in f.groupby("EPAFacilityID"):
        prev = None
        for r in g.itertuples():
            if prev is not None:
                ch = (r.parent and prev.parent and r.parent != prev.parent) or (r.oper and prev.oper and r.oper != prev.oper)
                if ch:
                    changes.append((plant_of.get(fac), r.ReceiptDate[:10]))
            prev = r
    ch = pd.DataFrame(changes, columns=["plant_id", "date"]).dropna()
    per = {p: np.column_stack([to_days(g.date), to_days(g.date) + 365]) for p, g in ch.groupby("plant_id")}

    def mask(pan):
        m = np.zeros(len(pan), dtype=bool)
        for p, idx in pan.groupby("plant_id").indices.items():
            pr = per.get(p)
            if pr is None:
                continue
            d = pan.day.values[idx].astype("datetime64[D]").astype(np.int64)
            m[idx] = ((d[:, None] > pr[None, :, 0]) & (d[:, None] <= pr[None, :, 1])).any(axis=1)
        return m
    return mask, {"ownership_or_operator_changes": len(ch), "plants_with_a_change": int(ch.plant_id.nunique())}


# ---------- added covariates ----------

def r27_cols(acc_all_dates):
    by = {p: to_days(g.date) for p, g in acc_all_dates.groupby("plant_id")}

    def add(pan):
        v = np.zeros(len(pan))
        for p, idx in pan.groupby("plant_id").indices.items():
            a = by.get(p)
            if a is None:
                continue
            d = pan.day.values[idx].astype("datetime64[D]").astype(np.int64)
            v[idx] = ((d[:, None] - a[None, :] >= 1) & (d[:, None] - a[None, :] <= 365)).any(axis=1)
        pan["prior_accident_365"] = v
        return pan
    return add


def monthly_window_mean(series_by_month, days, lo_off=97, hi_off=8):
    """Mean of a monthly series over the days of each window (each day takes its month's value)."""
    span = pd.date_range(days.min() - pd.Timedelta(days=lo_off + 1), days.max(), freq="D")
    daily = pd.Series(series_by_month.reindex(span.to_period("M")).values, index=span).astype(float)
    cs = daily.fillna(daily.mean()).cumsum()
    w = cs.shift(hi_off) - cs.shift(lo_off + 1)
    return days.map(w / (lo_off - hi_off + 1))


def r26_cols():
    x = pd.read_excel(ROOT / "data/external/eia/series/PET_PNP_UNC_DCU_R3B_M.xls", sheet_name="Data 1", header=2)
    util_col = [c for c in x.columns if "Utilization" in str(c)][0]
    util = pd.Series(pd.to_numeric(x[util_col], errors="coerce").values, index=pd.to_datetime(x["Date"]).dt.to_period("M"))

    def fed(code):
        rows = [l.split() for l in open(ROOT / "data/external/fed_g17/ip_sa.txt") if l.startswith(f'"{code}"')]
        vals = {}
        for r in rows:
            y = int(r[1])
            for m, v in enumerate(r[2:14], start=1):
                vals[pd.Period(f"{y}-{m:02d}", "M")] = float(v)
        return pd.Series(vals)
    chem, ref = fed("G325"), fed("G32411")

    def add(pan):
        pan["util_txgc"] = monthly_window_mean(util, pan.day).values
        pan["ip_chem"] = monthly_window_mean(chem, pan.day).values
        pan["ip_ref"] = monthly_window_mean(ref, pan.day).values
        return pan
    return add, {"eia_column": util_col}


def main():
    plants, ev, acc, acc_all, risk = P.tables("v2")
    a = attrs()
    out = {}

    def run(name, note="", **kw):
        try:
            r = P.h1_run(**kw)
            t = r["terms"]["x"]
            out[name] = {"rr": round(t["rr_doubling"], 4), "ci": [round(c, 4) for c in t["ci"]], "p": t["p"],
                         "n_accidents": r["n_accidents"], "n_plants": r["n_plants"], "n_days": r["n_days"],
                         "log": r["log"], "fitted_by": r.get("fitted_by"), "note": note,
                         "other_terms": {k: {"rr": round(v["rr_doubling"], 4), "p": v["p"]}
                                         for k, v in r["terms"].items() if k != "x"}}
        except Exception as e:  # noqa: BLE001
            out[name] = {"error": f"{type(e).__name__}: {e}", "note": note}
        print(name, {k: out[name].get(k) for k in ("rr", "ci", "p", "n_accidents", "error")}, flush=True)
        OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")

    run("primary", "Phase 4 primary, reproduced")
    for w in (30, 180, 365):
        run(f"R1_window_{w}", window=w)
    out["R29_tceq_coordinates"] = {"not_run": "needs TCEQ Central Registry coordinates requested under the Public "
                                              "Information Act; not received"}
    for g in (0, 1, 30):
        run(f"R2_gap_{g}", gap=g)
    run("R3_plus_opacity", event_types=("EMISSIONS EVENT", "EXCESS OPACITY"))
    run("R3_all_types", event_types=("EMISSIONS EVENT", "EXCESS OPACITY", "MAINTENANCE", "AIR STARTUP", "AIR SHUTDOWN"))
    run("R4_report_date", by="report")
    m5, l5 = r5_mask_fn()
    run("R5_noaa_storms", f"storm records {l5}", drop_days=m5)
    run("R6_regional_count", statewide="region", region_of=a.region)
    run("R7_one_to_one", plants_subset="one_to_one")
    for end in ("2022-12-31", "2023-12-31", "2025-12-31"):
        run(f"R8_end_{end[:4]}", end=end)
    acc9 = acc[~acc.within_3d_of_previous.astype(str).eq("True")]
    run("R9_merge_within_3_days", accidents=acc9)
    run("R12_plant_strata", formula_fe="plant_id + year + moy")
    run("R13_every_report", merge=False)
    run("R14_calendar_month", formula_fe="plant_year + ym", terms=["x"])
    run("R15_drop_chains_120", drop_chain_cases=120)
    run("R16_drop_post_120", post_excl=120)
    run("R17", exclude="r17")
    run("R17_extended", exclude="r17_extended")
    r18 = pd.read_csv(ROOT / "data/manifests/r18_original_dates.csv", **R) if (
        ROOT / "data/manifests/r18_original_dates.csv").exists() else None
    if r18 is not None:
        a18 = acc.copy()
        orig = dict(zip(r18.study_record, pd.to_datetime(r18.original)))
        a18["date"] = [orig.get(i, d) for i, d in zip(a18.AccidentHistoryID, a18.date)]
        run("R18_original_dates", accidents=a18)
    run("R19_no_merges", accidents=r19_table())
    run("R20_registry_links", links="v1")
    m22, l22 = r22_mask_fn()
    run("R22_fema", f"{l22}", drop_days=m22)
    m23, l23 = r23_mask_fn()
    run("R23_hurdat_150km", f"{l23}", drop_days=m23)
    run("R24_drop_covid_2020", drop_days=r24_mask)
    add26, l26 = r26_cols()
    run("R26_industry_controls", f"{l26}", extra_cols=add26, extra_terms=("util_txgc", "ip_chem", "ip_ref"))
    run("R27_prior_accident", extra_cols=r27_cols(acc_all_dates(acc)), extra_terms=("prior_accident_365",))
    m28, l28 = r28_mask_fn()
    run("R28_ownership_change", f"{l28}", drop_days=m28)
    run("R30_absorbed", exclude="r30")
    run("R11_conditional_logit", family="logit")
    run("R11_negative_binomial", family="negbin")


def acc_all_dates(acc):
    """All accidents at each plant, any date (prior-accident indicator R27 looks back before the study start)."""
    return acc[["plant_id", "date"]].dropna()


def r19_table():
    """R19: no duplicate merges, every record with its own filed date (the merge set the kept record's date)."""
    acc = pd.read_csv(DER / "accidents_v2.csv", parse_dates=["date"], keep_default_na=False,
                      dtype={"AccidentHistoryID": str, "EPAFacilityID": str, "merged_into": str})
    raw = pd.read_csv(SL / "rmp_accidents_tx.csv.gz", usecols=["AccidentHistoryID", "AccidentDate"], **R)
    acc["date"] = acc.AccidentHistoryID.map(dict(zip(raw.AccidentHistoryID, pd.to_datetime(raw.AccidentDate))))
    acc["plant_id"] = acc.plant_id.replace("", np.nan)
    return acc


if __name__ == "__main__":
    main()
