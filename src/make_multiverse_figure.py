"""Figure for plan D2 item 9: all 1,152 multiverse estimates in one picture, sorted, with 95% ranges, coloured by
window length; the primary specification is marked. Also writes the summary table used in docs/phase5_results.md.
Input: data/manifests/phase5_multiverse.csv. Output: docs/figures/multiverse.png and docs/figures/multiverse_summary.csv
"""
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
d = pd.read_csv(ROOT / "data/manifests/phase5_multiverse.csv").sort_values("rr").reset_index(drop=True)
assert len(d) == 1152 and d.rr.notna().all()
COL = {30: "#0072B2", 90: "#009E73", 180: "#E69F00", 365: "#CC79A7"}   # Okabe-Ito, colour-blind safe
prim = d.index[(d.end == 2021) & (d.gap == 7) & (d.window == 90) & (d.events == "unplanned") & (d.linking == "full")
               & (d.doubles == "merged")][0]

fig, ax = plt.subplots(figsize=(11, 5.2), dpi=150)
x = np.arange(len(d))
for w, c in COL.items():
    m = d.window.eq(w).values
    ax.vlines(x[m], d.ci_low[m], d.ci_high[m], color=c, alpha=0.25, lw=0.6)
    ax.plot(x[m], d.rr[m], "o", ms=2.2, color=c, label=f"{w}-day window (median {d.rr[m].median():.2f})")
ax.axhline(1, color="#333", lw=0.9)
ax.annotate("primary result (0.88)", xy=(prim, d.rr[prim]), xytext=(prim - 330, 1.75),
            arrowprops=dict(arrowstyle="->", color="#333", lw=0.8), fontsize=9)
ax.plot(prim, d.rr[prim], "D", ms=6, mfc="none", mec="#111", mew=1.2)
ax.set_yscale("log")
ticks = [0.25, 0.35, 0.5, 0.7, 1, 1.4, 2]
ax.set_yticks(ticks)
ax.set_yticklabels([str(t) for t in ticks])
ax.minorticks_off()
ax.set_ylim(0.2, 2.2)
ax.set_xlim(-10, len(d) + 10)
ax.set_xlabel("The 1,152 versions, sorted by estimate")
ax.set_ylabel("Accident rate ratio per doubling of events (log scale)")
ax.set_title("All 1,152 versions of the main test: the longer the window, the lower the estimate", fontsize=11, loc="left")
ax.text(0.01, 0.97, "Above 1 would mean more events before accidents. Lines are 95% ranges.",
        transform=ax.transAxes, fontsize=8.5, va="top", color="#444")
ax.legend(loc="lower right", fontsize=8.5, frameon=False)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(ROOT / "docs/figures/multiverse.png")

sig_pos = (d.p < 0.05) & (d.rr > 1)
sig_neg = (d.p < 0.05) & (d.rr < 1)
rows = []
for col in ("window", "gap", "events", "linking", "end", "doubles"):
    for v, g in d.groupby(col):
        rows.append({"choice": col, "value": v, "fits": len(g), "median_rr": round(g.rr.median(), 3),
                     "share_above_1": round((g.rr > 1).mean(), 3), "share_sig_above_1": round(sig_pos[g.index].mean(), 3),
                     "share_sig_below_1": round(sig_neg[g.index].mean(), 3)})
rows.append({"choice": "all", "value": "all", "fits": len(d), "median_rr": round(d.rr.median(), 3),
             "share_above_1": round((d.rr > 1).mean(), 3), "share_sig_above_1": round(sig_pos.mean(), 3),
             "share_sig_below_1": round(sig_neg.mean(), 3)})
pd.DataFrame(rows).to_csv(ROOT / "docs/figures/multiverse_summary.csv", index=False)
print(pd.DataFrame(rows).to_string(index=False))
print("primary row:", d.loc[prim, ["rr", "ci_low", "ci_high", "p"]].round(4).to_dict())
