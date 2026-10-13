"""Check V2 (plan D6 item 8): satellite heat (VIIRS night detections) on flaring-event nights.

Unit: RN-night (local evening date: a detection at local time before noon belongs to the previous evening).
Satellites: Suomi NPP 2012 to 2021 and NOAA-20 2018 to 2021, night detections, any FIRMS type, within 1 km.
Event nights: nights overlapping the first 72 hours of a D6 episode with the flare flag. Comparison nights: same RN
and calendar month, other years, no reported event of any type at that RN within 2 days of its span (plan D7). RNs with another event-reporting RN within 1 km are left out.
Outcome: any detection within 1 km. Model: conditional logistic regression (RN-by-month strata), fitted exactly from
per-stratum counts (with one binary exposure the conditional likelihood of a stratum is the noncentral hypergeometric
probability); the interval comes from 2,000 bootstrap resamples of RNs. The stratified Mantel-Haenszel odds ratio is
shown beside it as a check, with detection rates. Only RNs with at least one flaring episode in the satellite years enter.

Output: data/derived/vchecks/v2_result.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vchecks_common as vc  # noqa: E402

FIRMS = vc.ROOT / "data" / "slices" / "nasa_firms"


CLOCK = "solar"     # "solar" (primary) or "clock" (local clock time; sensitivity check, plan D7 addendum)
NIGHT = "noon"      # "noon" (primary: noon to noon) or "evening" (20:00 to 06:00; sensitivity check)


def to_local(utc, lon, tz="America/Chicago"):
    """Naive local time: solar (shift by longitude) or clock time in the RN's time zone."""
    utc = pd.Series(pd.to_datetime(utc)).reset_index(drop=True)
    if CLOCK == "solar":
        return utc + pd.to_timedelta(lon / 15.0, unit="h")
    return utc.dt.tz_localize("UTC").dt.tz_convert(tz).dt.tz_localize(None)


def local_night(utc, lon, tz="America/Chicago"):
    """Local evening date: times before local noon go to the previous date."""
    return (to_local(utc, lon, tz) - pd.Timedelta(hours=12)).dt.normalize()


def event_nights(start_utc, end_utc, lon, tz):
    """Nights an episode counts for: noon-to-noon nights it overlaps, or (evening rule) nights whose 20:00 to 06:00
    window it overlaps."""
    a, b = local_night(start_utc, lon, tz)[0], local_night(end_utc, lon, tz)[0]
    span = pd.date_range(a, max(a, b), freq="D")
    if NIGHT == "noon":
        return span
    ls, le = to_local(start_utc, lon, tz)[0], to_local(end_utc, lon, tz)[0]
    return [n for n in span if n + pd.Timedelta(hours=20) <= le and n + pd.Timedelta(hours=30) >= ls]


def mh_or(tab):
    """tab: per stratum a, b, c, d = exposed+det, exposed+no, unexposed+det, unexposed+no."""
    a, b, c, d = (tab[k].astype(float) for k in "abcd")
    n = a + b + c + d
    R, S = a * d / n, b * c / n
    P, Q = (a + d) / n, (b + c) / n
    orr = R.sum() / S.sum()
    var = ((P * R).sum() / (2 * R.sum() ** 2) + ((P * S + Q * R).sum()) / (2 * R.sum() * S.sum())
           + (Q * S).sum() / (2 * S.sum() ** 2))
    se = np.sqrt(var)
    return orr, np.exp(np.log(orr) - 1.96 * se), np.exp(np.log(orr) + 1.96 * se)


def cl_fit(t, se=True):
    """Exact conditional logistic MLE for one binary exposure from per-stratum counts a, b, c, d."""
    from scipy.optimize import minimize_scalar
    from scipy.special import gammaln
    n1 = (t.a + t.b).values.astype(int)
    n0 = (t.c + t.d).values.astype(int)
    dd = (t.a + t.c).values.astype(int)
    aa = t.a.values.astype(int)
    lo = np.maximum(0, dd - n0)
    hi = np.minimum(n1, dd)
    K = int((hi - lo).max()) + 1
    u = lo[:, None] + np.arange(K)[None, :]
    valid = u <= hi[:, None]
    uu = np.where(valid, u, lo[:, None])
    lc = (gammaln(n1 + 1)[:, None] - gammaln(uu + 1) - gammaln(n1[:, None] - uu + 1)
          + gammaln(n0 + 1)[:, None] - gammaln(dd[:, None] - uu + 1) - gammaln(n0[:, None] - dd[:, None] + uu + 1))
    lc = np.where(valid, lc, -np.inf)

    def nll(b):
        w = lc + b * uu
        m = w.max(axis=1, keepdims=True)
        lse = m[:, 0] + np.log(np.exp(w - m).sum(axis=1))
        return -(b * aa - lse).sum()

    b = minimize_scalar(nll, bounds=(-10, 10), method="bounded", options={"xatol": 1e-8}).x
    if not se:
        return b, None
    h = 1e-4
    info = (nll(b + h) - 2 * nll(b) + nll(b - h)) / h ** 2
    return b, 1 / np.sqrt(info)


