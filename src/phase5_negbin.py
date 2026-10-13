"""R11, negative binomial version (plan 6.2): NB2 with a separate intercept for every plant-year, month-of-year effects
and the statewide count; plant-clustered errors. Strata without accidents are dropped, as in the Poisson fit.

Fitted by Fisher scoring that keeps the plant-year intercepts in a diagonal block (no dummy matrix), so it needs
little memory; the dispersion alpha is chosen by maximum likelihood over a grid. Check: with alpha near 0 it must
reproduce the Poisson estimate. Errors: sandwich of the scores with the plant-year intercepts partialled out,
summed by plant, with G/(G-1). (A dense statsmodels fit ran out of memory, D9.)
Output: added to data/manifests/phase5_robustness.json as R11_negative_binomial
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import gammaln
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_robustness.json"


def fit_nb(Z, y, g, alpha, tol=1e-9, max_iter=500):
    G = g.max() + 1
    k = Z.shape[1]
    b = np.zeros(k)
    a = np.log(np.bincount(g, weights=y) / np.bincount(g))
    for it in range(max_iter):
        mu = np.exp(a[g] + Z @ b)
        r = (y - mu) / (1 + alpha * mu)
        w = mu / (1 + alpha * mu)
        sa = np.bincount(g, weights=r)
        sb = Z.T @ r
        haa = np.bincount(g, weights=w)
        hab = np.vstack([np.bincount(g, weights=w * Z[:, j], minlength=G) for j in range(k)]).T
        hbb = Z.T @ (Z * w[:, None])
        S = hbb - hab.T @ (hab / haa[:, None])
        db = np.linalg.solve(S, sb - hab.T @ (sa / haa))
        da = (sa - hab @ db) / haa
        b, a = b + db, a + da
        if max(np.abs(db).max(), np.abs(da).max()) < tol:
            break
    mu = np.exp(a[g] + Z @ b)
    inv = 1.0 / alpha
    ll = float(np.sum(gammaln(y + inv) - gammaln(inv) - gammaln(y + 1) + inv * np.log(inv / (inv + mu))
                      + y * np.log(mu / (inv + mu))))
    return b, a, mu, ll, it


def sandwich(Z, y, g, plant, mu, alpha):
    w = mu / (1 + alpha * mu)
    r = (y - mu) / (1 + alpha * mu)
    zbar = np.vstack([np.bincount(g, weights=w * Z[:, j]) / np.bincount(g, weights=w) for j in range(Z.shape[1])]).T
    Zt = Z - zbar[g]
    A = Zt.T @ (Zt * w[:, None])
    u = Zt * r[:, None]
    _, c = np.unique(plant, return_inverse=True)
    C = c.max() + 1
    B = np.vstack([np.bincount(c, weights=u[:, j], minlength=C) for j in range(Z.shape[1])]).T
    Ai = np.linalg.inv(A)
    return Ai @ (B.T @ B) @ Ai * C / (C - 1)


def main():
    pan = P.h1_run(keep_panel=True)["panel"]
    pan = pan[pan.groupby("plant_year").y.transform("sum") > 0].reset_index(drop=True)
    month = np.column_stack([(pan.moy.values == m).astype(float) for m in range(2, 13)])
    Z = np.column_stack([pan["x"].values, pan["xs"].values, month])
    y = pan.y.values.astype(float)
    _, g = np.unique(pan.plant_year.values, return_inverse=True)
    # check: alpha near 0 reproduces the Poisson estimate
    b0, *_ = fit_nb(Z, y, g, 1e-8)
    grid = np.exp(np.linspace(np.log(0.01), np.log(20), 25))
    fits = [fit_nb(Z, y, g, a) for a in grid]
    lls = [f[3] for f in fits]
    i = int(np.argmax(lls))
    b, a, mu, ll, it = fits[i]
    V = sandwich(Z, y, g, pan.plant_id.values, mu, grid[i])
    se = float(np.sqrt(V[0, 0]))
    res = {"rr": round(2 ** b[0], 4), "ci": [round(2 ** (b[0] - 1.959964 * se), 4), round(2 ** (b[0] + 1.959964 * se), 4)],
           "p": float(2 * norm.sf(abs(b[0] / se))), "n_accidents": int(y.sum()), "alpha": round(float(grid[i]), 4),
           "alpha_at_grid_edge": i in (0, len(grid) - 1),
           "check_alpha_near_0_beta": float(b0[0]), "poisson_beta": -0.18627538207990202,
           "loglik_by_alpha": {round(float(x), 4): round(v, 2) for x, v in zip(grid, lls)},
           "note": "NB2, plant-year intercepts, month effects, statewide count; alpha by grid maximum likelihood; "
                   "plant-clustered sandwich"}
    d = json.loads(OUT.read_text())
    d["R11_negative_binomial"] = res
    OUT.write_text(json.dumps(d, indent=1, default=float) + "\n")
    print({k: v for k, v in res.items() if k != "loglik_by_alpha"}, flush=True)


if __name__ == "__main__":
    main()
