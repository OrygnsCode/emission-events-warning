"""Rebuild every result in data/manifests/ and every figure from the tables in data/, in order.

    python src/run_all.py                   everything (about 10 hours on a four-core laptop)
    python src/run_all.py --list            show the steps
    python src/run_all.py --only NAME,NAME  run some steps
    python src/run_all.py --skip NAME,NAME  run all but some steps

The steps follow the order the work was done in: the warning-sign checks and the power check (no accident data),
the registered main test (Phase 4), the rest of the registered analysis and the checks added after it (Phase 5,
each labelled in docs/analysis_plan.md), and the numbers and figures for the paper. Every result is written over its
stored copy, so `git diff data/manifests` afterwards shows anything that came out different.

Two checks need downloaded data that is too large for the repository: V1 (hourly air monitor and airport wind data)
and V4 (TCEQ complaints and Houston 311 requests). They are skipped, with a note, unless those files are present;
README.md ("Rebuild the tables") lists the scripts that download and prepare them. Everything else runs from the
tables in data/.
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DER = ROOT / "data" / "derived"
M = ROOT / "data" / "manifests"

# name, script, arguments
STEPS = [
    # warning-sign checks V1 to V5 (plan D6 and D7)
    ("vchecks_events", "vchecks_common.py", []),
    ("v1", "v1_monitors.py", []),
    ("v2", "v2_satellite.py", []),
    ("v2_clock_noon", "v2_satellite.py", ["--clock", "clock", "--night", "noon"]),
    ("v2_clock_evening", "v2_satellite.py", ["--clock", "clock", "--night", "evening"]),
    ("v2_solar_evening", "v2_satellite.py", ["--clock", "solar", "--night", "evening"]),
    ("v3", "v3_fenceline.py", []),
    ("v4", "v4_complaints.py", []),
    ("v4_drop", "v4_complaints.py", ["--running", "drop"]),
    ("v4_exposed", "v4_complaints.py", ["--running", "exposed"]),
    ("v5", "v5_inventory.py", []),
    # power check with fake accident dates (plan 6.5, D2), and the two dry runs of the main test
    ("power_v1", "power_h1.py", ["300", "v1"]),
    ("power_2021", "power_h1.py", ["300", "v2", "2021-12-31", "--before-d8"]),
    ("power_2023", "power_h1.py", ["300", "v2", "2023-12-31", "--before-d8"]),
    ("power_2021_null", "power_h1.py", ["2000", "v2", "2021-12-31", "1.0", "--before-d8"]),
    ("dry_run_1.0", "run_h1.py", ["--planted", "1.0", "--seed", "3", "--shuffles", "1000"]),
    ("dry_run_1.5", "run_h1.py", ["--planted", "1.5", "--seed", "0", "--shuffles", "1000"]),
    # Phase 4: the registered main test
    ("h1", "run_h1.py", ["--real"]),
    ("h1_third_fit", "h1_third_fit.py", []),
    # Phase 5: registered tests
    ("family", "phase5_family.py", []),
    ("robustness", "phase5_robust.py", []),
    ("robustness2", "phase5_robust2.py", []),
    ("negative_binomial", "phase5_negbin.py", []),
    ("other", "phase5_other.py", []),
    ("multiverse", "phase5_multiverse.py", []),
    ("h2_h3", "phase5_h2h3.py", []),
    ("h4_o6", "phase5_h4_o6.py", []),
    ("h4_overlap", "h4_overlap.py", []),
    ("completeness", "completeness_check.py", []),
    ("news_completeness", "news_completeness.py", []),
    ("cause_agreement", "cause_agreement.py", []),
    # Phase 5: checks added after results were seen (plan D9 to D16)
    ("post_accident", "phase5_diag_post.py", []),
    ("clean", "phase5_diag_clean.py", []),
    ("own_reports", "phase5_diag_own_reports.py", []),
    ("era", "phase5_diag_era.py", []),
    ("era_own_removed", "phase5_diag_era_own_removed.py", []),
    ("h2_aftermath", "phase5_diag_h2.py", []),
    ("last_week", "phase5_diag_lastweek.py", []),
    ("planned", "phase5_diag_planned.py", []),
    ("planned_chains", "phase5_diag_planned.py", ["--chains"]),
    ("planned_extra", "phase5_diag_planned_extra.py", []),
    ("planned_shuffle", "phase5_diag_planned_perm.py", []),
    ("planned_rmp", "phase5_diag_planned_rmp.py", []),
    ("same_chemical", "phase5_same_chemical.py", []),
    ("satellite_heat", "phase5_satellite_heat.py", []),
    ("registered_extra", "phase5_registered_extra.py", []),
    ("removal_calibration", "phase5_removal_calibration.py", []),
    ("stored_checks", "stored_checks.py", []),
    ("simulation", "sim_design_trap.py", []),
    ("louisiana_power", "t2_louisiana_power.py", []),
    ("planned_nrc", "t3_planned_nrc.py", []),
    ("equivalence", "equivalence_summary.py", []),
    # numbers and figures for the paper
    ("paper_facts", "paper_facts.py", []),
    ("paper_precision", "paper_precision.py", []),
    ("multiverse_figure", "make_multiverse_figure.py", []),
    ("paper_figures", "make_paper_figures.py", []),
]

# steps that need downloaded data not kept in the repository: run only when these paths exist
NEEDS = {
    "v1": ["data/derived/vchecks/hourly_so2.parquet", "data/external/iem_asos"],
    "v4": ["data/external/tceq_open_data/complaints_tdzs-qqjn.csv", "data/external/houston_311"],
    "v4_drop": ["data/external/tceq_open_data/complaints_tdzs-qqjn.csv", "data/external/houston_311"],
    "v4_exposed": ["data/external/tceq_open_data/complaints_tdzs-qqjn.csv", "data/external/houston_311"],
}

# results that the scripts write next to their inputs in data/derived/ and that are kept in data/manifests/
COPIES = {
    "vchecks_events": [("vchecks/event_set_log.json", "vchecks_event_set_log.json")],
    "v1": [("vchecks/v1_result.json", "v1_result.json")],
    "v2": [("vchecks/v2_result.json", "v2_result.json")],
    "v2_clock_noon": [("vchecks/v2_result_clock_noon.json", "v2_result_clock_noon.json")],
    "v2_clock_evening": [("vchecks/v2_result_clock_evening.json", "v2_result_clock_evening.json")],
    "v2_solar_evening": [("vchecks/v2_result_solar_evening.json", "v2_result_solar_evening.json")],
    "v3": [("vchecks/v3_result.json", "v3_result.json")],
    "v4": [("vchecks/v4_result.json", "v4_result.json")],
    "v4_drop": [("vchecks/v4_result_running_drop.json", "v4_result_running_drop.json")],
    "v4_exposed": [("vchecks/v4_result_running_exposed.json", "v4_result_running_exposed.json")],
    "v5": [("vchecks/v5_result.json", "v5_result.json")],
    "power_v1": [("power_h1.json", "power_h1.json")],
    "power_2021": [("power_h1_v2_2021-12-31.json", "power_h1_v2_2021-12-31.json")],
    "power_2023": [("power_h1_v2_2023-12-31.json", "power_h1_v2_2023-12-31.json")],
    "power_2021_null": [("power_h1_v2_2021-12-31_ratios_1.0.json", "power_h1_v2_2021-12-31_ratios_1.0.json")],
    "dry_run_1.0": [("h1_dryrun_1.0_seed3.json", "h1_dryrun_1.0_seed3.json")],
    "dry_run_1.5": [("h1_dryrun_1.5_seed0.json", "h1_dryrun_1.5_seed0.json")],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    a = ap.parse_args()
    names = [s[0] for s in STEPS]
    only = [x for x in a.only.split(",") if x]
    skip = [x for x in a.skip.split(",") if x]
    for x in only + skip:
        if x not in names:
            sys.exit(f"unknown step {x}; see --list")
    if a.list:
        for name, script, args in STEPS:
            print(f"{name:22s} src/{script} {' '.join(args)}")
        return
    steps = [s for s in STEPS if (not only or s[0] in only) and s[0] not in skip]
    t_all = time.time()
    skipped = []
    for name, script, args in steps:
        missing = [p for p in NEEDS.get(name, []) if not (ROOT / p).exists()]
        if missing:
            print(f"== {name}: skipped, needs the downloaded data ({', '.join(missing)})", flush=True)
            skipped.append(name)
            continue
        t0 = time.time()
        print(f"== {name}: src/{script} {' '.join(args)}", flush=True)
        r = subprocess.run([sys.executable, str(ROOT / "src" / script), *args], cwd=ROOT)
        if r.returncode != 0:
            sys.exit(f"step {name} failed (exit code {r.returncode})")
        for src, dest in COPIES.get(name, []):
            shutil.copyfile(DER / src, M / dest)
        print(f"== {name} done in {time.time() - t0:.0f} s", flush=True)
    print(f"{len(steps) - len(skipped)} steps done in {(time.time() - t_all) / 60:.0f} min")
    if skipped:
        print("skipped (downloaded data not present):", ", ".join(skipped))


if __name__ == "__main__":
    main()
