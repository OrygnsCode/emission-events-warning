"""Check V3 (plan D6 item 9): refinery fenceline benzene against reported events, by refinery-quarter.

Unit: refinery-quarter of the main sampler ring, 2018 to 2021 (2022 to 2025 shown as description).
Value: mean two-week delta c of periods ending in the quarter (periods with suspect dates left out); quarters with
fewer than 4 valid periods dropped. Exposure: D6 episodes at the refinery's plant in the quarter (RN from the
crosswalk -> plant). Model: OLS of log mean delta c on log(1 + episodes) with refinery and quarter effects;
refinery-clustered errors and a wild cluster bootstrap (Rademacher weights, 9,999 draws, null imposed).

Output: data/derived/vchecks/v3_result.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vchecks_common as vc  # noqa: E402


def design(d):
    X = pd.get_dummies(d[["refinery", "q"]].astype(str), drop_first=True).astype(float)
    X.insert(0, "x", d.x.values)
    X.insert(0, "const", 1.0)
    return X.values, d.y.values, d.refinery.values


def ols_cluster(X, y, g):
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    G = np.unique(g)
    for c in G:
        s = X[g == c].T @ u[g == c]
        meat += np.outer(s, s)
    n, k = X.shape
    adj = len(G) / (len(G) - 1) * (n - 1) / (n - k)
    V = adj * XtX_inv @ meat @ XtX_inv
    return b, np.sqrt(np.diag(V)), u


def wild_bootstrap_p(X, y, g, reps=9999, seed=7):
    """Wild cluster bootstrap-t for the coefficient on x (column 1), with the null b_x = 0 imposed."""
    rng = np.random.default_rng(seed)
    b, se, _ = ols_cluster(X, y, g)
    t_obs = b[1] / se[1]
    Xr = np.delete(X, 1, axis=1)
    br = np.linalg.pinv(Xr.T @ Xr) @ Xr.T @ y
    fit_r, u_r = Xr @ br, y - Xr @ br
    G = np.unique(g)
    gi = np.searchsorted(G, g)
    ts = np.empty(reps)
    for i in range(reps):
        w = rng.choice([-1.0, 1.0], size=len(G))[gi]
        yb = fit_r + u_r * w
        bb, sb, _ = ols_cluster(X, yb, g)
        ts[i] = bb[1] / sb[1]
    return float((np.abs(ts) >= abs(t_obs)).mean())


def main():
    f = pd.read_csv(vc.DER / "fenceline_periods.csv", parse_dates=["start", "end"], date_format="%Y-%m-%d")
    f = f[f.network.eq("main") & ~f.date_suspect & f.period_dc.notna() & f.end.notna()].copy()
    f["q"] = f.end.dt.to_period("Q")
    qd = f.groupby(["refinery", "rn_crosswalk", "q"]).agg(dc=("period_dc", "mean"), n=("period_dc", "size")).reset_index()
    pm = pd.read_csv(vc.DER / "plant_members_v2.csv").query("id_type == 'RN'")
    rn2p = dict(zip(pm.id, pm.plant_id))
    qd["plant_id"] = qd.rn_crosswalk.map(rn2p)
    ep = pd.read_pickle(vc.OUT / "episodes.pkl")
    ep["q"] = ep.start_local.dt.to_period("Q")
    cnt = ep.groupby(["plant_id", "q"]).size().rename("episodes")
    qd = qd.join(cnt, on=["plant_id", "q"]).fillna({"episodes": 0})
    log = {"refinery_quarters_all": len(qd), "refineries": int(qd.refinery.nunique()),
           "refineries_without_plant_link": sorted(qd[qd.plant_id.isna()].refinery.unique().tolist()),
           "quarters_under_4_periods": int((qd.n < 4).sum())}
    d = qd[(qd.n >= 4) & qd.plant_id.notna()].copy()
    d["year"] = d.q.dt.year
    prim = d[d.year.between(2018, 2021)].copy()
    prim["y"] = np.log(prim.dc.clip(lower=0.01))
    prim["x"] = np.log1p(prim.episodes)
    X, y, g = design(prim)
    b, se, _ = ols_cluster(X, y, g)
    p_wild = wild_bootstrap_p(X, y, g)
    out = {"rule": "plan D6 item 9", "log": log,
           "primary_2018_2021": {"refinery_quarters": len(prim), "refineries": int(prim.refinery.nunique()),
                                 "quarters_with_any_episode": int((prim.episodes > 0).sum()),
                                 "coef_log1p_episodes": round(float(b[1]), 4),
                                 "cluster_se": round(float(se[1]), 4),
                                 "ci95": [round(float(b[1] - 1.96 * se[1]), 4), round(float(b[1] + 1.96 * se[1]), 4)],
                                 "wild_cluster_bootstrap_p": round(p_wild, 4),
                                 "meaning": "percent change in mean delta c for a doubling of (1 + episodes) is about "
                                            f"{round(float((2 ** b[1] - 1) * 100), 1)}%"},
           "descriptive_mean_dc_by_episode_band": prim.assign(
               band=pd.cut(prim.episodes, [-1, 0, 2, 5, 1000], labels=["0", "1-2", "3-5", "6+"])).groupby(
               "band", observed=True).dc.agg(["size", "median", "mean"]).round(2).to_dict(orient="index")}
    # 2022 to 2025, description only (D6 item 9): the D6 event set ends in 2021, so these quarters count every
    # emissions event report at the plant (same-start merge applied), without the D6 text filters
    ev = pd.read_csv(vc.DER / "events_v2.csv.gz", usecols=["plant_id", "event_type", "is_duplicate", "event_datetime"],
                     parse_dates=["event_datetime"])
    ev = ev[ev.event_type.eq("EMISSIONS EVENT") & ~ev.is_duplicate & ev.event_datetime.dt.year.between(2022, 2025)]
    late = d[d.year.between(2022, 2025)].drop(columns="episodes").join(
        ev.assign(q=ev.event_datetime.dt.to_period("Q")).groupby(["plant_id", "q"]).size().rename("reports"),
        on=["plant_id", "q"]).fillna({"reports": 0})
    out["description_2022_2025"] = {
        "refinery_quarters": len(late), "refineries": int(late.refinery.nunique()),
        "last_quarter": str(late.q.max()) if len(late) else None,
        "spearman_reports_vs_dc": round(float(late[["reports", "dc"]].corr(method="spearman").iloc[0, 1]), 3)
        if len(late) > 2 else None,
        "mean_dc_by_report_band": late.assign(
            band=pd.cut(late.reports, [-1, 0, 2, 5, 1000], labels=["0", "1-2", "3-5", "6+"])).groupby(
            "band", observed=True).dc.agg(["size", "median", "mean"]).round(2).to_dict(orient="index")}
    (vc.OUT / "v3_result.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
