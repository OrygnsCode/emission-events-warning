"""Phase 5 engine: the H1 model with every pre-registered variation (plan sections 5.2, 6.2, 6.3, D2, D4, D6, D7).

One function, h1_run(spec), builds the panel and fits the model. With the default spec it reproduces the Phase 4
primary result exactly (checked by test_anchor()). Every option below maps to an item of the plan:

  outcome        "O1" (primary) / "O2" / "O3" / "O4"                       5.2
  window, gap    days in the window and the gap (90, 7)                   5.2, R1, R2
  event_types    which TCEQ event types count (unplanned only)            R3
  by             "event" (start date) or "report" (report date)           5.2 real-time, R4
  merge          same-start merge of reports (True)                       R13
  exclude        name of the exclusion set in h1_exclusion_sets.json      R17, R17 extended, R30
  links          "v2" (extended, hand-reviewed) or "v1" (registry only)   R20
  plants_subset  "one_to_one" keeps one-to-one linked plants only         R7
  accident_merge True applies the duplicate merges, False keeps all       R19
  end            last day of the study window                             D2 item 1, R8
  exposures      dict name -> per (plant, day) series; default the event count. Each becomes log(1 + windowed sum)
                 in the model, with its own window and gap unless a (window, gap) pair is given per exposure
  statewide      "state" (all other sites in Texas), "region" (TCEQ region, R6) or None
  extra_cols     callable(panel) -> panel with added covariate columns, named in extra_terms
  drop_days      callable(panel) -> boolean mask of plant-days to drop (R5, R22 to R24, R28)
  formula_fe     fixed effects (primary "plant_year + moy"; R12 "plant_id + year + moy"; R14 "plant_year + ym")
  family         "poisson" (primary), "logit" (R11 conditional logistic on any accident), "negbin" (R11)
  post_excl, drop_chain_cases  R16, R15

Nothing here reads outcomes except through the accident table, and every count of what was left out is returned.
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h1  # noqa: E402

DER = h1.DER
_CACHE = {}


def tables(links="v2"):
    if links not in _CACHE:
        plants, ev, acc, risk = h1.load(links)
        acc_all = pd.read_csv(DER / ("accidents_v2.csv" if links == "v2" else "accidents.csv"), parse_dates=["date"],
                              keep_default_na=False, dtype={"AccidentHistoryID": str, "EPAFacilityID": str,
                                                            "merged_into": str})
        _CACHE[links] = (plants, ev, acc, acc_all, risk)
    return _CACHE[links]


def exclusion(name):
    sets = json.loads((DER / "h1_exclusion_sets.json").read_text())
    if name in (None, "none"):
        return set()
    if name == "r30":
        return set(sets["primary"]) | set(sets["r30_absorbed"])
    return set(sets[name])


def event_counts(ev, event_types=("EMISSIONS EVENT",), merge=True, by="event", exclude="primary", weight=None):
    """Per (plant, day) count of occurrences, or the sum of a per-incident weight over the occurrences' reports.
    weight: Series indexed by incident (summed over all reports of the occurrence, not only the kept one)."""
    excl = exclusion(exclude)
    e = ev[ev.event_type.isin(event_types) & ev.date_source.ne("none") & ev.plant_id.notna() & ~ev.incident.isin(excl)]
    day_col = e.event_datetime.dt.normalize() if by == "event" else e.report_date
    e = e.assign(day=day_col).dropna(subset=["day"])
    if weight is None:
        if merge:
            e = e[~e.is_duplicate]
        return e.groupby(["plant_id", "day"]).size()
    # weights: an occurrence carries the weight of all its reports (kept report and its same-start duplicates)
    e = e.assign(occ=np.where(e.is_duplicate, e.dup_of, e.incident).astype(int)) if merge else e.assign(occ=e.incident)
    w = weight.reindex(e.incident).fillna(0).values
    e = e.assign(w=w)
    if merge:
        # the occurrence is dated and placed by its kept report
        kept = e[~e.is_duplicate].set_index("incident")[["plant_id", "day"]]
        tot = e.groupby("occ").w.sum()
        k = kept.join(tot.rename("w"), how="inner")
        return k.groupby(["plant_id", "day"]).w.sum()
    return e.groupby(["plant_id", "day"]).w.sum()


def windowed(counts, plant_days, window, gap, start_pad):
    """Sum of counts over days -(window+gap) .. -(gap+1) for each (plant_id, day) row of plant_days."""
    out = np.zeros(len(plant_days))
    for p, idx in plant_days.groupby("plant_id").indices.items():
        days = plant_days.day.values[idx]
        lo, hi = days.min(), days.max()
        span = pd.date_range(pd.Timestamp(lo) - pd.Timedelta(days=start_pad), pd.Timestamp(hi), freq="D")
        c = counts[p].reindex(span, fill_value=0) if p in counts.index.get_level_values(0) else pd.Series(0.0, index=span)
        cs = c.cumsum()
        e = (cs.shift(gap + 1) - cs.shift(gap + window + 1)).reindex(pd.DatetimeIndex(days))
        out[idx] = e.fillna(0).values
    return out


def statewide(counts, days, window, gap, groups=None):
    """Windowed statewide total for each day, or (groups: Series plant_id -> region) a dict region -> windowed total."""
    span = pd.date_range(days.min() - pd.Timedelta(days=window + gap + 1), days.max(), freq="D")

    def win(daily):
        cs = daily.reindex(span, fill_value=0).cumsum()
        return cs.shift(gap + 1) - cs.shift(gap + window + 1)

    if groups is None:
        return win(counts.groupby(level="day").sum())
    reg = counts.rename("c").reset_index()
    reg["g"] = reg.plant_id.map(groups)
    return {g: win(sub.groupby("day").c.sum()) for g, sub in reg.dropna(subset=["g"]).groupby("g")}


def base_days(plant_ids, risk, start, end):
    r = risk.set_index("plant_id")
    frames = []
    for p in plant_ids:
        if p not in r.index:
            continue
        lo, hi = max(start, r.at[p, "risk_start"]), min(end, r.at[p, "risk_end"])
        if lo > hi:
            continue
        frames.append(pd.DataFrame({"plant_id": p, "day": pd.date_range(lo, hi, freq="D")}))
    d = pd.concat(frames, ignore_index=True)
    d["year"] = d.day.dt.year
    d["moy"] = d.day.dt.month
    d["ym"] = d.day.dt.strftime("%Y-%m")
    return d


DATA_START = pd.Timestamp("2003-02-01")   # first day of the TCEQ event data (build_tables.TCEQ_START)

DEFAULT = dict(outcome="O1", window=90, gap=7, event_types=("EMISSIONS EVENT",), by="event", merge=True,
               exclude="primary", links="v2", plants_subset=None, accident_merge=True, end="2021-12-31",
               exposures=None, statewide="state", region_of=None, extra_cols=None, extra_terms=(),
               drop_days=None, formula_fe="plant_year + moy", family="poisson", post_excl=0, drop_chain_cases=None,
               accidents=None, keep_panel=False, terms=None, statewide_counts=None, statewide_each=False, full_window_only=True)


def h1_run(**kw):
    s = dict(DEFAULT, **kw)
    plants, ev, acc, acc_all, risk = tables(s["links"])
    end = pd.Timestamp(s["end"])
    linked = set(plants.loc[plants.linked, "plant_id"])
    if s["plants_subset"] == "one_to_one":
        linked = set(plants.loc[plants.linked & plants.one_to_one, "plant_id"])
    a = s["accidents"] if s["accidents"] is not None else (acc if s["accident_merge"] else acc_all)
    if s["outcome"] != "O1":
        a = a[a[s["outcome"]].astype(str).eq("True")]
    a = a[a.plant_id.isin(linked) & a.date.between(h1.STUDY_START, end)]
    acc_days = pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values})
    log = {"accidents_in_window": len(acc_days)}
    plant_ids = sorted(acc_days.plant_id.unique())
    pan = base_days(plant_ids, risk, h1.STUDY_START, end)
    at_risk = set(zip(pan.plant_id, pan.day))
    inside = np.array([(p, pd.Timestamp(d)) in at_risk for p, d in zip(acc_days.plant_id, acc_days.day)])
    log["accidents_not_at_risk"] = int((~inside).sum())
    acc_days = acc_days[inside]
    # exposures
    if s["exposures"] is None:
        cnt = event_counts(ev, s["event_types"], s["merge"], s["by"], s["exclude"])
        exps = {"x": (cnt, s["window"], s["gap"])}
    else:
        exps = {k: (v if isinstance(v, tuple) else (v, s["window"], s["gap"])) for k, v in s["exposures"].items()}
    pad = max(w + g + 1 for _, w, g in exps.values())
    if s["full_window_only"]:
        # D9: only days whose whole window lies inside the event data (no-op for the 90-day primary window)
        first_ok = DATA_START + pd.Timedelta(days=pad - 1)
        log["days_before_full_window"] = int((pan.day < first_ok).sum())
        pan = pan[pan.day >= first_ok].reset_index(drop=True)
    for name, (cnt, w, g) in exps.items():
        own = windowed(cnt, pan[["plant_id", "day"]], w, g, pad)
        pan["E_" + name] = own
        pan[name] = np.log1p(own)
    # statewide control: for the first exposure (the event count, as in the primary model), or one per exposure
    first, (cnt0, w0, g0) = next(iter(exps.items()))
    if s.get("statewide_counts") is not None:
        cnt0 = s["statewide_counts"]
    if s["statewide"] == "state" and s["statewide_each"]:
        for name, (cnt, w, g) in exps.items():
            st = statewide(cnt, pan.day, w, g)
            pan["xs_" + name] = np.log1p((pan.day.map(st).values - pan["E_" + name].values).clip(min=0))
    elif s["statewide"] == "state" and s.get("statewide_counts") is not None:
        st = statewide(cnt0, pan.day, w0, g0)
        own = windowed(cnt0, pan[["plant_id", "day"]], w0, g0, pad)
        pan["S"] = (pan.day.map(st).values - own).clip(min=0)
        pan["xs"] = np.log1p(pan.S)
    elif s["statewide"] == "state":
        st = statewide(cnt0, pan.day, w0, g0)
        pan["S"] = (pan.day.map(st).values - pan["E_" + first].values).clip(min=0)
        pan["xs"] = np.log1p(pan.S)
    elif s["statewide"] == "region":
        reg = statewide(cnt0, pan.day, w0, g0, groups=s["region_of"])
        own_reg = pan.plant_id.map(s["region_of"])
        tot = np.array([reg[g].get(d, 0) if g in reg else 0 for g, d in zip(own_reg, pan.day)], dtype=float)
        pan["S"] = (tot - pan["E_" + first].values).clip(min=0)
        pan["xs"] = np.log1p(pan.S)
    if s["extra_cols"] is not None:
        pan = s["extra_cols"](pan)
    if "plant_year" in s["formula_fe"]:
        pan = h1.attach_outcome(pan, acc_days, post_excl=s["post_excl"], drop_chain_cases=s["drop_chain_cases"])
    else:
        # strata by plant (R12): keep every at-risk year of plants with an accident; same day drops as attach_outcome
        pan = all_years_outcome(pan, acc_days, s["post_excl"], s["drop_chain_cases"])
    if s["drop_days"] is not None:
        m = s["drop_days"](pan)
        log["days_dropped_by_rule"] = int(m.sum())
        log["accidents_on_dropped_days"] = int(pan.y[m].sum())
        pan = pan[~m]
        unit = "plant_year" if "plant_year" in s["formula_fe"] else "plant_id"
        keep = pan.groupby(unit)["y"].transform("sum") > 0
        pan = pan[keep].copy()
    if s["terms"] is not None:
        terms = list(s["terms"])
    elif s["statewide_each"]:
        terms = list(exps) + ["xs_" + n for n in exps] + list(s["extra_terms"])
    else:
        terms = list(exps) + (["xs"] if s["statewide"] else []) + list(s["extra_terms"])
    res = fit(pan, terms, s["formula_fe"], s["family"])
    res["log"] = log
    if s["keep_panel"]:
        res["panel"] = pan
    return res


def all_years_outcome(expo, acc_days, post_excl=0, drop_chain_cases=None):
    """attach_outcome without the plant-year restriction: every at-risk day of plants with an accident in the panel."""
    y = acc_days.groupby(["plant_id", "day"]).size().rename("y")
    pan = expo.merge(y, left_on=["plant_id", "day"], right_index=True, how="left")
    pan["y"] = pan["y"].fillna(0).astype(int)
    drop = np.zeros(len(pan), dtype=bool)
    if drop_chain_cases:
        a = acc_days.sort_values(["plant_id", "day"]).drop_duplicates(["plant_id", "day"])
        gap = a.groupby("plant_id")["day"].diff().dt.days
        chain = set(zip(a[gap.le(drop_chain_cases)].plant_id, a[gap.le(drop_chain_cases)].day))
        drop |= np.array([(p, d) in chain for p, d in zip(pan.plant_id, pan.day)])
    if post_excl:
        for p, days in acc_days.groupby("plant_id")["day"]:
            idx = np.flatnonzero(pan.plant_id.values == p)
            d = pan.day.values[idx]
            for a_ in days.values:
                drop[idx[(d > a_) & (d <= a_ + np.timedelta64(post_excl, "D"))]] = True
    pan = pan[~drop]
    pan = pan[pan.groupby("plant_id")["y"].transform("sum") > 0].copy()
    pan["plant_year"] = pan.plant_id + "_" + pan.year.astype(str)
    return pan


def fit(pan, terms, fe, family):
    import pyfixest as pf
    out = {"n_days": len(pan), "n_accidents": int(pan.y.sum()), "n_plants": int(pan.plant_id.nunique()),
           "n_strata": int(pan.plant_year.nunique())}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if family == "poisson":
            try:
                m = pf.fepois(f"y ~ {' + '.join(terms)} | {fe}", data=pan, vcov={"CRV1": "plant_id"},
                              separation_check=["fe"], fixef_maxiter=100_000, fixef_tol=1e-8, iwls_maxiter=100)
                coef, se, p = m.coef(), m.se(), m.pvalue()
                out["vcov"] = pd.DataFrame(m._vcov, index=coef.index, columns=coef.index)
                out["fitted_by"] = "pyfixest"
            except ValueError:
                if fe != "plant_year + moy":
                    raise
                coef, se, p, V = cond_poisson(pan, terms)
                out["vcov"] = V
                out["fitted_by"] = "exact conditional likelihood (pyfixest demeaning did not converge)"
        elif family == "logit":
            coef, se, p, V = clogit(pan.assign(y=(pan.y > 0).astype(int)), terms, fe)
            out["vcov"] = V
        elif family == "negbin":
            coef, se, p, V = negbin(pan, terms, fe)
            out["vcov"] = V
    out["terms"] = {t: {"beta": float(coef[t]), "se": float(se[t]), "p": float(p[t]), "rr_doubling": float(2 ** coef[t]),
                        "ci": [float(2 ** (coef[t] - 1.959964 * se[t])), float(2 ** (coef[t] + 1.959964 * se[t]))]}
                    for t in terms if t in coef.index}
    return out


def cond_poisson(pan, terms, tol=1e-10, max_iter=200):
    """Conditional Poisson (multinomial within plant_year) with month-of-year dummies, any number of terms, Newton's
    method, plant-clustered sandwich with G/(G-1); the h1_numpy method generalized. Returns coef, se, p, vcov."""
    from scipy.stats import norm
    pan = pan.reset_index(drop=True)
    month = np.column_stack([(pan.moy.values == m).astype(float) for m in range(2, 13)])
    Z = np.column_stack([pan[t].to_numpy(dtype=float) for t in terms] + [month])
    names = list(terms) + [f"m{m}" for m in range(2, 13)]
    y = pan.y.to_numpy(dtype=float)
    _, g = np.unique(pan.plant_year.to_numpy(), return_inverse=True)
    n_g = np.bincount(g, weights=y)
    keep = n_g[g] > 0
    Z, y, g, plants = Z[keep], y[keep], g[keep], pan.plant_id.to_numpy()[keep]
    _, g = np.unique(g, return_inverse=True)
    n_g = np.bincount(g, weights=y)
    usable = Z.std(axis=0) > 0
    Z = Z[:, usable]
    names = [n for n, u in zip(names, usable) if u]
    k = Z.shape[1]
    th = np.zeros(k)

    def pieces(th):
        eta = Z @ th
        eta = eta - np.bincount(g, weights=eta)[g] / np.bincount(g)[g]
        w = np.exp(eta)
        pr = w / np.bincount(g, weights=w)[g]
        return pr, n_g[g] * pr

    def hess(pr, mu):
        zbar = np.vstack([np.bincount(g, weights=pr * Z[:, j]) for j in range(k)]).T
        return -(Z.T @ (Z * mu[:, None])) + (zbar.T * n_g) @ zbar

    def loglik(th):
        eta = Z @ th
        eta = eta - np.bincount(g, weights=eta)[g] / np.bincount(g)[g]
        m = pd.Series(eta).groupby(g).transform("max").to_numpy()
        lse = np.log(np.bincount(g, weights=np.exp(eta - m))) + np.bincount(g, weights=m) / np.bincount(g)
        # within a stratum m is constant, so the mean of m over the stratum equals m
        return float((y * eta).sum() - (n_g * lse).sum())

    ll = loglik(th)
    converged = False
    for _ in range(max_iter):
        pr, mu = pieces(th)
        step = np.linalg.lstsq(hess(pr, mu), Z.T @ (y - mu), rcond=None)[0]
        t = 1.0
        while t > 1e-8:
            new = th - t * step
            ln = loglik(new)
            if np.isfinite(ln) and ln >= ll - 1e-12:
                break
            t /= 2
        th, ll = new, ln
        if np.max(np.abs(t * step)) < tol:
            converged = True
            break
    if not converged:
        raise RuntimeError("conditional Poisson did not converge")
    pr, mu = pieces(th)
    H = hess(pr, mu)
    _, c = np.unique(plants, return_inverse=True)
    G = c.max() + 1
    sc = Z * (y - mu)[:, None]
    S = np.vstack([np.bincount(c, weights=sc[:, j], minlength=G) for j in range(k)]).T
    Hi = np.linalg.inv(H)
    V = Hi @ (S.T @ S) @ Hi * G / (G - 1)
    coef = pd.Series(th, index=names)
    se = pd.Series(np.sqrt(np.diag(V)), index=names)
    return coef, se, pd.Series(2 * norm.sf(np.abs(coef / se)), index=names), pd.DataFrame(V, index=names, columns=names)


def clogit(pan, terms, fe):
    """Conditional logistic regression on any accident that day, stratified by plant_year, month-of-year dummies;
    plant-clustered sandwich errors. Fitted with statsmodels ConditionalLogit."""
    from statsmodels.discrete.conditional_models import ConditionalLogit
    pan = pan[pan.groupby("plant_year").y.transform("sum") > 0]
    X = pan[terms].copy()
    if "moy" in fe:
        X = pd.concat([X, pd.get_dummies(pan.moy, prefix="m", drop_first=True, dtype=float)], axis=1)
    X = X.loc[:, X.std() > 0]
    m = ConditionalLogit(pan.y.values, X.values, groups=pan.plant_year.values).fit(disp=0)
    # cluster by plant: sandwich from per-observation scores summed by plant
    b = m.params
    V = cluster_sandwich_clogit(pan, X.values, b)
    se = np.sqrt(np.diag(V))
    from scipy.stats import norm
    names = list(X.columns)
    coef = pd.Series(b, index=names)
    sei = pd.Series(se, index=names)
    return coef, sei, pd.Series(2 * norm.sf(np.abs(coef / sei)), index=names), pd.DataFrame(V, index=names, columns=names)


def cluster_sandwich_clogit(pan, X, b):
    """Plant-clustered covariance for the conditional logit: strata scores summed by plant (strata nest in plants)."""
    eta = X @ b
    g = pd.factorize(pan.plant_year.values)[0]
    y = pan.y.values.astype(float)
    # for one event per stratum the likelihood is softmax; with several events use the same first-order score
    # (exact for the Breslow-style approximation used only for the variance)
    w = np.exp(eta - pd.Series(eta).groupby(g).transform("max").values)
    sw = np.bincount(g, weights=w)
    p = w / sw[g]
    ny = np.bincount(g, weights=y)
    score = X * (y - ny[g] * p)[:, None]
    zbar = np.vstack([np.bincount(g, weights=p * X[:, j]) for j in range(X.shape[1])]).T
    H = -(X.T @ (X * (ny[g] * p)[:, None])) + (zbar.T * ny) @ zbar
    c = pd.factorize(pan.plant_id.values)[0]
    G = c.max() + 1
    S = np.vstack([np.bincount(c, weights=score[:, j], minlength=G) for j in range(X.shape[1])]).T
    Hi = np.linalg.inv(H)
    return Hi @ (S.T @ S) @ Hi * G / (G - 1)


def negbin(pan, terms, fe):
    """Negative binomial (NB2) with plant_year and month-of-year dummies, plant-clustered errors (statsmodels).
    Strata without accidents carry no information and are dropped, as in the Poisson fit."""
    import statsmodels.api as sm
    pan = pan[pan.groupby("plant_year").y.transform("sum") > 0].reset_index(drop=True)
    X = pd.concat([pan[terms], pd.get_dummies(pan.moy, prefix="m", drop_first=True, dtype=float),
                   pd.get_dummies(pan.plant_year, prefix="py", dtype=float)], axis=1)
    m = sm.NegativeBinomial(pan.y.values, X.values).fit(disp=0, maxiter=500, method="bfgs",
                                                        cov_type="cluster",
                                                        cov_kwds={"groups": pd.factorize(pan.plant_id)[0]})
    names = list(X.columns) + ["alpha"]
    coef = pd.Series(m.params, index=names)
    se = pd.Series(m.bse, index=names)
    p = pd.Series(m.pvalues, index=names)
    V = pd.DataFrame(m.cov_params(), index=names, columns=names)
    return coef[terms], se[terms], p[terms], V.loc[terms, terms]


def test_anchor():
    """The default spec must reproduce the Phase 4 primary result."""
    r = h1_run()
    ref = json.loads((h1.ROOT / "data/manifests/h1_primary_result.json").read_text())["primary_end_2021"]["pyfixest"]
    b = r["terms"]["x"]["beta"]
    print("anchor beta", b, "Phase 4", ref["beta"], "diff", abs(b - ref["beta"]), "| n_days", r["n_days"], ref["n_days"],
          "| accidents", r["n_accidents"], ref["n_accidents"])
    assert abs(b - ref["beta"]) < 1e-9 and r["n_days"] == ref["n_days"] and r["n_accidents"] == ref["n_accidents"]
    return r


if __name__ == "__main__":
    test_anchor()
