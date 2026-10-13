"""Check of the Phase 4 result (docs/phase4_results.md): accident counts rebuilt straight from the accident table,
and the H1 model refit a third way (statsmodels Poisson GLM with a dummy for every plant-year, plant-clustered errors).
Usage: python3 src/h1_third_fit.py (results also saved to data/manifests/h1_third_fit.json)
"""
import sys, numpy as np, pandas as pd, statsmodels.api as sm, scipy.sparse as sp
sys.path.insert(0,'src'); import h1, run_h1
import json
linked, acc, risk, counts, log = run_h1.inputs()
out = {}
for end in [pd.Timestamp("2021-12-31"), pd.Timestamp("2023-12-31")]:
    a = run_h1.real_accidents(acc, linked, end)
    expo = h1.exposure_frame(sorted(a.plant_id.unique()), counts, risk, end=end)
    pan = h1.attach_outcome(expo, a)
    # independent y: straight from the raw accident CSV
    raw = pd.read_csv(h1.DER/"accidents_v2.csv", dtype=str, keep_default_na=False)
    plants = pd.read_csv(h1.DER/"plants_v2.csv"); L = set(plants.loc[plants.linked, "plant_id"])
    raw = raw[(raw.merged_into == "") & raw.plant_id.isin(L)]
    raw = raw[(raw.date >= "2003-06-01") & (raw.date <= str(end.date()))]
    yy = raw.groupby(["plant_id", "date"]).size()
    key = list(zip(pan.plant_id, pan.day.dt.strftime("%Y-%m-%d")))
    y_ind = np.array([yy.get(k, 0) for k in key])
    print(end.date(), "y matches independent count:", bool((y_ind == pan.y.values).all()), "| accidents in panel", int(pan.y.sum()), "raw in window", len(raw))
    # third fit: Poisson GLM with explicit plant-year and month dummies, plant-clustered SE
    X = pd.get_dummies(pan[["plant_year"]].astype(str), drop_first=False, dtype=float)
    M = pd.get_dummies(pan.moy.astype(str), prefix="m", drop_first=True, dtype=float)
    Z = pd.concat([pan[["x", "xs"]].reset_index(drop=True), M.reset_index(drop=True), X.reset_index(drop=True)], axis=1)
    g = pd.factorize(pan.plant_id)[0]
    m = sm.GLM(pan.y.values, Z.values, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": g}, maxiter=200, tol=1e-12)
    b, se = m.params[0], m.bse[0]
    out[str(end.date())] = {"y_matches_independent_count": bool((y_ind == pan.y.values).all()), "plant_days": len(pan),
                             "beta": float(b), "se": float(se), "rr_doubling": float(2 ** b),
                             "ci": [float(2 ** (b - 1.96 * se)), float(2 ** (b + 1.96 * se))], "p": float(m.pvalues[0])}
    print("   statsmodels GLM: beta %.8f se %.6f RR/doubling %.4f [%.4f, %.4f] p %.4f" % (b, se, 2**b, 2**(b-1.96*se), 2**(b+1.96*se), m.pvalues[0]))

(h1.ROOT / "data/manifests/h1_third_fit.json").write_text(json.dumps(out, indent=1) + "\n")
