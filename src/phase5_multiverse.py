"""Phase 5: the multiverse of plan D2 item 9. H1 over every combination of window end (2021, 2022, 2023, 2025),
gap (0, 1, 7, 30 days), window length (30, 90, 180, 365 days), events counted (unplanned; plus opacity; all
types), linking (registry only; full; one-to-one) and doubles (merged; not). 1,152 fits. Shown as a spread, not as
tests; the primary result stays the primary result.
Output: data/manifests/phase5_multiverse.csv (written every 48 fits; with --resume, fits already in it are kept and
only the missing ones are run, so a long run can be stopped and continued)
"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402
import phase5_robust as RB  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_multiverse.csv"
TYPES = {"unplanned": ("EMISSIONS EVENT",), "plus_opacity": ("EMISSIONS EVENT", "EXCESS OPACITY"),
         "all_types": ("EMISSIONS EVENT", "EXCESS OPACITY", "MAINTENANCE", "AIR STARTUP", "AIR SHUTDOWN")}
_R19 = {}
KEYS = ["end", "gap", "window", "events", "linking", "doubles"]


def one(combo):
    end, gap, window, types, linking, doubles = combo
    kw = dict(end=f"{end}-12-31", gap=gap, window=window, event_types=TYPES[types])
    if linking == "registry_only":
        kw["links"] = "v1"
    elif linking == "one_to_one":
        kw["plants_subset"] = "one_to_one"
    if doubles == "not_merged":
        if linking == "registry_only":
            kw["accident_merge"] = True   # the registry-only table has no merges: identical to merged
        else:
            if "t" not in _R19:
                _R19["t"] = RB.r19_table()
            kw["accidents"] = _R19["t"]
    row = dict(end=end, gap=gap, window=window, events=types, linking=linking, doubles=doubles)
    try:
        r = P.h1_run(**kw)
        t = r["terms"]["x"]
        row.update(rr=t["rr_doubling"], ci_low=t["ci"][0], ci_high=t["ci"][1], p=t["p"], n_accidents=r["n_accidents"],
                   n_plants=r["n_plants"], fitted_by=r.get("fitted_by"))
    except Exception as e:  # noqa: BLE001
        row.update(error=f"{type(e).__name__}: {e}")
    return row


def main():
    combos = list(itertools.product((2021, 2022, 2023, 2025), (0, 1, 7, 30), (30, 90, 180, 365), list(TYPES),
                                    ("registry_only", "full", "one_to_one"), ("merged", "not_merged")))
    rows = []
    if "--resume" in sys.argv and OUT.exists():
        rows = pd.read_csv(OUT, float_precision="round_trip").to_dict("records")
        done = {tuple(r[k] for k in KEYS) for r in rows}
        combos = [c for c in combos if c not in done]
        print(len(rows), "fits kept,", len(combos), "to run", flush=True)
    total = len(rows) + len(combos)
    with Pool(3) as pool:
        for i, r in enumerate(pool.imap_unordered(one, combos, chunksize=4), len(rows) + 1):
            rows.append(r)
            if i % 48 == 0:
                pd.DataFrame(rows).to_csv(OUT, index=False)
                print(i, "of", total, flush=True)
    d = pd.DataFrame(rows).sort_values(KEYS)
    d.to_csv(OUT, index=False)
    ok = d.dropna(subset=["rr"])
    print("fits", len(d), "ok", len(ok), "| median rr", round(ok.rr.median(), 3), "| share rr>1", round((ok.rr > 1).mean(), 3),
          "| share p<0.05 and rr>1", round(((ok.p < 0.05) & (ok.rr > 1)).mean(), 3),
          "| share p<0.05 and rr<1", round(((ok.p < 0.05) & (ok.rr < 1)).mean(), 3))
    print(ok.groupby("window").rr.median().round(3).to_dict())


if __name__ == "__main__":
    main()
