"""Power check for H1 using fake accident dates (analysis plan section 6.5).

Real inputs used: event data, and how many accidents each plant-year has. Real
accident days are never used: in every run, accidents are placed on random days
inside the same plant-years, with chance proportional to (1 + E)^beta, where
beta = log2(planted rate ratio). Each fake dataset is analyzed three ways:
  primary  no days dropped after accidents
  R15      also drop accidents within 120 days after an earlier one (case days only)
  R16      drop days 1 to 120 after every accident (the original design; biased upward)
With a planted ratio of 1 (no effect), the share of runs with p < 0.05 checks
that the false-alarm rate is about 5%. Fits use the NumPy implementation, which
matches pyfixest to 1e-14 on these data.

Usage: python3 src/power_h1.py [runs_per_ratio] [v1|v2] [window_end YYYY-MM-DD] [ratios, comma separated] [--before-d8]
  v2 uses the extended, hand-reviewed links and merged duplicates (plan D2, D3); output power_h1_v2_<end>.json.
  --before-d8 uses the accident table as it was when the v2 power checks were run (2026-10-04): record 8699 not yet
  merged into its pair, which plan D8 item 3 did later (546 accidents in the 2021 window instead of 545). The stored
  v2 results were made this way. Without it the final table is used; one accident fewer changes the random draws, so
  the shares move by a few points.
"""
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h1  # noqa: E402
import h1_numpy  # noqa: E402

RATIOS = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
VARIANTS = {"primary": {}, "R15_drop_chain_cases_120": {"drop_chain_cases": 120},
            "R16_post_exclusion_120": {"post_excl": 120}}
OUT = h1.ROOT / "data" / "derived" / "power_h1.json"
_G = {}


def setup(version="v1", before_d8=False):
    plants, ev, acc, risk = h1.load(version)
    if before_d8 and version == "v2":
        full = pd.read_csv(h1.DER / "accidents_v2.csv", parse_dates=["date"], keep_default_na=False,
                           dtype={"AccidentHistoryID": str, "EPAFacilityID": str, "merged_into": str})
        full["plant_id"] = full.plant_id.replace("", np.nan)
        acc = full[(full.merged_into == "") | (full.AccidentHistoryID == "8699")]
    linked = set(plants.loc[plants.linked, "plant_id"])
    acc = acc[acc.plant_id.isin(linked) & acc.date.between(h1.STUDY_START, h1.STUDY_END)]
    k = acc.assign(year=acc.date.dt.year).groupby(["plant_id", "year"]).size()   # accidents per plant-year
    counts = h1.daily_counts(ev)
    expo = h1.exposure_frame(sorted(k.index.get_level_values(0).unique()), counts, risk)
    expo = expo.merge(k.rename("k"), left_on=["plant_id", "year"], right_index=True, how="inner")
    return expo


def init(expo):
    _G["expo"] = expo
    _G["groups"] = [(p, g.day.values, g.x.values, int(g.k.iloc[0]))
                    for (p, _), g in expo.groupby(["plant_id", "year"], sort=False)]


def one_run(args):
    ratio, seed = args
    rng = np.random.default_rng(seed)
    beta = np.log(ratio) / np.log(2)
    picks = []
    for p, days, x, k in _G["groups"]:
        w = np.exp(beta * x)
        idx = rng.choice(len(days), size=min(k, len(days)), replace=False, p=w / w.sum())
        picks.append(pd.DataFrame({"plant_id": p, "day": days[idx]}))
    fake = pd.concat(picks, ignore_index=True)
    base = _G["expo"].drop(columns="k")
    out = []
    for name, kw in VARIANTS.items():
        pan = h1.attach_outcome(base, fake, **kw)
        r = h1_numpy.fit(pan)
        r.update(ratio=ratio, seed=seed, variant=name,
                 p=float(2 * norm.sf(abs(r["beta"] / r["se"]))),
                 ci_low=2 ** (r["beta"] - 1.959964 * r["se"]), ci_high=2 ** (r["beta"] + 1.959964 * r["se"]))
        out.append(r)
    return out


def main():
    before_d8 = "--before-d8" in sys.argv
    if before_d8:
        sys.argv.remove("--before-d8")
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    version = sys.argv[2] if len(sys.argv) > 2 else "v1"
    if len(sys.argv) > 3:
        h1.STUDY_END = pd.Timestamp(sys.argv[3])
    ratios = [float(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else RATIOS
    out_file = OUT if version == "v1" else OUT.with_name(f"power_h1_v2_{h1.STUDY_END.date()}.json")
    if ratios != RATIOS:
        out_file = out_file.with_name(out_file.stem + "_ratios_" + "_".join(str(r) for r in ratios) + ".json")
    t0 = time.time()
    expo = setup(version, before_d8)
    jobs = [(r, 2_000_000 * i + s) for i, r in enumerate(ratios) for s in range(runs)]
    with Pool(3, initializer=init, initargs=(expo,)) as pool:
        res = pool.map(one_run, jobs, chunksize=10)
    df = pd.DataFrame([r for trio in res for r in trio])
    summary = []
    for (v, r), g in df.groupby(["variant", "ratio"]):
        summary.append({"variant": v, "planted_ratio": r, "runs": len(g),
                        "share_p_below_0.05": round((g.p < 0.05).mean(), 3),
                        "share_detected_and_positive": round(((g.p < 0.05) & (g.beta > 0)).mean(), 3),
                        "median_estimated_ratio": round(g.rr_doubling.median(), 3),
                        "median_ci": [round(g.ci_low.median(), 3), round(g.ci_high.median(), 3)],
                        "median_accidents_used": int(g.n_accidents.median())})
    out = {"runs_per_ratio": runs, "links": version, "seconds": round(time.time() - t0), "formula": h1.PRIMARY,
           "design": {"window": h1.WINDOW, "gap": h1.GAP,
                      "study": [str(h1.STUDY_START.date()), str(h1.STUDY_END.date())]},
           "plant_years": int(expo.groupby(["plant_id", "year"]).ngroups), "plants": int(expo.plant_id.nunique()),
           "summary": summary}
    out_file.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
