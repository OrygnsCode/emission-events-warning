"""Phase 4: the H1 primary test (analysis plan section 5.1, with deviation D2), run end to end.

What it does, for the primary window end (December 31, 2021, D2 item 1) and the original frozen end (December 31,
2023), reported side by side:
  1. accidents: O1 (any RMP accident), extended links and merged doubles (D2 items 2 and 3), at linked plants, dated
     in the window; accidents on days the plant is not at risk are counted and left out;
  2. exposure: emissions-event occurrences (same-start merge) in days -97 to -8, reports whose text says they
     duplicate another not counted (frozen rule), statewide count at every other site as a control;
  3. the model in two programs that share no code (pyfixest and the NumPy conditional likelihood, section 6.6),
     which must agree;
  4. the shuffle test: accident days moved at random within the same plant and year 10,000 times;
  5. the picture: events by month from 24 months before to 12 months after accidents, relative to each plant's
     own average, beside the same curve for random dates in the same plant-years.

Modes:
  --fake [--planted R]  (default) accident days are drawn at random inside the real plant-years with chance
                        proportional to (1 + E)^log2(R), as in the power check. Real accident days are not read.
                        Used to test this script before Phase 4.
  --real                the real accident days. Run only with the author's go (Phase 4).
Output: data/derived/h1_dryrun_<R>.json (fake) or data/manifests/h1_primary_result.json (real).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h1  # noqa: E402
import h1_numpy  # noqa: E402
import permutation_h1  # noqa: E402

ENDS = {"primary_end_2021": pd.Timestamp("2021-12-31"), "original_end_2023": pd.Timestamp("2023-12-31")}
MONTH = 30.4375


def inputs():
    plants, ev, acc, risk = h1.load("v2")
    linked = set(plants.loc[plants.linked, "plant_id"])
    excl = json.loads((h1.DER / "h1_exclusion_sets.json").read_text())["primary"]
    counts = h1.daily_counts(ev, exclude_incidents=excl)
    log = {"linked_plants": len(linked), "reports_not_counted_frozen_duplicate": len(excl),
           "reports_without_any_date": int(ev.date_source.eq("none").sum())}
    return linked, acc, risk, counts, log


def real_accidents(acc, linked, end):
    a = acc[acc.plant_id.isin(linked) & acc.date.between(h1.STUDY_START, end)]
    return pd.DataFrame({"plant_id": a.plant_id.values, "day": a.date.dt.normalize().values})


def fake_accidents(expo_k, planted, seed):
    """Random days inside the plant-years, k per plant-year, chance proportional to (1 + E)^log2(planted)."""
    rng = np.random.default_rng(seed)
    beta = np.log(planted) / np.log(2)
    picks = []
    for (p, _), g in expo_k.groupby(["plant_id", "year"], sort=False):
        w = np.exp(beta * g.x.values)
        k = min(int(g.k.iloc[0]), len(g))
        idx = rng.choice(len(g), size=k, replace=False, p=w / w.sum())
        picks.append(pd.DataFrame({"plant_id": p, "day": g.day.values[idx]}))
    return pd.concat(picks, ignore_index=True)


def picture(acc_days, counts, expo_all, n_fake=100, seed=7):
    """Events per month-offset around accidents, relative to the plant's own average daily rate over its at-risk days
    in the window. Bin b covers day offsets round(b * 30.44) to round((b + 1) * 30.44) - 1; only days inside the event
    data (from 2003-02-01 to the last event) count toward the expected number."""
    span = expo_all.groupby("plant_id").day.agg(["min", "max"])
    first = pd.Timestamp("2003-02-01")
    last = counts.index.get_level_values("day").max()
    ev_days, avg = {}, {}
    for p in span.index:
        c = counts[p] if p in counts.index.get_level_values(0) else pd.Series(dtype=int)
        d = c.index.values.repeat(c.values) if len(c) else np.array([], dtype="datetime64[ns]")
        ev_days[p] = d
        lo, hi = span.at[p, "min"], span.at[p, "max"]
        avg[p] = ((d >= lo.to_datetime64()) & (d <= hi.to_datetime64())).sum() / ((hi - lo).days + 1)
    bins = np.arange(-24, 13)
    edges = [(int(round(b * MONTH)), int(round((b + 1) * MONTH)) - 1) for b in bins]

    def curve(days_df):
        obs, exp = np.zeros(len(bins)), np.zeros(len(bins))
        for p, d in zip(days_df.plant_id, days_df.day):
            if not avg.get(p):
                continue
            d = pd.Timestamp(d).normalize()
            t = (ev_days[p] - d.to_datetime64()) / np.timedelta64(1, "D")
            for i, (a, b) in enumerate(edges):
                lo, hi = max(d + pd.Timedelta(days=a), first), min(d + pd.Timedelta(days=b), last)
                if hi < lo:
                    continue
                ta, tb = (lo - d).days, (hi - d).days
                obs[i] += ((t >= ta) & (t <= tb)).sum()
                exp[i] += avg[p] * (tb - ta + 1)
        return obs, exp

    o, e = curve(acc_days)
    rng = np.random.default_rng(seed)
    pool = {k: g.day.values for k, g in expo_all.groupby(["plant_id", "year"])}
    fo, fe = np.zeros(len(bins)), np.zeros(len(bins))
    for _ in range(n_fake):
        rows = []
        for p, d in zip(acc_days.plant_id, acc_days.day):
            days = pool.get((p, pd.Timestamp(d).year))
            if days is not None:
                rows.append((p, days[rng.integers(len(days))]))
        a_, b_ = curve(pd.DataFrame(rows, columns=["plant_id", "day"]))
        fo += a_
        fe += b_
    ratio = lambda x, y: [None if v == 0 else round(float(u / v), 3) for u, v in zip(x, y)]  # noqa: E731
    return {"month_offset": bins.tolist(), "accident_ratio_to_plant_average": ratio(o, e),
            "random_dates_ratio_to_plant_average": ratio(fo, fe), "random_draws": n_fake,
            "accidents_used": int(sum(1 for p in acc_days.plant_id if avg.get(p)))}


def one_end(name, end, linked, acc, risk, counts, mode, planted, shuffles, seed):
    t0 = time.time()
    if mode == "real":
        acc_days = real_accidents(acc, linked, end)
        plants_with = sorted(acc_days.plant_id.unique())
    else:
        a = acc[acc.plant_id.isin(linked) & acc.date.between(h1.STUDY_START, end)]   # plant-year counts only
        k = a.assign(year=a.date.dt.year).groupby(["plant_id", "year"]).size().rename("k")
        plants_with = sorted(k.index.get_level_values(0).unique())
    expo = h1.exposure_frame(plants_with, counts, risk, end=end)
    if mode == "fake":
        expo_k = expo.merge(k, left_on=["plant_id", "year"], right_index=True, how="inner")
        acc_days = fake_accidents(expo_k, planted, seed)
    at_risk = set(zip(expo.plant_id, expo.day))
    inside = np.array([(p, pd.Timestamp(d)) in at_risk for p, d in zip(acc_days.plant_id, acc_days.day)])
    log = {"accidents_at_linked_plants_in_window": len(acc_days),
           "accidents_on_days_not_at_risk_left_out": int((~inside).sum()),
           "plants_with_accidents": len(plants_with)}
    acc_days = acc_days[inside]
    pan = h1.attach_outcome(expo, acc_days)
    r_pf = h1.fit(pan)
    r_np = h1_numpy.fit(pan)
    agree = {"beta_abs_diff": abs(r_pf["beta"] - r_np["beta"]),
             "se_rel_diff": abs(r_pf["se"] - r_np["se"]) / r_np["se"]}
    agree["programs_agree"] = bool(agree["beta_abs_diff"] < 1e-6 and agree["se_rel_diff"] < 0.01)
    # shuffle test: accident days moved within the same plant and year
    k_obs = acc_days.assign(year=pd.to_datetime(acc_days.day).dt.year).groupby(["plant_id", "year"]).size().rename("k")
    expo_k = expo.merge(k_obs, left_on=["plant_id", "year"], right_index=True, how="inner")
    betas = permutation_h1.null_betas(expo_k, shuffles, seed=20261002, workers=4)
    p_shuffle = float(permutation_h1.p_value(r_np["beta"], betas))
    res = {"log": log, "pyfixest": r_pf, "numpy": r_np, "agreement": agree,
           "shuffle_test": {"shuffles": int(shuffles), "p": round(p_shuffle, 5)},
           "robust": bool(not (r_pf["p"] < 0.05 and p_shuffle > 0.05)),
           "picture": picture(acc_days, counts, expo),
           "seconds": round(time.time() - t0)}
    print(name, json.dumps({k: res[k] for k in ("log", "agreement", "shuffle_test", "robust")}), flush=True)
    print(name, "rate ratio per doubling", round(r_pf["rr_doubling"], 3),
          [round(r_pf["ci_low"], 3), round(r_pf["ci_high"], 3)], "p", round(r_pf["p"], 4), flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--planted", type=float, default=1.0)
    ap.add_argument("--shuffles", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    mode = "real" if a.real else "fake"
    linked, acc, risk, counts, log = inputs()
    out = {"mode": mode, "planted_ratio": None if mode == "real" else a.planted, "formula": h1.PRIMARY,
           "design": {"window": h1.WINDOW, "gap": h1.GAP, "study_start": str(h1.STUDY_START.date()), "links": "v2"},
           "log": log}
    for name, end in ENDS.items():
        out[name] = one_end(name, end, linked, acc, risk, counts, mode, a.planted, a.shuffles, a.seed)
    dest = (h1.ROOT / "data" / "manifests" / "h1_primary_result.json" if mode == "real"
            else h1.DER / f"h1_dryrun_{a.planted}_seed{a.seed}.json")
    dest.write_text(json.dumps(out, indent=1, default=float) + "\n")
    print("written", dest)


if __name__ == "__main__":
    main()
