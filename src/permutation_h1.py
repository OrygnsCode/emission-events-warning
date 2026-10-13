"""Shuffle test for H1 (analysis plan section 5.1).

Each accident is moved to a random day in the same plant and year (no planted
effect), post-accident exclusions are recomputed for the new days, and the H1
model is refit with the independent NumPy implementation. The two-sided p value
is (1 + number of shuffles with |beta| >= |observed beta|) / (shuffles + 1).

Module use: null_betas(expo_with_k, n, seed) -> array of betas under no effect.
"""
from multiprocessing import Pool

import numpy as np
import pandas as pd

import h1
import h1_numpy

_G = {}


def _init(expo):
    _G["expo"] = expo
    _G["groups"] = [(p, g.day.values, int(g.k.iloc[0])) for (p, _), g in expo.groupby(["plant_id", "year"], sort=False)]


def _one(seed):
    rng = np.random.default_rng(seed)
    picks = [pd.DataFrame({"plant_id": p, "day": days[rng.choice(len(days), size=min(k, len(days)), replace=False)]})
             for p, days, k in _G["groups"]]
    pan = h1.attach_outcome(_G["expo"].drop(columns="k"), pd.concat(picks, ignore_index=True))
    return h1_numpy.fit(pan)["beta"]


def null_betas(expo_with_k, n, seed=20261002, workers=3):
    seeds = [seed * 100_000 + i for i in range(n)]
    with Pool(workers, initializer=_init, initargs=(expo_with_k,)) as pool:
        return np.array(pool.map(_one, seeds, chunksize=20))


def p_value(observed_beta, betas):
    return (1 + np.sum(np.abs(betas) >= abs(observed_beta))) / (len(betas) + 1)
