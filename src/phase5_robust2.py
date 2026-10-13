"""Phase 5, part B (continued): R8b, R10, R21 and R25 (plan 6.2, D2 items 1, 4 and 6).

R8b   window end 2025, each accident year weighted by the inverse of its expected completeness
      (data/manifests/r8b_completeness.csv: share of accidents filed by the data date, from filing lags of 2005 to
      2018 accidents, averaged over the days of the year). Weights apply to every day of the year in the model.
R10   leave each plant out in turn (exact conditional likelihood, the method of the independent program).
R21   H1 in 2003 to 2005, 2006 to 2014 and 2015 to 2021 (reporting-rule periods): one model with the event term
      interacted with period, and a Wald test that the three coefficients are equal (2 degrees of freedom).
R25   adds, for the plant and the window (days -97 to -8): days with a minimum below 28 F at the nearest GHCN
      station with a minimum that day; days with any NLDN lightning in the plant's 0.1 degree cell; the highest
      wind (gust if reported, else sustained wind) at the nearest airport with an observation that day, in m/s.
      The station series are read from the downloads the first time and kept in data/derived/r25_weather_*.parquet
      (station locations, and the daily values of the stations R25 uses), so that R25 can be rerun without the
      several gigabytes of station files.
Output: data/manifests/phase5_robustness2.json
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
OUT = ROOT / "data" / "manifests" / "phase5_robustness2.json"
STATIONS = P.DER / "r25_weather_stations.parquet"
SERIES = P.DER / "r25_weather_series.parquet"


def summary(coef, se, p, name="x"):
    b, s = float(coef[name]), float(se[name])
    return {"rr": round(2 ** b, 4), "ci": [round(2 ** (b - 1.959964 * s), 4), round(2 ** (b + 1.959964 * s), 4)],
            "p": float(p[name])}


def r8b():
    import pyfixest as pf
    comp = pd.read_csv(ROOT / "data/manifests/r8b_completeness.csv").set_index("year").expected_completeness
    pan = P.h1_run(end="2025-12-31", keep_panel=True)["panel"]
    pan["w"] = 1.0 / pan.year.map(comp).values
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = pf.fepois("y ~ x + xs | plant_year + moy", data=pan, weights="w", vcov={"CRV1": "plant_id"},
                      separation_check=["fe"], fixef_maxiter=100_000, fixef_tol=1e-8)
    return {**summary(m.coef(), m.se(), m.pvalue()), "n_accidents": int(pan.y.sum()),
            "weights_by_year": {int(y): round(1 / c, 3) for y, c in comp.items() if y >= 2019}}


def r10():
    r = P.h1_run(keep_panel=True)
    pan = r["panel"]
    full = r["terms"]["x"]["rr_doubling"]
    res = []
    for p in sorted(pan.plant_id.unique()):
        c, se, pv, _ = P.cond_poisson(pan[pan.plant_id != p], ["x", "xs"])
        res.append((p, 2 ** float(c["x"]), float(pv["x"])))
    d = pd.DataFrame(res, columns=["plant", "rr", "p"])
    d.to_csv(ROOT / "data/derived/r10_leave_one_out.csv", index=False)
    return {"full_rr": round(full, 4), "min_rr": round(d.rr.min(), 4), "max_rr": round(d.rr.max(), 4),
            "median_rr": round(d.rr.median(), 4), "share_p_below_0.05": round(float((d.p < 0.05).mean()), 4),
            "plants": len(d), "largest_single_shift": round(float((d.rr - full).abs().max()), 4)}


def r21():
    pan = P.h1_run(keep_panel=True)["panel"]
    per = np.select([pan.year <= 2005, pan.year <= 2014], ["p2003_2005", "p2006_2014"], "p2015_2021")
    for k in ("p2003_2005", "p2006_2014", "p2015_2021"):
        pan["x_" + k] = pan.x * (per == k)
    terms = ["x_p2003_2005", "x_p2006_2014", "x_p2015_2021", "xs"]
    c, se, p, V = P.cond_poisson(pan, terms)
    b = c[terms[:3]].values
    Vb = V.loc[terms[:3], terms[:3]].values
    L = np.array([[1, -1, 0], [0, 1, -1]])
    w = float((L @ b) @ np.linalg.solve(L @ Vb @ L.T, L @ b))
    out = {k: {**summary(c, se, p, "x_" + k), "n_accidents": int(pan.y[per == k].sum())}
           for k in ("p2003_2005", "p2006_2014", "p2015_2021")}
    out["equality_test"] = {"wald_chi2": round(w, 3), "df": 2, "p": float(chi2.sf(w, 2))}
    return out


def nearest_daily(points, plant_lat, plant_lon, series_by_station, days, k=8):
    """For each day, the value of the nearest station (of the k nearest) that has a value that day."""
    d = P_km(plant_lat, plant_lon, points.lat.values, points.lon.values)
    order = points.index[np.argsort(d)][:k]
    out = pd.Series(np.nan, index=days)
    for st in order:
        s = series_by_station.get(st)
        if s is None:
            continue
        s = s.reindex(days)
        out = out.fillna(s)
        if out.notna().all():
            break
    return out


def P_km(lat1, lon1, lat2, lon2):
    x = np.radians(np.asarray(lon2) - lon1) * np.cos(np.radians((np.asarray(lat2) + lat1) / 2))
    return 6371.0 * np.hypot(x, np.radians(np.asarray(lat2) - lat1))


def weather_from_downloads(plants, attrs):
    """Station series for R25, read from the downloads: GHCN daily minimum temperature (8 nearest stations with TMIN
    per plant), airport daily highest wind (5 nearest per plant) and NLDN lightning days per 0.1 degree cell."""
    # GHCN stations with TMIN (inventory)
    inv = pd.read_fwf(ROOT / "data/external/noaa_ghcn/ghcnd-inventory.txt", header=None,
                      colspecs=[(0, 11), (12, 20), (21, 30), (31, 35), (36, 40), (41, 45)],
                      names=["id", "lat", "lon", "el", "y0", "y1"])
    inv = inv[inv.id.str.startswith("US") & inv.el.eq("TMIN") & (inv.y1 >= 2003)]
    have = {f.name.split(".")[0] for f in (ROOT / "data/external/noaa_ghcn/stations").glob("*.csv.gz")}
    inv = inv[inv.id.isin(have)].drop_duplicates("id").set_index("id")
    near_ids = set()
    for p in plants:
        dd = P_km(attrs.at[p, "lat"], attrs.at[p, "lon"], inv.lat.values, inv.lon.values)
        near_ids |= set(inv.index[np.argsort(dd)][:8])
    tmin = {}
    for st in near_ids:
        x = pd.read_csv(ROOT / f"data/external/noaa_ghcn/stations/{st}.csv.gz", usecols=lambda c: c in ("DATE", "TMIN"),
                        low_memory=False)
        if "TMIN" in x:
            x = x.dropna(subset=["TMIN"])
            tmin[st] = pd.Series(pd.to_numeric(x.TMIN, errors="coerce").values, index=pd.to_datetime(x.DATE)).dropna()
    # ASOS stations: location from the files (first row), daily highest wind
    asos_dir = ROOT / "data/external/iem_asos"
    st_loc, wind = {}, {}
    for f in asos_dir.glob("*.csv.gz"):
        h = pd.read_csv(f, nrows=1)
        st_loc[f.name.split(".")[0]] = (float(h.lat.iloc[0]), float(h.lon.iloc[0]))
    stl = pd.DataFrame(st_loc, index=["lat", "lon"]).T
    near_asos = set()
    for p in plants:
        dd = P_km(attrs.at[p, "lat"], attrs.at[p, "lon"], stl.lat.values, stl.lon.values)
        near_asos |= set(stl.index[np.argsort(dd)][:5])
    for st in near_asos:
        x = pd.read_csv(asos_dir / f"{st}.csv.gz", usecols=["valid", "sknt", "gust"], na_values=["M"], low_memory=False)
        x["day"] = pd.to_datetime(x.valid.str[:10], errors="coerce")
        x["w"] = x.gust.fillna(x.sknt)
        g = x.dropna(subset=["day", "w"]).groupby("day").w.max() * 0.514444
        wind[st] = g
    # NLDN daily counts per 0.1 degree cell
    cells = {(round(attrs.at[p, "lon"], 1), round(attrs.at[p, "lat"], 1)) for p in plants}
    light = {}
    for y in range(2002, 2022):
        f = ROOT / f"data/slices/noaa_nldn/nldn-tiles-{y}_tx.csv.gz"
        x = pd.read_csv(f)
        x["cell"] = list(zip(x.CENTERLON.round(1), x.CENTERLAT.round(1)))
        x = x[x.cell.isin(cells) & (x.TOTAL_COUNT > 0)]
        for c, g in x.groupby("cell"):
            light.setdefault(c, []).append(pd.to_datetime(g.ZDAY.astype(str), format="%Y%m%d"))
    inv_t = inv.loc[[i for i in inv.index if i in tmin], ["lat", "lon"]]
    stl_w = stl.loc[[i for i in stl.index if i in wind], ["lat", "lon"]]
    return inv_t, tmin, stl_w, wind, light


def weather_to_store(inv_t, tmin, stl_w, wind, light, days):
    """Keep the station locations and the daily values inside the study days (the only ones R25 reads)."""
    st = pd.concat([inv_t.assign(kind="tmin"), stl_w.assign(kind="wind")]).rename_axis("id").reset_index()
    st[["kind", "id", "lat", "lon"]].to_parquet(STATIONS, index=False)
    parts = [pd.DataFrame({"kind": kind, "id": i, "lon": np.nan, "lat": np.nan,
                           "day": pd.DatetimeIndex(s.index), "value": s.values.astype(float)})
             for kind, d in (("tmin", tmin), ("wind", wind)) for i, s in d.items()]
    parts += [pd.DataFrame({"kind": "light", "id": "", "lon": c[0], "lat": c[1], "day": pd.DatetimeIndex(s),
                            "value": 1.0}) for c, lst in light.items() for s in lst]
    se = pd.concat(parts, ignore_index=True)
    se[se.day.between(days[0], days[-1])].to_parquet(SERIES, index=False)


def weather_from_store():
    st = pd.read_parquet(STATIONS)
    se = pd.read_parquet(SERIES)
    out = []
    for kind in ("tmin", "wind"):
        pts = st[st.kind == kind].set_index("id")[["lat", "lon"]]
        g = dict(list(se[se.kind == kind].groupby("id", sort=False)))
        series = {i: pd.Series(g[i].value.values, index=pd.DatetimeIndex(g[i].day.values)) if i in g
                  else pd.Series(dtype=float, index=pd.DatetimeIndex([])) for i in pts.index}
        out += [pts, series]
    lt = se[se.kind == "light"]
    light = {(lo, la): [pd.DatetimeIndex(g.day.values)] for (lo, la), g in lt.groupby(["lon", "lat"], sort=False)}
    return out[0], out[1], out[2], out[3], light


def r25():
    r = P.h1_run(keep_panel=True)
    pan = r["panel"]
    attrs = pd.read_csv(P.DER / "plant_attributes.csv").set_index("plant_id")
    plants = sorted(pan.plant_id.unique())
    days = pd.date_range(P.h1.STUDY_START - pd.Timedelta(days=98), "2021-12-31", freq="D")
    if STATIONS.exists() and SERIES.exists():
        inv_t, tmin, stl_w, wind, light = weather_from_store()
    else:
        inv_t, tmin, stl_w, wind, light = weather_from_downloads(plants, attrs)
        weather_to_store(inv_t, tmin, stl_w, wind, light, days)
    cols = {"freeze_days": np.zeros(len(pan)), "lightning_days": np.zeros(len(pan)), "max_wind_ms": np.zeros(len(pan))}
    log = {"ghcn_stations_read": len(tmin), "asos_stations_read": len(wind), "plants": len(plants)}
    for p, idx in pan.groupby("plant_id").indices.items():
        la, lo = attrs.at[p, "lat"], attrs.at[p, "lon"]
        tm = nearest_daily(inv_t, la, lo, tmin, days)
        frz = (tm < -22.22).astype(float).where(tm.notna(), 0.0)
        wd = nearest_daily(stl_w, la, lo, wind, days, k=5)
        lt = pd.Series(0.0, index=days)
        for s in light.get((round(lo, 1), round(la, 1)), []):
            lt.loc[lt.index.isin(s)] = 1.0
        d = pd.DatetimeIndex(pan.day.values[idx])

        def win_sum(s):
            cs = s.cumsum()
            return (cs.shift(8) - cs.shift(98)).reindex(d).fillna(0).values

        cols["freeze_days"][idx] = win_sum(frz)
        cols["lightning_days"][idx] = win_sum(lt)
        cols["max_wind_ms"][idx] = wd.rolling(90, min_periods=1).max().shift(8).reindex(d).fillna(0).values
    for k, v in cols.items():
        pan[k] = v
    log["means"] = {k: round(float(np.mean(v)), 3) for k, v in cols.items()}
    terms = ["x", "xs", "freeze_days", "lightning_days", "max_wind_ms"]
    c, se, p, _ = P.cond_poisson(pan, terms)
    return {**summary(c, se, p), "controls": {t: {"beta": float(c[t]), "p": float(p[t])} for t in terms[2:]},
            "log": log}


def main():
    out = {}
    for name, fn in (("R21_rule_periods", r21), ("R8b_end_2025_weighted", r8b), ("R10_leave_one_plant_out", r10),
                     ("R25_weather_controls", r25)):
        try:
            out[name] = fn()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            out[name] = {"error": f"{type(e).__name__}: {e}"}
        print(name, json.dumps(out[name])[:400], flush=True)
        OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
