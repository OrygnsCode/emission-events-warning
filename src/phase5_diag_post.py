"""Diagnostic added after the Phase 5 family results were seen (labelled as such in the plan, D9): do the negative
estimates come from the days after accidents? Each significant family item is refit dropping every plant-day that
falls within (longest window + gap) days after an accident at the same plant, so no comparison day's window can
contain an accident or its own reports. The pre-registered R16 does the same with 120 days for the primary window.
Output: data/manifests/phase5_diag_post_accident.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

OUT = P.h1.ROOT / "data" / "manifests" / "phase5_diag_post_accident.json"


def counts_only(pan, terms, fe, family):
    """Stands in for the fit when the model does not converge: the panel's counts, and no estimate."""
    nan = float("nan")
    return {"n_days": len(pan), "n_accidents": int(pan.y.sum()), "n_plants": int(pan.plant_id.nunique()),
            "terms": {t: {"rr_doubling": nan, "ci": [nan, nan], "p": nan} for t in terms}}


def run(days, kw):
    """h1_run; when the model does not converge (window_365 and lag_profile, where few days are left), the item is
    kept with its counts and an empty estimate."""
    try:
        return P.h1_run(post_excl=days, **kw)
    except (ValueError, RuntimeError):
        fit, P.fit = P.fit, counts_only
        try:
            return P.h1_run(post_excl=days, **kw)
        finally:
            P.fit = fit


def main():
    plants, ev, acc, acc_all, risk = P.tables("v2")
    cnt = P.event_counts(ev)
    lag = {"l0_3": (cnt, 84, 7), "l3_6": (cnt, 92, 91), "l6_12": (cnt, 182, 183), "l12_24": (cnt, 365, 365)}

    def topq(pan):
        q = pan.groupby("plant_id").E_x.transform(lambda v: v.quantile(0.75))
        pan["top"] = (pan.E_x > q).astype(float)
        return pan

    items = {
        "primary_90": (dict(), ["x"], 97),
        "O4_harm_outside_fence": (dict(outcome="O4"), ["x"], 97),
        "window_180": (dict(window=180), ["x"], 187),
        "window_365": (dict(window=365), ["x"], 372),
        "lag_profile": (dict(exposures=lag, statewide_each=True), list(lag), 730),
        "dose_top_quarter": (dict(extra_cols=topq, terms=["top", "xs"]), ["top"], 97),
    }
    out = {}
    for name, (kw, terms, days) in items.items():
        r = run(days, kw)
        out[name] = {"post_days_dropped": days, "n_accidents": r["n_accidents"], "n_plants": r["n_plants"],
                     "n_days": r["n_days"],
                     **{t: {"rr": round(r["terms"][t]["rr_doubling"], 4),
                            "ci": [round(c, 4) for c in r["terms"][t]["ci"]], "p": r["terms"][t]["p"]} for t in terms}}
        if name == "dose_top_quarter":
            # yes/no term: its rate ratio is exp(beta), not 2^beta (found in the model review, plan D10)
            b, se = r["terms"]["top"]["beta"], r["terms"]["top"]["se"]
            out[name]["top"]["rr_yes_vs_no"] = round(float(np.exp(b)), 4)
            out[name]["top"]["ci_yes_vs_no"] = [round(float(np.exp(b - 1.959964 * se)), 4),
                                                round(float(np.exp(b + 1.959964 * se)), 4)]
        print(name, {t: (out[name][t]["rr"], round(out[name][t]["p"], 4)) for t in terms}, "accidents", r["n_accidents"],
              flush=True)
    out["note_dose_scale"] = "top is a yes/no term: read rr_yes_vs_no (exp(beta)); rr is 2^beta (D10 addendum)."
    OUT.write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
