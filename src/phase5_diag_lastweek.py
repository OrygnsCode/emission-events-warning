"""Phase 5 diagnostic (D9): the only multiverse corner with significant positive estimates is the 30-day window with
no gap (or a 1-day gap), all event types, registry-only links (rate ratios 1.15 to 1.19 in that corner; 1.18 to 1.19 for the significant ones). A 7-day gap removes it,
so it comes from events in the last week before the accident. This splits the 30-day window into the last week
(days -7 to -1) and the rest (days -30 to -8), and the event types into planned (maintenance, startup, shutdown) and
unplanned (emission events, excess opacity), to see where it sits. Model and everything else as in the multiverse
row (end 2023). Statewide control: one per exposure.
Output: data/manifests/phase5_diag_lastweek.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_lastweek.json"
PLANNED = ("MAINTENANCE", "AIR STARTUP", "AIR SHUTDOWN")
UNPLANNED = ("EMISSIONS EVENT", "EXCESS OPACITY")
ALL = UNPLANNED + PLANNED


def term(r, t):
    x = r["terms"][t]
    return {"rr": round(x["rr_doubling"], 3), "ci": [round(c, 3) for c in x["ci"]], "p": round(x["p"], 4)}


def run(links, plants_subset=None):
    _, ev, *_ = P.tables(links)
    c = {k: P.event_counts(ev, v) for k, v in (("all", ALL), ("planned", PLANNED), ("unplanned", UNPLANNED))}
    base = dict(end="2023-12-31", links=links, plants_subset=plants_subset, statewide_each=True)
    out = {}
    r = P.h1_run(window=30, gap=0, event_types=ALL, **base)
    out["row_as_in_multiverse"] = term(r, "x") | {"n_accidents": r["n_accidents"]}
    r = P.h1_run(exposures={"last_week": (c["all"], 7, 0), "days_8_to_30": (c["all"], 23, 7)}, **base)
    out["all_types_split_by_time"] = {t: term(r, t) for t in ("last_week", "days_8_to_30")}
    r = P.h1_run(exposures={"planned_last_week": (c["planned"], 7, 0), "unplanned_last_week": (c["unplanned"], 7, 0),
                            "planned_days_8_to_30": (c["planned"], 23, 7),
                            "unplanned_days_8_to_30": (c["unplanned"], 23, 7)}, **base)
    out["split_by_time_and_type"] = {t: term(r, t) for t in r["terms"] if t.endswith(("week", "30"))}
    return out


def main():
    res = {"note": __doc__.split("Output:")[0].strip(),
           "registry_only": run("v1"), "full": run("v2"), "one_to_one": run("v2", "one_to_one")}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "note"}, indent=1))


if __name__ == "__main__":
    main()
