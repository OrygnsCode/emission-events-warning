"""Phase 5, part D: H2 and H2b (between plants), H3 (forward test) and the usefulness numbers (plan 5.3, 5.4, D4 item 5).

Cohort: every linked plant (extended links), years 2004 to 2021 (primary window end, D2 item 1; 2004 so that the
prior year exists), plant-years with at least one at-risk day. Rules not spelled out in the plan (D9):
- exposure time: log(days at risk / days in the year) is an offset (a plant registered mid-year is at risk for part
  of the year);
- RMP covariates for a plant-year come, for each of the plant's facilities, from its latest filing received by
  the end of that year, or its earliest filing if none yet (D2 note: most recent non-missing value); staff is the
  sum of FTE (0 read as missing, D6 item 3; a version keeping 0 is reported beside), the largest regulated chemical
  quantity is the largest process-chemical quantity, processes is the count of processes; plant-years still missing
  a covariate are dropped and counted;
- emissions: EPA National Emissions Inventory (EIS program in EPA's combined emissions report): pounds of carbon
  monoxide, nitrogen oxides, sulfur dioxide, volatile organic compounds and primary PM10, summed over the plant's
  EPA registry IDs, from the NEI year nearest the plant-year (2008, 2011, 2014, 2017, 2020; ties to the earlier),
  as log(1 + tons); plants with no NEI record get 0 and an indicator;
- inspections (ICIS-Air full and partial compliance evaluations, by end date), violations (ICIS-Air violation history
  records, by the earliest violation determination date) and enforcement (ICIS-Air formal actions, by settlement date), counted in the prior
  calendar year over the plant's air program IDs, each as log(1 + count); both state and EPA records (ICIS-Air is
  the federal system).
H2: Poisson of accidents in the year on log(1 + unplanned event occurrences in the prior year), the covariates,
    sector and year effects; plant-clustered errors. H2b adds inspections, violations and enforcement.
H3: plant-quarters; the H2b covariates without year effects (a model fit on past years cannot carry year effects
    forward) and events in the prior four quarters; fit on 2004 to 2015, tested unchanged on 2016 to 2021 (and
    2016 to 2023 beside). Baseline: size, sector, prior accidents, inspections and violations. Measures on the test
    years: ROC and precision-recall areas (any accident in the quarter), share of accident quarters among the top
    10% of predicted plant-quarters, calibration slope (Poisson of the outcome on log predicted rate); 95%
    intervals from 1,000 bootstrap resamples of plants.
Usefulness (D4 item 5): flags of at least 1, 3 and 10 unplanned event occurrences in the 90 days before a quarter,
    and the top 10% of the H3 full model; per 1,000 plant-quarters, accidents in that quarter among flagged and
    unflagged plant-quarters, sensitivity and false alarms per true alarm; absolute accident rate per 1,000
    plant-years.
Output: data/manifests/phase5_h2h3.json
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

ROOT = P.h1.ROOT
DER = P.DER
SL = ROOT / "data" / "slices"
OUT = ROOT / "data" / "manifests" / "phase5_h2h3.json"
R = dict(dtype=str, keep_default_na=False)
NEI_POLL = ["Carbon monoxide", "Nitrogen oxides", "Sulfur dioxide", "Volatile organic compounds",
            "Primary PM10 (filterables and condensibles)"]


def registry_ids(pm, linked):
    frs = pd.read_csv(SL / "frs_program_tx_relevant.csv.gz", usecols=["PGM_SYS_ACRNM", "PGM_SYS_ID", "REGISTRY_ID"], **R)
    m = pm[pm.plant_id.isin(linked)]
    a = frs[(frs.PGM_SYS_ACRNM == "RMP") & frs.PGM_SYS_ID.isin(m[m.id_type == "RMP"].id)]
    b = frs[(frs.PGM_SYS_ACRNM == "TX-TCEQ ACR") & frs.PGM_SYS_ID.isin(m[m.id_type == "RN"].id)]
    id2p = dict(zip(m.id, m.plant_id))
    reg = pd.concat([a.assign(plant_id=a.PGM_SYS_ID.map(id2p)), b.assign(plant_id=b.PGM_SYS_ID.map(id2p))])
    return reg[["plant_id", "REGISTRY_ID"]].drop_duplicates()


def rmp_covariates(pm, linked, years):
    f = pd.read_csv(SL / "rmp_raw/tblS1Facilities.csv.gz", usecols=["FacilityID", "EPAFacilityID", "FTE", "ReceiptDate"], **R)
    pr = pd.read_csv(SL / "rmp_raw/tblS1Processes.csv.gz", usecols=["ProcessID", "FacilityID"], **R)
    pc = pd.read_csv(SL / "rmp_raw/tblS1ProcessChemicals.csv.gz", usecols=["ProcessID", "Quantity"], **R)
    pc["q"] = pd.to_numeric(pc.Quantity, errors="coerce")
    nproc = pr.groupby("FacilityID").size()
    maxq = pc.merge(pr, on="ProcessID").groupby("FacilityID").q.max()
    f["fte"] = pd.to_numeric(f.FTE, errors="coerce")
    f["nproc"] = f.FacilityID.map(nproc).fillna(0)
    f["maxq"] = f.FacilityID.map(maxq)
    f["rec"] = pd.to_datetime(f.ReceiptDate.str[:10], errors="coerce")
    rmp_plant = dict(zip(pm[pm.id_type == "RMP"].id, pm[pm.id_type == "RMP"].plant_id))
    f["plant_id"] = f.EPAFacilityID.map(rmp_plant)
    f = f[f.plant_id.isin(linked)].sort_values("rec")
    rows = []
    for y in years:
        cut = pd.Timestamp(f"{y}-12-31")
        latest = f[f.rec <= cut].groupby("EPAFacilityID").tail(1)
        earliest = f.groupby("EPAFacilityID").head(1)
        use = pd.concat([latest, earliest[~earliest.EPAFacilityID.isin(latest.EPAFacilityID)]])
        g = use.groupby("plant_id").agg(fte_raw=("fte", lambda s: s.sum(min_count=1)),
                                       fte_any_zero=("fte", lambda s: bool((s == 0).any())),
                                       nproc=("nproc", "sum"), maxq=("maxq", "max"))
        g["year"] = y
        rows.append(g.reset_index())
    d = pd.concat(rows)
    d["fte_zero_missing"] = d.fte_raw.where(~d.fte_any_zero, np.nan)
    return d


def nei_emissions(reg, years):
    e = pd.read_csv(SL / "poll_rpt_combined_emissions_tx.csv.gz", **R)
    e = e[(e.PGM_SYS_ACRNM == "EIS") & e.POLLUTANT_NAME.isin(NEI_POLL) & e.UNIT_OF_MEASURE.eq("Pounds")]
    e["lb"] = pd.to_numeric(e.ANNUAL_EMISSION, errors="coerce")
    e = e.merge(reg, on="REGISTRY_ID")
    t = e.groupby(["plant_id", "REPORTING_YEAR"]).lb.sum().div(2000).rename("tons").reset_index()
    t["REPORTING_YEAR"] = t.REPORTING_YEAR.astype(int)
    nei_years = np.array(sorted(t.REPORTING_YEAR.unique()))
    out = []
    for y in years:
        ny = nei_years[np.argmin(np.abs(nei_years - y) + (nei_years > y) * 1e-6)]
        out.append(t[t.REPORTING_YEAR == ny].assign(year=y)[["plant_id", "year", "tons"]])
    return pd.concat(out)


def icis_counts(reg):
    fac = pd.read_csv(SL / "icis_air_facilities_tx.csv.gz", usecols=["PGM_SYS_ID", "REGISTRY_ID"], **R)
    air = fac.merge(reg, on="REGISTRY_ID")[["PGM_SYS_ID", "plant_id"]].drop_duplicates()
    ins = pd.read_csv(SL / "icis_air_fces_pces_tx.csv.gz", usecols=["PGM_SYS_ID", "ACTIVITY_ID", "ACTUAL_END_DATE"], **R)
    ins["d"] = pd.to_datetime(ins.ACTUAL_END_DATE, format="%m-%d-%Y", errors="coerce")
    vio = pd.read_csv(SL / "icis_air_violation_history_tx.csv.gz",
                      usecols=["PGM_SYS_ID", "ACTIVITY_ID", "EARLIEST_FRV_DETERM_DATE"], **R)
    vio["d"] = pd.to_datetime(vio.EARLIEST_FRV_DETERM_DATE, format="%m-%d-%Y", errors="coerce")
    enf = pd.read_csv(SL / "icis_air_formal_actions_tx.csv.gz", usecols=["PGM_SYS_ID", "ACTIVITY_ID", "SETTLEMENT_ENTERED_DATE"], **R)
    enf["d"] = pd.to_datetime(enf.SETTLEMENT_ENTERED_DATE, format="%m/%d/%Y", errors="coerce")
    res, log = {}, {}
    for name, d in (("inspections", ins), ("violations", vio), ("enforcement", enf)):
        d = d.drop_duplicates(["PGM_SYS_ID", "ACTIVITY_ID"]).merge(air, on="PGM_SYS_ID")
        log[name] = {"records_linked": len(d), "missing_date_share": round(float(d.d.isna().mean()), 4)}
        res[name] = d.dropna(subset=["d"])[["plant_id", "d"]]
    return res, log


def build(years, quarters=False):
    plants, ev, acc, acc_all, risk = P.tables("v2")
    pm = pd.read_csv(DER / "plant_members_v2.csv", **R)
    linked = set(plants.loc[plants.linked, "plant_id"])
    attrs = pd.read_csv(DER / "plant_attributes.csv").set_index("plant_id")
    reg = registry_ids(pm, linked)
    # at-risk days per plant and period
    days = P.base_days(sorted(linked), risk, pd.Timestamp(f"{min(years) - 1}-01-01"), pd.Timestamp(f"{max(years)}-12-31"))
    days["q"] = days.day.dt.to_period("Q")
    unit = "q" if quarters else "year"
    panel = days.groupby(["plant_id", unit]).size().rename("days_at_risk").reset_index()
    panel["year"] = panel[unit].dt.year if quarters else panel[unit]
    panel = panel[panel.year.isin(years)]
    period_len = (panel[unit].map(lambda q: (q.end_time.normalize() - q.start_time).days + 1) if quarters
                  else panel.year.map(lambda y: pd.Timestamp(f"{y}-12-31").dayofyear))
    panel["offset"] = np.log(panel.days_at_risk / period_len)
    # outcome
    a = acc[acc.plant_id.isin(linked)]
    a = a.assign(key=a.date.dt.to_period("Q") if quarters else a.date.dt.year)
    y = a.groupby(["plant_id", "key"]).size()
    panel["y"] = [y.get((p, k), 0) for p, k in zip(panel.plant_id, panel[unit])]
    # events in the prior year (or prior four quarters) and in the prior 90 days (flags)
    cnt = P.event_counts(ev)
    c = cnt.reset_index().rename(columns={0: "n"})
    c.columns = ["plant_id", "day", "n"]
    by = {p: g for p, g in c.groupby("plant_id")}
    prior, prior90 = [], []
    for p, k in zip(panel.plant_id, panel[unit]):
        g = by.get(p)
        start = (k.start_time if quarters else pd.Timestamp(f"{k}-01-01"))
        lo = start - (pd.DateOffset(years=1))
        if g is None:
            prior.append(0)
            prior90.append(0)
            continue
        prior.append(int(g.n[(g.day >= lo) & (g.day < start)].sum()))
        prior90.append(int(g.n[(g.day >= start - pd.Timedelta(days=90)) & (g.day < start)].sum()))
    panel["events_prior"] = prior
    panel["events_prior90"] = prior90
    panel["x"] = np.log1p(panel.events_prior)
    # prior accidents in the five years before the period
    acc_by = {p: g.date.values for p, g in acc[acc.plant_id.isin(linked)].groupby("plant_id")}
    pa = []
    for p, k in zip(panel.plant_id, panel[unit]):
        start = (k.start_time if quarters else pd.Timestamp(f"{k}-01-01"))
        d = acc_by.get(p, np.array([], dtype="datetime64[ns]"))
        pa.append(int(((d >= np.datetime64(start - pd.DateOffset(years=5))) & (d < np.datetime64(start))).sum()))
    panel["prior_acc5"] = np.log1p(pa)
    # covariates by year
    cov = rmp_covariates(pm, linked, sorted(set(panel.year)))
    panel = panel.merge(cov, on=["plant_id", "year"], how="left")
    nei = nei_emissions(reg, sorted(set(panel.year)))
    panel = panel.merge(nei, on=["plant_id", "year"], how="left")
    panel["no_nei"] = panel.tons.isna().astype(float)
    panel["log_emis"] = np.log1p(panel.tons.fillna(0))
    icis, ilog = icis_counts(reg)
    for name, d in icis.items():
        byp = {p: g.d.values for p, g in d.groupby("plant_id")}
        v = []
        for p, k in zip(panel.plant_id, panel[unit]):
            start = (k.start_time if quarters else pd.Timestamp(f"{k}-01-01"))
            dd = byp.get(p, np.array([], dtype="datetime64[ns]"))
            v.append(int(((dd >= np.datetime64(start - pd.DateOffset(years=1))) & (dd < np.datetime64(start))).sum()))
        panel[name] = np.log1p(v)
    panel["sector"] = panel.plant_id.map(attrs.sector)
    return panel, ilog


def poisson(panel, terms, year_fe=True):
    import statsmodels.api as sm
    X = panel[terms].astype(float)
    X = pd.concat([X, pd.get_dummies(panel.sector, prefix="sec", drop_first=True, dtype=float)], axis=1)
    if year_fe:
        X = pd.concat([X, pd.get_dummies(panel.year, prefix="yr", drop_first=True, dtype=float)], axis=1)
    X = sm.add_constant(X)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = sm.GLM(panel.y.values, X, family=sm.families.Poisson(), offset=panel.offset.values).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(panel.plant_id)[0]})
    return m


def coef(m, t="x"):
    b, s = float(m.params[t]), float(m.bse[t])
    return {"rr_doubling": round(2 ** b, 4), "ci": [round(2 ** (b - 1.959964 * s), 4), round(2 ** (b + 1.959964 * s), 4)],
            "p": float(m.pvalues[t])}


def main():
    out = {}
    years = list(range(2004, 2022))
    pan, ilog = build(years)
    base = ["prior_acc5", "log_fte", "log_maxq", "log_nproc", "log_emis", "no_nei"]
    for k, col in (("zero_missing", "fte_zero_missing"), ("keep_zero", "fte_raw")):
        d = pan.copy()
        d["log_fte"] = np.log1p(d[col])
        d["log_maxq"] = np.log1p(d.maxq)
        d["log_nproc"] = np.log1p(d.nproc)
        need = ["log_fte", "log_maxq", "log_nproc", "sector"]
        dropped = d[need].isna().any(axis=1)
        d = d[~dropped]
        m2 = poisson(d, ["x"] + base)
        m2b = poisson(d, ["x"] + base + ["inspections", "violations", "enforcement"])
        out[f"H2_{k}"] = {**coef(m2), "plant_years": len(d), "plants": int(d.plant_id.nunique()),
                          "accidents": int(d.y.sum()), "plant_years_dropped_missing": int(dropped.sum())}
        out[f"H2b_{k}"] = {**coef(m2b), "regulator_terms": {t: coef(m2b, t) for t in ("inspections", "violations",
                                                                                         "enforcement")}}
        print(k, out[f"H2_{k}"], out[f"H2b_{k}"], flush=True)
    out["icis_log"] = ilog
    out["absolute_rate_per_1000_plant_years"] = round(1000 * pan.y.sum() / (np.exp(pan.offset).sum()), 2)
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")
    # H3 and usefulness on plant-quarters
    q, _ = build(list(range(2004, 2024)), quarters=True)
    q["log_fte"] = np.log1p(q.fte_zero_missing)
    q["log_maxq"] = np.log1p(q.maxq)
    q["log_nproc"] = np.log1p(q.nproc)
    q = q.dropna(subset=["log_fte", "log_maxq", "log_nproc", "sector"])
    train = q[q.year.between(2004, 2015)]
    base3 = ["log_fte", "log_maxq", "log_nproc", "log_emis", "no_nei", "prior_acc5", "inspections", "violations"]
    mb = poisson(train, base3, year_fe=False)
    mf = poisson(train, ["x"] + base3, year_fe=False)
    out["H3_fit_on_2004_2015"] = {"events_term": coef(mf), "plant_quarters": len(train), "accidents": int(train.y.sum())}
    for label, (y0, y1) in (("test_2016_2021", (2016, 2021)), ("test_2016_2023", (2016, 2023))):
        test = q[q.year.between(y0, y1)].copy()
        out[f"H3_{label}"] = h3_measures(test, mb, mf, base3)
        print(label, out[f"H3_{label}"], flush=True)
    out["usefulness"] = usefulness(q[q.year.between(2004, 2021)], mf, base3)
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")


def predict(m, d, terms):
    import statsmodels.api as sm
    X = d[terms].astype(float)
    X = pd.concat([X, pd.get_dummies(d.sector, prefix="sec", drop_first=True, dtype=float)], axis=1)
    X = sm.add_constant(X, has_constant="add")
    X = X.reindex(columns=m.params.index, fill_value=0.0)
    return np.exp(X.values @ m.params.values + d.offset.values)


def roc_auc_score(y, s):
    """Area under the ROC curve (Mann-Whitney, ties counted half)."""
    y = np.asarray(y)
    r = pd.Series(np.asarray(s)).rank().values
    n1 = y.sum()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def average_precision_score(y, s):
    """Average precision: mean of precision at each positive, scores sorted high to low (ties broken by order)."""
    y = np.asarray(y)[np.argsort(-np.asarray(s), kind="mergesort")]
    hits = np.cumsum(y)
    return float((hits[y == 1] / (np.flatnonzero(y == 1) + 1)).mean())


def h3_measures(test, mb, mf, base3, B=1000):
    test = test.assign(pb=predict(mb, test, base3), pf=predict(mf, test, ["x"] + base3), any=(test.y > 0).astype(int))

    def calib(y, mu):
        import statsmodels.api as sm
        m = sm.GLM(y, sm.add_constant(np.log(mu)), family=sm.families.Poisson()).fit()
        return float(m.params[1])

    def meas(d):
        r = {}
        for k, col in (("baseline", "pb"), ("with_events", "pf")):
            top = d[col] >= d[col].quantile(0.9)
            r[k] = {"auc_roc": roc_auc_score(d["any"], d[col]), "auc_pr": average_precision_score(d["any"], d[col]),
                    "share_accident_quarters_in_top10": float(d.loc[top, "any"].sum() / max(d["any"].sum(), 1)),
                    "calibration_slope": calib(d.y.values, d[col].values)}
        r["auc_roc_gain"] = r["with_events"]["auc_roc"] - r["baseline"]["auc_roc"]
        return r

    point = meas(test)
    rng = np.random.default_rng(3)
    plants = test.plant_id.unique()
    g = {p: x for p, x in test.groupby("plant_id")}
    boots = []
    for _ in range(B):
        d = pd.concat([g[p] for p in rng.choice(plants, len(plants))])
        if d["any"].sum() == 0 or d["any"].sum() == len(d):
            continue
        boots.append(meas(d))

    def ci(path):
        v = [b[path[0]][path[1]] if len(path) == 2 else b[path[0]] for b in boots]
        return [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]

    res = {"plant_quarters": len(test), "accident_quarters": int(test["any"].sum()), "bootstrap_draws": len(boots)}
    for k in ("baseline", "with_events"):
        res[k] = {m: {"value": round(point[k][m], 4), "ci": ci((k, m))} for m in point[k]}
    res["auc_roc_gain"] = {"value": round(point["auc_roc_gain"], 4), "ci": ci(("auc_roc_gain",))}
    return res


def usefulness(q, mf, base3):
    out = {}
    q = q.assign(any=(q.y > 0).astype(int))
    for k in (1, 3, 10):
        out[f"at_least_{k}_events_prior_90_days"] = flag_numbers(q, q.events_prior90 >= k)
    pf = predict(mf, q, ["x"] + base3)
    out["top10_H3_model"] = flag_numbers(q, pd.Series(pf >= np.quantile(pf, 0.9), index=q.index))
    return out


def flag_numbers(q, flag):
    f, a = flag.values, q["any"].values
    tp, fp = int((f & (a == 1)).sum()), int((f & (a == 0)).sum())
    return {"flagged_plant_quarters": int(f.sum()), "unflagged_plant_quarters": int((~f).sum()),
            "accident_quarters_per_1000_flagged": round(1000 * tp / max(f.sum(), 1), 2),
            "accident_quarters_per_1000_unflagged": round(1000 * int(((~f) & (a == 1)).sum()) / max((~f).sum(), 1), 2),
            "sensitivity": round(tp / max(a.sum(), 1), 3), "false_alarms_per_true_alarm": round(fp / max(tp, 1), 1)}


if __name__ == "__main__":
    main()
