"""Independent implementation of the H1 model from scratch (analysis plan section 6.6).

Conditional Poisson regression: within each plant-year stratum g, given the
stratum's accident total n_g, accidents fall on days with multinomial
probabilities p_i = exp(eta_i) / sum_g exp(eta), where
eta_i = beta * x_i + delta * xs_i + gamma[month_of_year_i] (January = 0).
The plant-year effects cancel out exactly, so none are estimated. Fit by
Newton's method with the analytic gradient and Hessian; standard errors are
clustered by plant (sandwich with the G/(G-1) small-sample factor).

This shares no code with pyfixest, which removes the effects by demeaning.
"""
import numpy as np
import pandas as pd


def design(pan):
    moy = pan["moy"].to_numpy()
    month = np.zeros((len(pan), 11))
    for m in range(2, 13):
        month[:, m - 2] = moy == m
    return np.column_stack([pan["x"].to_numpy(), pan["xs"].to_numpy(), month])


def fit(pan, tol=1e-10, max_iter=100):
    pan = pan.reset_index(drop=True)
    Z = design(pan)
    y = pan["y"].to_numpy(dtype=float)
    g_codes, g_index = np.unique(pan["plant_year"].to_numpy(), return_inverse=True)
    n_g = np.bincount(g_index, weights=y)
    keep = n_g[g_index] > 0
    Z, y, g_index = Z[keep], y[keep], g_index[keep]
    _, g_index = np.unique(g_index, return_inverse=True)
    n_g = np.bincount(g_index, weights=y)
    # drop month columns that never vary within the kept data
    usable = Z.std(axis=0) > 0
    Z = Z[:, usable]
    k = Z.shape[1]
    theta = np.zeros(k)

    def pieces(theta):
        eta = Z @ theta
        eta -= np.bincount(g_index, weights=eta)[g_index] / np.bincount(g_index)[g_index]  # stability
        w = np.exp(eta)
        s = np.bincount(g_index, weights=w)
        p = w / s[g_index]
        mu = n_g[g_index] * p
        return p, mu

    for _ in range(max_iter):
        p, mu = pieces(theta)
        grad = Z.T @ (y - mu)
        # Hessian of the multinomial log-likelihood: -sum_g n_g (Z' diag(p) Z - zbar zbar')
        zbar = np.vstack([np.bincount(g_index, weights=p * Z[:, j]) for j in range(k)]).T
        H = -(Z.T @ (Z * mu[:, None])) + (zbar.T * n_g) @ zbar
        step = np.linalg.solve(H, grad)
        theta = theta - step
        if np.max(np.abs(step)) < tol:
            break
    p, mu = pieces(theta)
    zbar = np.vstack([np.bincount(g_index, weights=p * Z[:, j]) for j in range(k)]).T
    H = -(Z.T @ (Z * mu[:, None])) + (zbar.T * n_g) @ zbar
    # cluster-robust variance by plant
    plants = pan.loc[keep, "plant_id"].to_numpy()
    _, c_index = np.unique(plants, return_inverse=True)
    G = c_index.max() + 1
    score = (Z * (y - mu)[:, None])
    S = np.vstack([np.bincount(c_index, weights=score[:, j], minlength=G) for j in range(k)]).T
    Hinv = np.linalg.inv(H)
    V = Hinv @ (S.T @ S) @ Hinv * G / (G - 1)
    b, se = theta[0], np.sqrt(V[0, 0])
    return {"beta": float(b), "se": float(se), "rr_doubling": float(2 ** b),
            "delta_statewide": float(theta[1]), "n_days": int(keep.sum()), "n_accidents": int(y.sum()),
            "n_plants": int(G)}
