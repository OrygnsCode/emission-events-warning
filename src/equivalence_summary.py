"""Plan D14 items 1 and 5: one-sided bounds (two one-sided tests at the 5% level, that is the upper end of the 90%
interval) for the main result in its registered form, with the accident's own reports removed, and in the National
Response Center replication; and what the bound means against the observed accident rate. Where a manifest keeps only
the rate ratio and 95% range, the standard error is recovered from the range on the log scale.
Output: data/manifests/equivalence_summary.json
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
M = ROOT / "data" / "manifests"


def from_ci(rr, ci):
    b = math.log2(rr)
    se = (math.log2(ci[1]) - math.log2(ci[0])) / (2 * 1.959964)
    return b, se


def bound(b, se):
    return {"rr": round(2 ** b, 3), "upper_90": round(2 ** (b + 1.644854 * se), 3),
            "rises_rejected_above_pct": round((2 ** (b + 1.644854 * se) - 1) * 100, 1)}


def main():
    h = json.loads((M / "h1_primary_result.json").read_text())["primary_end_2021"]["pyfixest"]
    own = json.loads((M / "phase5_diag_own_reports.json").read_text())
    h4 = json.loads((M / "phase5_h4_o6.json").read_text())
    out = {"note": __doc__.split("Output:")[0].strip(),
           "registered_primary": bound(h["beta"], h["se"])}
    for k in ("remove_0_to_0", "remove_0_to_2", "remove_0_to_7"):
        x = own[k]["window_90"]
        out[f"own_reports_{k}"] = bound(*from_ci(x["rr"], x["ci"]))
    x = h4["H4_end_2021_own_reports_removed"]
    out["H4_nrc_own_reports_removed"] = bound(*from_ci(x["rr"], x["ci"]))
    rate = 33.32  # accidents per 1,000 plant-years, linked plants (phase5_h2h3.json)
    up = out["own_reports_remove_0_to_2"]["upper_90"]
    out["plain_numbers"] = {"accidents_per_1000_plant_years": rate,
                            "if_events_double_at_most": round(rate * up, 1),
                            "extra_per_1000_plant_years_at_most": round(rate * (up - 1), 1)}
    (M / "equivalence_summary.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "note"}, indent=1))


if __name__ == "__main__":
    main()
