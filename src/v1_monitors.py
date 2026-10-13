"""Check V1 (plan D6 item 7): air monitors downwind of reported events.

For each D6 episode with a valid end and a location, and each pollutant family it reported (SO2, NOx, H2S, benzene,
1,3-butadiene, VOC as total non-methane organics), the nearest monitor within 10 km that measures the family and has
at least one valid hour in the episode's first 72 hours. NOx uses NO2 where the site has it, else total NOx.
Hours are UTC; a monitor's local standard hour of day and month are fixed offsets of UTC, so "same month and hour of
day" is taken on local standard time (UTC-6, or UTC-7 for El Paso and Hudspeth monitors).
Wind: resultant direction and speed at the monitor site; if missing that hour, the nearest airport within 50 km
(the last routine observation inside the hour). Hours with wind under 1 m/s are not used. Downwind: the wind comes
from within 30 degrees of the bearing from the monitor to the event site.
Comparison hours: same monitor, calendar month and hour of day, downwind by the same rule, other years of 2003 to
2021, on local days with no reported event of any type at any RN within 10 km of the monitor (from the day before
an event starts to the day after it ends; plan D7). At least 10 comparison hours are needed.
Measures by family: (a) ratio of sums of mean downwind episode concentration to mean comparison concentration over
episodes, 95% interval from 2,000 bootstrap resamples of plants; (b) share of episodes whose highest downwind hour
exceeds the 95th percentile of its comparison hours. Placebo: the same clock hours one year earlier (one year later if
the earlier year is outside 2003 to 2021 or falls on an excluded day), same rules.

Output: data/derived/vchecks/v1_result.json, v1_pairs.parquet
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vchecks_common as vc  # noqa: E402

FAMS = ["so2", "nox", "h2s", "benzene", "butadiene", "voc"]
MOUNTAIN_SITES = ("48_141_", "48_229_")   # El Paso and Hudspeth county monitors keep Mountain time
Y0, Y1 = 2003, 2021


def angdiff(a, b):
    return np.abs((np.asarray(a) - np.asarray(b) + 180) % 360 - 180)


def load_asos(stations):
    out = {}
    for st in stations:
        f = vc.ROOT / "data/external/iem_asos" / f"{st}.csv.gz"
        d = pd.read_csv(f, usecols=["valid", "drct", "sknt"], na_values=["M"], low_memory=False)
        d = d[d.valid.str[:4].astype(int).between(Y0 - 1, Y1 + 1)].dropna()
        d["utc"] = pd.to_datetime(d.valid).dt.floor("h")
        d = d.groupby("utc").last()
        out[st] = pd.DataFrame({"wd": d.drct.values, "ws": d.sknt.values * 0.514444}, index=d.index)
    return out


def main():
    ep = pd.read_pickle(vc.OUT / "episodes.pkl")
    ep = ep[ep.valid_end & ep.lat.notna()].copy()
    ep["end72"] = np.minimum(ep.end_utc, ep.start_utc + pd.Timedelta(hours=72))
    sites = pd.read_csv(vc.OUT / "monitor_sites.csv", index_col=0)
    # all reported events (any type, any plant) for the exclusion days
    # D7: an event blocks every local day it runs, from the day before its start to the day after its end; a missing
    # end, an end before the start, or an end more than 365 days after the start (end-date typos) blocks its start day
    allev = pd.read_csv(vc.DER / "events_v2.csv.gz", usecols=["incident", "rn", "event_date"]).dropna()
    det = pd.read_parquet(vc.DER / "details_table.parquet", columns=["incident", "end_text"])
    det["incident"] = det.incident.astype(int)
    allev = allev.merge(det, on="incident", how="left")
    pts = vc.rn_points()
    allev = allev.join(pts, on="rn").dropna(subset=["lat"])
    d0 = pd.to_datetime(allev.event_date).values.astype("datetime64[D]").astype(np.int64)
    d1 = pd.to_datetime(allev.end_text, format="%m/%d/%Y %I:%M %p", errors="coerce").values.astype("datetime64[D]")
    d1 = np.where(np.isnat(d1), -10**9, d1.astype(np.int64))
    bad = (d1 < d0) | (d1 - d0 > 365)
    allev["d0"], allev["d1"] = d0, np.where(bad, d0, d1)
    excl = {}
    for s, r in sites.iterrows():
        near = allev[vc.km(r.lat, r.lon, allev.lat.values, allev.lon.values) <= 10.0]
        excl[s] = set(np.concatenate([np.arange(a - 1, b + 2) for a, b in zip(near.d0, near.d1)] or [[]]).tolist())
    # wind: site, then nearest airport within 50 km
    wind = pd.read_parquet(vc.OUT / "hourly_wd.parquet").rename(columns={"value": "wd"})
    ws = pd.read_parquet(vc.OUT / "hourly_ws.parquet").rename(columns={"value": "ws"})
    sw = wind.merge(ws[["site", "utc", "ws"]], on=["site", "utc"], how="inner")
    sw = {s: g.set_index("utc")[["wd", "ws"]] for s, g in sw.groupby("site")}
    ast = pd.read_csv(vc.DER / "monitors/asos_station_years.csv").groupby("station")[["lat", "lon"]].median()
    nearest_airport = {}
    for s, r in sites.iterrows():
        d = vc.km(r.lat, r.lon, ast.lat.values, ast.lon.values)
        if d.min() <= 50:
            nearest_airport[s] = ast.index[d.argmin()]
    asos = load_asos(sorted(set(nearest_airport.values())))
    log = {"episodes_valid_end_with_location": len(ep), "monitor_sites_considered": len(sites),
           "sites_with_airport_within_50km": len(nearest_airport),
           "exclusion_events": len(allev), "exclusion_events_end_used": int((~bad).sum()),
           "exclusion_events_end_over_365_days": int(((d1 - d0) > 365).sum())}

    def site_frame(site, conc):
        """Hourly frame for one site and family: value, wind used, local month/hour/year/day, excluded flag."""
        c = conc[conc.site == site].set_index("utc").value
        w = sw.get(site)
        f = pd.DataFrame({"value": c})
        if w is not None:
            f = f.join(w)
        else:
            f["wd"], f["ws"] = np.nan, np.nan
        miss = f.wd.isna() | f.ws.isna()
        ap = nearest_airport.get(site)
        if ap is not None and miss.any():
            a = asos[ap].reindex(f.index[miss])
            f.loc[miss, "wd"], f.loc[miss, "ws"] = a.wd.values, a.ws.values
        off = 7 if site.startswith(MOUNTAIN_SITES) else 6
        loc = f.index - pd.Timedelta(hours=off)
        f["month"], f["hour"], f["year"] = loc.month, loc.hour, loc.year
        f["lday"] = loc.values.astype("datetime64[D]").astype(np.int64)
        f["excluded"] = f.lday.isin(excl.get(site, set())).values
        f["wind_ok"] = f.ws >= 1.0
        return f

    results, pairs = {}, []
    for fam in FAMS:
        p = vc.OUT / f"hourly_{fam}.parquet"
        if not p.exists():
            continue
        conc = pd.read_parquet(p)
        if fam == "nox":
            tot = vc.OUT / "hourly_nox_total.parquet"
            if tot.exists():
                t = pd.read_parquet(tot)
                t = t[~t.site.isin(set(conc.site))]
                conc = pd.concat([conc, t])
        fsites = sites.loc[sites.index.intersection(conc.site.unique())]
        frames = {}
        e = ep[ep[f"fam_{fam}"]]
        n_none, rows = 0, []
        for r in e.itertuples(index=False):
            d = vc.km(r.lat, r.lon, fsites.lat.values, fsites.lon.values)
            order = np.argsort(d)
            chosen = None
            hours = pd.date_range(r.start_utc.floor("h"), r.end72.floor("h"), freq="h")
            for i in order:
                if d[i] > 10:
                    break
                s = fsites.index[i]
                if s not in frames:
                    frames[s] = site_frame(s, conc)
                f = frames[s]
                if f.value.reindex(hours).notna().any():
                    chosen = (s, d[i])
                    break
            if chosen is None:
                n_none += 1
                continue
            s, dist = chosen
            f = frames[s]
            brg = float(vc.bearing(sites.at[s, "lat"], sites.at[s, "lon"], r.lat, r.lon))
            down = f.wind_ok & (angdiff(f.wd, brg) <= 30) & f.value.notna()

            def measure(hrs, year_excl):
                h = f.reindex(hrs)
                dh = h[down.reindex(hrs, fill_value=False).values]
                if dh.empty:
                    return None
                months, hours_ = set(dh.month), set(dh.hour)
                comp = f[down & ~f.excluded & (f.year != year_excl) & f.year.between(Y0, Y1)
                         & f.month.isin(months) & f.hour.isin(hours_)]
                # same month AND hour as each downwind hour: keep comparison hours whose (month, hour) pair occurs
                pairs_ = set(zip(dh.month, dh.hour))
                comp = comp[[(m, hh) in pairs_ for m, hh in zip(comp.month, comp.hour)]]
                if len(comp) < 10:
                    return {"n_down": len(dh), "n_comp": len(comp)}
                return {"n_down": len(dh), "n_comp": len(comp), "E": float(dh.value.mean()),
                        "C": float(comp.value.mean()), "peak": float(dh.value.max()),
                        "p95": float(comp.value.quantile(0.95))}

            yr = (r.start_utc - pd.Timedelta(hours=6)).year
            real = measure(hours, yr)
            # placebo one year earlier, else later
            plc = None
            for shift in (-1, 1):
                ph = hours + pd.DateOffset(years=shift)
                py = yr + shift
                if not (Y0 <= py <= Y1):
                    continue
                fr = f.reindex(ph)
                if fr.value.notna().sum() == 0 or fr.excluded.fillna(False).astype(bool).any():
                    continue
                plc = measure(ph, py)
                break
            rows.append({"family": fam, "plant_id": r.plant_id, "rn": r.rn, "site": s, "km": round(float(dist), 2),
                         "start_utc": r.start_utc, **{f"r_{k}": v for k, v in (real or {}).items()},
                         **{f"p_{k}": v for k, v in (plc or {}).items()}})
        df = pd.DataFrame(rows)
        pairs.append(df)
        res = {"episodes_reporting_family": int(len(e)), "no_monitor_with_data_within_10km": n_none,
               "paired": len(df)}
        ok = df.dropna(subset=["r_E"]) if "r_E" in df else df.iloc[0:0]
        res["no_downwind_hour"] = int(df["r_n_down"].isna().sum()) if "r_n_down" in df else len(df)
        res["under_10_comparison_hours"] = int((df.get("r_n_down").notna() & df.get("r_E", pd.Series(np.nan, index=df.index)).isna()).sum()) if len(df) else 0
        res["analysed"] = len(ok)
        if len(ok):
            ratio = ok.r_E.sum() / ok.r_C.sum()
            rng = np.random.default_rng(1)
            plants = ok.plant_id.unique()
            g = {p_: x for p_, x in ok.groupby("plant_id")}
            bs = []
            for _ in range(2000):
                pick = rng.choice(plants, len(plants), replace=True)
                b = pd.concat([g[p_] for p_ in pick])
                bs.append(b.r_E.sum() / b.r_C.sum())
            res.update({"plants": int(len(plants)), "monitors": int(ok.site.nunique()),
                        "ratio": round(float(ratio), 3),
                        "ratio_ci95": [round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)],
                        "share_peak_above_p95": round(float((ok.r_peak > ok.r_p95).mean()), 3),
                        "median_downwind_hours": float(ok.r_n_down.median())})
            pk = ok.dropna(subset=["p_E"]) if "p_E" in ok else ok.iloc[0:0]
            if len(pk):
                res.update({"placebo_analysed": len(pk),
                            "placebo_ratio": round(float(pk.p_E.sum() / pk.p_C.sum()), 3),
                            "placebo_share_peak_above_p95": round(float((pk.p_peak > pk.p_p95).mean()), 3),
                            "real_share_same_episodes": round(float((pk.r_peak > pk.r_p95).mean()), 3)})
        results[fam] = res
        print(fam, json.dumps(res), flush=True)
    pd.concat(pairs).to_parquet(vc.OUT / "v1_pairs.parquet", index=False)
    out = {"rule": "plan D6 item 7", "log": log, "by_family": results}
    (vc.OUT / "v1_result.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