def main():
    ep = pd.read_pickle(vc.OUT / "episodes.pkl").dropna(subset=["lat"])
    allev = pd.read_csv(vc.DER / "events_v2.csv.gz", usecols=["rn"]).rn.unique()
    pts = vc.rn_points()
    # neighbours: another event-reporting RN within 1 km
    P = pts.loc[pts.index.intersection(allev)]
    lat, lon = P.lat.values, P.lon.values
    crowded = set()
    for rn, la, lo in zip(P.index, lat, lon):
        m = (np.abs(lat - la) < 0.012) & (np.abs(lon - lo) < 0.014)
        if (vc.km(la, lo, lat[m], lon[m]) <= 1.0).sum() > 1:
            crowded.add(rn)
    ep = ep[ep.start_utc.dt.year.between(2012, 2021)]
    rn_cty = dict(zip(ep.rn, ep.county))
    flare_rns = set(ep[ep.flare].rn) - crowded
    log = {"rns_with_flaring_episodes_2012_2021": int(ep[ep.flare].rn.nunique()),
           "left_out_neighbour_within_1km": int(len(set(ep[ep.flare].rn) & crowded)),
           "rns_used": len(flare_rns)}
    # detections
    det = []
    for f in sorted(FIRMS.glob("viirs-*_tx.csv.gz")):
        sat = f.name.split("_")[0]
        d = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time", "daynight"],
                        dtype={"acq_time": str})
        d = d[d.daynight.eq("N")]
        d["utc"] = pd.to_datetime(d.acq_date + " " + d.acq_time.str.zfill(4), format="%Y-%m-%d %H%M")
        d = d[d.utc.dt.year.between(2012, 2021)]
        d["sat"] = sat
        det.append(d)
    det = pd.concat(det)
    rows = []
    ll, lo_ = det.latitude.values, det.longitude.values
    for rn in flare_rns:
        la, lo = pts.at[rn, "lat"], pts.at[rn, "lon"]
        m = (np.abs(ll - la) < 0.012) & (np.abs(lo_ - lo) < 0.014)
        sub = det[m]
        sub = sub[vc.km(la, lo, sub.latitude.values, sub.longitude.values) <= 1.0]
        tz = "America/Denver" if rn_cty.get(rn) in vc.MOUNTAIN else "America/Chicago"
        nights = set(local_night(sub.utc, lo, tz)) if len(sub) else set()
        rows.append((rn, lo, nights, tz))
    # every reported event of any type at the RN, for the comparison-night exclusion (plan D7); an end that is
    # missing, before the start or more than 365 days after it is replaced by the start
    rep = pd.read_csv(vc.DER / "events_v2.csv.gz", usecols=["incident", "rn"])
    rep = rep[rep.rn.isin(flare_rns)]
    dt_ = pd.read_parquet(vc.DER / "details_table.parquet", columns=["incident", "county", "start_text", "end_text"])
    dt_["incident"] = dt_.incident.astype(int)
    rep = rep.merge(dt_, on="incident", how="left")
    cty = rep.county.fillna("").str.upper().str.strip()
    rs = vc.to_utc(pd.to_datetime(rep.start_text, format="%m/%d/%Y %I:%M %p", errors="coerce"), cty)
    re_ = vc.to_utc(pd.to_datetime(rep.end_text, format="%m/%d/%Y %I:%M %p", errors="coerce"), cty)
    ok = (re_ >= rs) & (re_ - rs <= pd.Timedelta(days=365))
    rep["s"], rep["e"] = rs, re_.where(ok, rs)
    rep = rep.dropna(subset=["s"])
    log["reports_any_type_at_used_rns"] = len(rep)
    # RN-night panel
    out_rows = []
    for rn, lo, nights, tz in rows:
        e = ep[ep.rn == rn]
        days = pd.date_range("2012-01-20", "2021-12-31", freq="D")  # Suomi NPP data start 2012-01-20
        s_loc = local_night(e.start_utc, lo, tz)
        e_loc = local_night(e.end_utc, lo, tz)
        # D6 item 6: an episode longer than 72 hours counts its first 72 hours only
        e72 = np.minimum(e.end_utc, e.start_utc + pd.Timedelta(hours=72))
        ev_night, near = set(), set()
        for fl, a, b, su, eu in zip(e.flare, s_loc, e_loc, e.start_utc, e72):
            if fl:
                ev_night.update(event_nights([su], [eu], lo, tz))
            near.update(pd.date_range(a - pd.Timedelta(days=2), max(a, b) + pd.Timedelta(days=2), freq="D"))
        r_ = rep[rep.rn == rn]
        for a, b in zip(local_night(r_.s, lo, tz), local_night(r_.e, lo, tz)):
            near.update(pd.date_range(a - pd.Timedelta(days=2), max(a, b) + pd.Timedelta(days=2), freq="D"))
        df = pd.DataFrame({"night": days})
        df["event"] = df.night.isin(ev_night)
        df["near"] = df.night.isin(near)
        df["det"] = df.night.isin(nights)
        df = df[df.event | ~df.near]
        df["rn"] = rn
        df["stratum"] = rn + "_" + df.night.dt.month.astype(str)
        df["year"] = df.night.dt.year
        out_rows.append(df)
    pan = pd.concat(out_rows)
    # comparison nights must be in other years than the stratum's event nights in that year? D6: "other years"
    ev_sy = pan.loc[pan.event, ["stratum", "year"]].drop_duplicates().assign(ev_year=True)
    pan = pan.merge(ev_sy, on=["stratum", "year"], how="left")
    pan = pan[pan.event | pan.ev_year.isna()]
    pan["a"] = pan.event & pan.det
    pan["b"] = pan.event & ~pan.det
    pan["c"] = ~pan.event & pan.det
    pan["d"] = ~pan.event & ~pan.det
    tab = pan.groupby("stratum")[["a", "b", "c", "d"]].sum()
    tab = tab[(tab.a + tab.b > 0) & (tab.c + tab.d > 0)]
    if (CLOCK, NIGHT) == ("solar", "noon"):
        tab.to_csv(vc.OUT / "v2_strata.csv")
    orr, lo95, hi95 = mh_or(tab)
    used = pan[pan.stratum.isin(tab.index)]
    # conditional logistic regression with one binary exposure: the exact conditional likelihood of each stratum is
    # the noncentral hypergeometric probability of a detections among n1 event nights given d detections in all
    inf = tab[((tab.a + tab.c) > 0) & ((tab.b + tab.d) > 0)].copy()
    inf["rn"] = inf.index.str.rsplit("_", n=1).str[0]
    beta, se = cl_fit(inf)
    rng = np.random.default_rng(11)
    rns = inf.rn.unique()
    groups = {r: g for r, g in inf.groupby("rn")}
    boots = []
    for _ in range(2000):
        pick = rng.choice(rns, size=len(rns), replace=True)
        boots.append(cl_fit(pd.concat([groups[r] for r in pick]), se=False)[0])
    clo, chi = np.percentile(boots, [2.5, 97.5])
    out = {"rule": "plan D6 item 8", "log": log,
           "event_nights": int(used.event.sum()), "comparison_nights": int((~used.event).sum()),
           "strata": len(tab), "informative_strata": len(inf), "rns_in_strata": int(used.rn.nunique()),
           "detection_rate_event_nights": round(float(used[used.event].det.mean()), 4),
           "detection_rate_comparison_nights": round(float(used[~used.event].det.mean()), 4),
           "conditional_logit_or": round(float(np.exp(beta)), 3),
           "conditional_logit_ci95_rn_bootstrap": [round(float(np.exp(clo)), 3), round(float(np.exp(chi)), 3)],
           "bootstrap_draws": len(boots),
           "model_se_ci95": [round(float(np.exp(beta - 1.96 * se)), 3), round(float(np.exp(beta + 1.96 * se)), 3)],
           "odds_ratio_mh_check": round(float(orr), 3), "mh_ci95": [round(float(lo95), 3), round(float(hi95), 3)]}
    tag = "" if (CLOCK, NIGHT) == ("solar", "noon") else f"_{CLOCK}_{NIGHT}"
    out["variant"] = {"clock": CLOCK, "night": NIGHT, "primary": tag == ""}
    (vc.OUT / f"v2_result{tag}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--clock", choices=["solar", "clock"], default="solar")
    ap.add_argument("--night", choices=["noon", "evening"], default="noon")
    a = ap.parse_args()
    CLOCK, NIGHT = a.clock, a.night
    main()
