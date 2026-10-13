"""H1 panel and model (analysis plan section 5.1). Shared by the power check and the real analysis.

Panel: one row per plant-day, for plants with at least one accident in the study
window, kept only in plant-years that contain an accident (other plant-years
carry no information under plant-by-year strata).

  y  accidents that day
  E  unplanned emission event occurrences in the window that ends gap+1 days
     before the day (default: days -97 to -8)
  x  log(1 + E)

  xs log(1 + S), S = events at every other plant statewide in the same window

No days are dropped after accidents in the primary analysis (post_excl = 0):
dropping them removes busy comparison days and, in simulation, biased the
estimate upward when a real effect exists (planted 1.3 came out 1.39). Options:
post_excl (R16) drops days 1..N after each accident; drop_chain_cases (R15)
drops only the case days of accidents within N days after an earlier one at the
same plant, so accident chains through restart upsets cannot drive the result. Primary model: Poisson with plant-by-year fixed effects
(equivalent to conditional Poisson stratified by plant-year), month-of-year
effects for seasons, and xs for statewide shocks; standard errors clustered by
plant. Effect: rate ratio per doubling of (1 + E) = 2**beta.
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DER = ROOT / "data" / "derived"

WINDOW, GAP, POST_EXCL = 90, 7, 0
STUDY_START, STUDY_END = pd.Timestamp("2003-06-01"), pd.Timestamp("2023-12-31")


STUDY_END_D2 = pd.Timestamp("2021-12-31")   # plan D2 item 1: primary window end


def load(version="v1"):
    """v1: the frozen registry-only tables (R20). v2: extended, hand-reviewed links (plan D2, D3) with the
    duplicate-accident merges applied (merged-away records dropped; R19 keeps them)."""
    suf = "_v2" if version == "v2" else ""
    plants = pd.read_csv(DER / f"plants{suf}.csv")
    ev = pd.read_csv(DER / f"events{suf}.csv.gz", parse_dates=["event_datetime", "report_date"])
    acc = pd.read_csv(DER / f"accidents{suf}.csv", parse_dates=["date"], keep_default_na=False,
                      dtype={"AccidentHistoryID": str, "EPAFacilityID": str, "merged_into": str})
    acc["plant_id"] = acc.plant_id.replace("", np.nan)
    if "merged_into" in acc:
        acc = acc[acc.merged_into == ""]
    risk = pd.read_csv(DER / f"plant_risk{suf}.csv", parse_dates=["risk_start", "risk_end"])
    return plants, ev, acc, risk


def daily_counts(ev, event_types=("EMISSIONS EVENT",), merge=True, by="event", exclude_incidents=()):
    """exclude_incidents: incident numbers not to count (primary: reports whose text says they are duplicates)."""
    e = ev[ev.event_type.isin(event_types) & ev.date_source.ne("none") & ev.plant_id.notna()
           & ~ev.incident.isin(set(exclude_incidents))]
    if merge:
        e = e[~e.is_duplicate]
    day = e.event_datetime.dt.normalize() if by == "event" else e.report_date
    return e.assign(day=day).dropna(subset=["day"]).groupby(["plant_id", "day"]).size()


def exposure_frame(plant_ids, counts, risk, window=WINDOW, gap=GAP, start=None, end=None):
    """Exposure for every at-risk day of each plant in the study window. No outcome involved.

    Also adds the statewide count over the same window at every other plant (S), which carries
    storms, freezes, reporting-rule changes and other shocks that hit all plants at once.
    """
    start = STUDY_START if start is None else start
    end = STUDY_END if end is None else end
    r = risk.set_index("plant_id")
    allday = counts.groupby(level="day").sum()
    span_all = pd.date_range(start - pd.Timedelta(days=window + gap + 1), end, freq="D")
    cs_all = allday.reindex(span_all, fill_value=0).cumsum()
    state = (cs_all.shift(gap + 1) - cs_all.shift(gap + window + 1)).loc[start:end]
    frames = []
    for p in plant_ids:
        if p not in r.index:
            continue
        lo, hi = max(start, r.at[p, "risk_start"]), min(end, r.at[p, "risk_end"])
        if lo > hi:
            continue
        span = pd.date_range(lo - pd.Timedelta(days=window + gap + 1), hi, freq="D")
        c = counts[p].reindex(span, fill_value=0) if p in counts.index.get_level_values(0) else \
            pd.Series(0, index=span)
        cs = c.cumsum()
        e = (cs.shift(gap + 1) - cs.shift(gap + window + 1)).loc[lo:hi]
        frames.append(pd.DataFrame({"plant_id": p, "day": e.index, "E": e.values.astype(int)}))
    out = pd.concat(frames, ignore_index=True)
    out["year"] = out.day.dt.year
    out["ym"] = out.day.dt.strftime("%Y-%m")
    out["moy"] = out.day.dt.month
    out["x"] = np.log1p(out.E)
    out["S"] = (out.day.map(state).astype(int) - out.E).clip(lower=0)
    out["xs"] = np.log1p(out.S)
    return out


def attach_outcome(expo, acc_days, post_excl=POST_EXCL, drop_chain_cases=None):
    """acc_days: DataFrame with plant_id and day (one row per accident). Returns the H1 panel."""
    y = acc_days.groupby(["plant_id", "day"]).size().rename("y")
    pan = expo.merge(y, left_on=["plant_id", "day"], right_index=True, how="left")
    pan["y"] = pan["y"].fillna(0).astype(int)
    drop = np.zeros(len(pan), dtype=bool)
    if drop_chain_cases:
        a = acc_days.sort_values(["plant_id", "day"]).drop_duplicates(["plant_id", "day"])
        gap = a.groupby("plant_id")["day"].diff().dt.days
        chain = a[gap.le(drop_chain_cases)]
        key = set(zip(chain.plant_id, chain.day))
        drop |= np.array([(p, d) in key for p, d in zip(pan.plant_id, pan.day)])
    # drop days 1..post_excl after any accident at the same plant
    for p, days in (acc_days.groupby("plant_id")["day"] if post_excl else []):
        idx = np.flatnonzero(pan.plant_id.values == p)
        if not len(idx):
            continue
        d = pan.day.values[idx]
        for a in days.values:
            after = (d > a) & (d <= a + np.timedelta64(post_excl, "D"))
            drop[idx[after]] = True
    pan = pan[~drop]
    # keep plant-years that contain at least one accident
    keep = pan.groupby(["plant_id", "year"])["y"].transform("sum") > 0
    pan = pan[keep].copy()
    pan["plant_year"] = pan.plant_id + "_" + pan.year.astype(str)
    return pan


PRIMARY = "y ~ x + xs | plant_year + moy"   # state-wide shocks via S, seasons via month of year
MONTHLY = "y ~ x | plant_year + ym"          # one effect per calendar month (R14)


def fit(pan, formula=PRIMARY, maxiter=100_000):
    import pyfixest as pf
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # separation_check drops groups whose effects run to minus infinity (no accidents in them)
        m = pf.fepois(formula, data=pan, vcov={"CRV1": "plant_id"}, separation_check=["fe"],
                      fixef_maxiter=maxiter, fixef_tol=1e-8, iwls_maxiter=100)
    b, se, p = float(m.coef()["x"]), float(m.se()["x"]), float(m.pvalue()["x"])
    return {"beta": b, "se": se, "p": p, "rr_doubling": 2 ** b,
            "ci_low": 2 ** (b - 1.959964 * se), "ci_high": 2 ** (b + 1.959964 * se),
            "n_days": int(getattr(m, "_N", len(pan))), "n_accidents": int(pan.y.sum()),
            "n_plants": int(pan.plant_id.nunique()), "n_strata": int(pan.plant_year.nunique())}
