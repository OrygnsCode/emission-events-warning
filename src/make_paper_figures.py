"""Figures for the paper (figures/). Every value is read from data/manifests/.

Figure 1: unplanned events month by month around accidents, against random days in the same plant-years
          (h1_primary_result.json, picture).
Figure 2: the main test by window length, as registered and with the accident's own reports removed
          (phase5_family.json, h1_primary_result.json, phase5_diag_own_reports.json).
Figure 3: the time-scale check, as registered and with the accident's own reports removed
          (phase5_diag_era.json, phase5_diag_era_own_removed.json).
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
M = ROOT / "data" / "manifests"
OUT = ROOT / "figures"
plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "pdf.fonttype": 42})
DARK, MID, LIGHT = "#1f3a5f", "#c0504d", "#9aa5b1"


def load(name):
    return json.loads((M / name).read_text())


def fig1():
    p = load("h1_primary_result.json")["primary_end_2021"]["picture"]
    # bin b covers days round(30.44 b) to round(30.44 (b + 1)) - 1 after the accident, so it is drawn at b + 0.5
    x = [b + 0.5 for b in p["month_offset"]]
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    ax.axvspan(-97 / 30.44, -8 / 30.44, color="#e8edf3", lw=0)
    ax.text(-1.72, 2.02, "main test\nwindow", ha="center", va="top", fontsize=7.5, color="#555555")
    ax.plot(x, p["random_dates_ratio_to_plant_average"], color=LIGHT, lw=1.6, label="Random days, same plant-years")
    ax.plot(x, p["accident_ratio_to_plant_average"], color=DARK, lw=1.6, marker="o", ms=2.6, label="Accident days")
    ax.axvline(0, color="#888888", lw=0.6, ls=":")
    ax.set_xlabel("Months from the accident day (or the random day)")
    ax.set_ylabel("Events relative to\nthe plant's average")
    ax.set_xlim(-24.2, 13.2)
    ax.set_ylim(0.8, 2.05)
    ax.set_xticks(range(-24, 13, 3))
    ax.legend(frameon=False, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig1_event_rate.pdf")
    plt.close(fig)


def fig2():
    fam = load("phase5_family.json")["results"]
    prim = load("h1_primary_result.json")["primary_end_2021"]["pyfixest"]
    own = load("phase5_diag_own_reports.json")["remove_0_to_2"]
    w = [30, 90, 180, 365]
    reg = [(fam["window_30"]["x"]["rr"], *fam["window_30"]["x"]["ci"]),
           (prim["rr_doubling"], prim["ci_low"], prim["ci_high"]),
           (fam["window_180"]["x"]["rr"], *fam["window_180"]["x"]["ci"]),
           (fam["window_365"]["x"]["rr"], *fam["window_365"]["x"]["ci"])]
    cor = [(own[f"window_{v}"]["rr"], *own[f"window_{v}"]["ci"]) for v in w]
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    pos = range(len(w))
    for k, (vals, col, lab, dx, mk) in enumerate([(reg, MID, "As registered", -0.09, "s"),
                                                 (cor, DARK, "Accident's own reports removed", 0.09, "o")]):
        xs = [i + dx for i in pos]
        ax.errorbar(xs, [v[0] for v in vals], yerr=[[v[0] - v[1] for v in vals], [v[2] - v[0] for v in vals]],
                    fmt=mk, color=col, ms=4.5, capsize=2.5, lw=1.1, label=lab)
    ax.axhline(1, color="#888888", lw=0.7)
    ax.set_xticks(list(pos))
    ax.set_xticklabels([f"{v} days" for v in w])
    ax.set_xlabel("Length of the look-back window")
    ax.set_ylabel("Rate ratio per doubling\nof recent events")
    ax.set_yscale("log")
    ax.set_yticks([0.4, 0.5, 0.6, 0.8, 1.0, 1.25, 1.5])
    ax.set_yticklabels(["0.4", "0.5", "0.6", "0.8", "1.0", "1.25", "1.5"])
    ax.minorticks_off()
    ax.legend(frameon=False, loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig2_window_length.pdf")
    plt.close(fig)


def fig3():
    reg = load("phase5_diag_era.json")
    path = M / "phase5_diag_era_own_removed.json"
    cor = json.loads(path.read_text()) if path.exists() else None
    keys = ["plant_only_R12", "plant_x_5yr", "plant_x_3yr", "plant_x_2yr", "plant_year_primary"]
    labels = ["Whole\nhistory", "Same\n5 years", "Same\n3 years", "Same\n2 years", "Same\nyear"]
    fig, ax = plt.subplots(figsize=(6.2, 2.8))
    series = [(reg, MID, "As registered", -0.09, "s")]
    if cor is not None and all(k in cor for k in keys):
        series.append((cor, DARK, "Accident's own reports removed", 0.09, "o"))
    for d, col, lab, dx, mk in series:
        xs = [i + dx for i in range(len(keys))]
        r = [d[k]["rr"] for k in keys]
        lo = [d[k]["rr"] - d[k]["ci"][0] for k in keys]
        hi = [d[k]["ci"][1] - d[k]["rr"] for k in keys]
        ax.errorbar(xs, r, yerr=[lo, hi], fmt=mk, color=col, ms=4.5, capsize=2.5, lw=1.1, label=lab)
    ax.axhline(1, color="#888888", lw=0.7)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(labels)
    ax.set_xlabel("Each accident day is compared with the same plant's days in its ...")
    ax.set_ylabel("Rate ratio per doubling\nof recent events")
    ax.set_yscale("log")
    ax.set_yticks([0.8, 1.0, 1.25, 1.5, 1.75])
    ax.set_yticklabels(["0.8", "1.0", "1.25", "1.5", "1.75"])
    ax.minorticks_off()
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_time_scale.pdf")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fig1()
    fig2()
    fig3()
    print("figures written to", OUT)
