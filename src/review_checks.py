"""Numbers added in the second version of the paper (November 2026), after an outside review. Each is computed from
the stored results or the tables:
  zero_count_days        share of days in the primary panel whose 90-day window holds no unplanned event
  multiverse_by_choice   median rate ratio of the 1,152 variants for each value of each choice, and the variants at
                         the main settings by plant links
  planned_widened        planned-work intervals widened to match the spread of the shuffle test
                         (phase5_diag_planned_perm.json)
  corrected_estimates    the corrected main estimate and the four checks with other records, side by side
Output: data/manifests/review_checks.json
"""
import csv
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase5_h1 as P  # noqa: E402

M = P.h1.ROOT / "data" / "manifests"
OUT = M / "review_checks.json"
Z95, Z90 = 1.959964, 1.644854


def load(name):
    return json.loads((M / name).read_text())


def ci(rr, se, z=Z95):
    return [round(math.exp(math.log(rr) - z * se), 3), round(math.exp(math.log(rr) + z * se), 3)]


def se_from_ci(lo, hi):
    return (math.log(hi) - math.log(lo)) / (2 * Z95)


def main():
    res = {"note": __doc__.split("Output:")[0].strip()}

    # days with no event in the window (primary panel, as in the main test)
    pan = P.h1_run(keep_panel=True)["panel"]
    res["zero_count_days"] = {"panel_days": int(len(pan)), "accident_days": int(pan.y.sum()),
                              "share_with_no_event": round(float((pan.E_x == 0).mean()), 3),
                              "share_of_accident_days_with_no_event": round(float((pan.loc[pan.y > 0, "E_x"] == 0).mean()), 3)}
    print(res["zero_count_days"], flush=True)

    # multiverse medians by choice
    rows = list(csv.DictReader(open(M / "phase5_multiverse.csv")))
    by = {}
    for key in ("end", "gap", "window", "events", "linking", "doubles"):
        vals = {}
        for r in rows:
            vals.setdefault(r[key], []).append(float(r["rr"]))
        by[key] = {k: round(statistics.median(v), 3) for k, v in sorted(vals.items())}
    main_set = [r for r in rows if r["end"] == "2021" and r["gap"] == "7" and r["window"] == "90"
                and r["events"] == "unplanned" and r["doubles"] == "merged"]
    res["multiverse_by_choice"] = {
        "variants": len(rows), "median_by_choice": by,
        "main_settings_by_linking": {r["linking"]: {"rr": round(float(r["rr"]), 3), "accidents": int(r["n_accidents"]),
                                                    "plants": int(r["n_plants"])} for r in main_set}}
    print(res["multiverse_by_choice"]["main_settings_by_linking"], flush=True)

    # planned work: widen the model intervals by the spread of the shuffle test
    perm = load("phase5_diag_planned_perm.json")
    lo, hi = perm["null_p5_p95_rr"]
    sd_shuffle = (math.log(hi) - math.log(lo)) / (2 * Z90)
    base = load("phase5_diag_planned.json")["base_2021"]["planned"]
    yes_no = load("phase5_diag_planned_extra.json")["yes_no"]
    se_base = se_from_ci(*base["ci"])
    factor = sd_shuffle / se_base
    res["planned_widened"] = {
        "shuffle_sd_log_rr": round(sd_shuffle, 4), "model_se_log_rr": round(se_base, 4), "factor": round(factor, 3),
        "per_doubling": {"rr": base["rr"], "model_ci": base["ci"], "widened_ci": ci(base["rr"], sd_shuffle)},
        "yes_no_same_factor": {"rr": yes_no["rr"], "model_ci": yes_no["ci"],
                               "widened_ci": ci(yes_no["rr"], se_from_ci(*yes_no["ci"]) * factor)}}
    print(res["planned_widened"], flush=True)

    # corrected estimates side by side
    own = load("phase5_diag_own_reports.json")["remove_0_to_2"]["window_90"]
    h4 = load("phase5_h4_o6.json")
    chem = load("phase5_same_chemical.json")["own_reports_removed"]
    sat = load("phase5_satellite_heat.json")["own_detections_removed"]
    res["corrected_estimates"] = {
        "rmp_main": {"rr": own["rr"], "ci": own["ci"]},
        "national_response_center": {"rr": h4["H4_end_2021_own_reports_removed"]["rr"], "ci": h4["H4_end_2021_own_reports_removed"]["ci"]},
        "osha": {"rr": h4["O6_end_2021_own_reports_removed"]["rr"], "ci": h4["O6_end_2021_own_reports_removed"]["ci"]},
        "plant_own_chemicals": {"rr": chem["rr"], "ci": chem["ci"]},
        "satellite_heat": {"rr": sat["rr"], "ci": sat["ci"]}}

    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print("written", OUT)


if __name__ == "__main__":
    main()
