"""Check V5 (plan D6 item 11): emissions inventory event tons against the event database, by site-year.

Unit: RN-year, 2016 to 2021, for RNs in both sources (an inventory row in some year and a D6 event in some year): every
year the RN has an inventory row (plan D7; event years without an inventory row are counted separately).
NOx parts (nitrogen dioxide, nitric oxide) are left out where a total NOx row exists for the same incident and
emission point (events) or RN-year (inventory), so NOx is not counted twice (plan D7).
95% intervals: 2,000 bootstrap resamples of RNs.
For the four severity families (SO2, H2S, NOx, CO; the same frozen name lists for both sources), inventory EE tons
are compared with the sum of reported event pounds / 2,000 over the RN's D6 emissions events starting that year
(0.0001 read as zero). Measures: Spearman correlation of site-year totals, median ratio, share within a factor of 2;
counts of site-years with tons in only one source. Also by family.

Output: data/derived/vchecks/v5_result.json (copied to data/manifests/)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vchecks_common as vc  # noqa: E402

FAM4 = ["so2", "h2s", "nox", "co"]
NOX_TOTAL = (r"^(NITROGEN OXIDES?|NOX|OXIDES OF NITROGEN|NITROGEN OXIDES \(NOX\)|OXIDES OF NITROGEN \(NOX\)"
             r"|NOX \(STARTUP/SHUTDOWN\))$")


def drop_nox_parts(df, name_col, key_cols):
    """Rows of NOx parts are dropped where the same key also has a total NOx row."""
    up = df[name_col].str.upper().str.strip()
    tot = df.fam.eq("nox") & up.str.contains(NOX_TOTAL, regex=True, na=False)
    part = df.fam.eq("nox") & ~tot
    k = df[key_cols[0]].astype(str)
    for col in key_cols[1:]:
        k = k + "|" + df[col].fillna("").astype(str)
    drop = part & k.isin(set(k[tot]))
    return df[~drop], int(drop.sum())


def family_of(names):
    out = pd.Series(None, index=names.index, dtype=object)
    up = names.str.upper().str.strip()
    for f in FAM4:
        out[up.str.contains(vc.CONTAM[f], regex=True, na=False) & out.isna()] = f
    return out


def boot(t, B=2000):
    """95% intervals for the Spearman correlation and the median ratio, resampling RNs."""
    rng = np.random.default_rng(1)
    t = t.reset_index(drop=True)
    inv, evt = t.inv.values, t.evt.values
    groups = list(t.groupby("rn").indices.values())
    rho, med = [], []
    for _ in range(B):
        ix = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        a, b = inv[ix], evt[ix]
        rho.append(spearmanr(a, b)[0])
        m = (a > 0) & (b > 0)
        med.append(np.median(b[m] / a[m]) if m.any() else np.nan)
    q = lambda v: [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]  # noqa: E731
    return {"spearman_all_ci95": q(rho), "median_ratio_ci95": q(med)}


def summarize(t):
    both = t[(t.inv > 0) & (t.evt > 0)]
    r = both.evt / both.inv
    rho = spearmanr(t.inv, t.evt) if len(t) > 2 else (np.nan, np.nan)
    return {"site_years": len(t), "both_positive": len(both),
            "inventory_only": int(((t.inv > 0) & (t.evt <= 0)).sum()),
            "events_only": int(((t.inv <= 0) & (t.evt > 0)).sum()),
            "neither": int(((t.inv <= 0) & (t.evt <= 0)).sum()),
            "spearman_all": round(float(rho[0]), 3),
            "spearman_both_positive": round(float(spearmanr(both.inv, both.evt)[0]), 3) if len(both) > 2 else None,
            "median_ratio_events_to_inventory": round(float(r.median()), 3) if len(r) else None,
            "ratio_iqr": [round(float(r.quantile(.25)), 3), round(float(r.quantile(.75)), 3)] if len(r) else None,
            "share_within_factor_2": round(float(((r >= .5) & (r <= 2)).mean()), 3) if len(r) else None,
            "inventory_tons": round(float(t.inv.sum()), 1), "event_tons": round(float(t.evt.sum()), 1),
            **(boot(t) if len(t) > 2 else {})}


def main():
    e = pd.read_pickle(vc.OUT / "events.pkl")
    e = e[e.start_utc.dt.year.between(2016, 2021)]
    c = pd.read_csv(vc.DER / "contaminants.csv.gz", usecols=["incident", "epn", "description", "quantity", "units"])
    c = c[c.incident.isin(e.incident) & c.units.eq("POUNDS")].copy()
    c["fam"] = family_of(c.description)
    c = c.dropna(subset=["fam"])
    c, n_ev_parts = drop_nox_parts(c, "description", ["incident", "epn"])
    c["q"] = c.quantity.where(~np.isclose(c.quantity, 0.0001, rtol=0, atol=1e-10), 0.0)
    c = c.merge(e[["incident", "rn"]].assign(year=e.start_utc.dt.year.values), on="incident")
    ev = c.groupby(["rn", "year", "fam"]).q.sum().div(2000).rename("evt")

    p = pd.concat([pd.read_parquet(vc.DER / "psei_cache" / f"{y}.parquet") for y in range(2016, 2022)])
    p["fam"] = family_of(p["CONTAMINANT NAME"])
    inv_sites = p.groupby(["RN", "YEAR"]).size().index
    pq, n_inv_parts = drop_nox_parts(p.dropna(subset=["fam"]), "CONTAMINANT NAME", ["RN", "YEAR"])
    pf = pq.groupby(["RN", "YEAR", "fam"]).ee_tpy.sum().rename("inv")
    pf.index = pf.index.set_names(["rn", "year", "fam"])

    ev_sites = set(zip(e.rn, e.start_utc.dt.year))
    inv_keys = set(zip(inv_sites.get_level_values(0), inv_sites.get_level_values(1)))
    both_rns = {r for r, _ in inv_keys} & {r for r, _ in ev_sites}
    keys = sorted(k for k in inv_keys if k[0] in both_rns)
    idx = pd.MultiIndex.from_tuples([(r, y, f) for r, y in keys for f in FAM4], names=["rn", "year", "fam"])
    t = pd.concat([pf.reindex(idx), ev.reindex(idx)], axis=1).fillna(0.0).reset_index()
    out = {"rule": "plan D6 item 11", "site_years_in_both_sources": len(keys),
           "rns": len({k[0] for k in keys}),
           "d6_event_site_years_2016_2021": len(ev_sites),
           "event_site_years_without_inventory_record": len(ev_sites - inv_keys),
           "site_years_with_a_d6_event": len(set(keys) & ev_sites),
           "nox_part_rows_dropped": {"events": n_ev_parts, "inventory": n_inv_parts},
           "total_four_families": summarize(t.groupby(["rn", "year"])[["inv", "evt"]].sum().reset_index()),
           "by_family": {f: summarize(t[t.fam == f]) for f in FAM4}}
    (vc.OUT / "v5_result.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
