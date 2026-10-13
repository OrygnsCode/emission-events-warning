"""Phase 5 exposure series (per plant and day), each built by a written rule (plan 5.2, D4 item 2, D6 item 2, D7, D9).

pounds_by_occurrence(): pounds released per occurrence in the four severity families (SO2, H2S, NOx, CO), D6 item 2:
    contaminant rows in pounds only; 0.0001 read as zero; NOx parts (nitrogen dioxide, nitric oxide) left out where a
    total NOx row exists for the same emission point (D7); an occurrence (a kept report and its same-start duplicates)
    sums the rows of all its reports, counting a row that repeats exactly (same emission point, pollutant and
    amount) once (D9). Also the VOC measure of D6 item 2 (reported separately): the larger of total-VOC rows and the
    sum of single hydrocarbon rows is not defined here (single hydrocarbons have no frozen name list), so VOC is the
    total-VOC rows only, and is labelled so.
recurrence_flags(): an occurrence is a recurrence when another unplanned event report at the same RN names the same
    emission point (EPN, upper case, letters and digits only) and started in the 30 days before it (D9).
cause_groups(): D4 item 2 groups of the frozen primary cause: process control, outside or planned, unknown.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vchecks_common as vc  # noqa: E402

DER = vc.DER
NOX_TOTAL = (r"^(NITROGEN OXIDES?|NOX|OXIDES OF NITROGEN|NITROGEN OXIDES \(NOX\)|OXIDES OF NITROGEN \(NOX\)"
             r"|NOX \(STARTUP/SHUTDOWN\))$")
PROCESS = {"equipment", "instrument", "upset", "operator"}
OUTSIDE = {"weather", "third_party", "power", "maintenance_startup"}


def norm_epn(s):
    return s.fillna("").astype(str).str.upper().map(lambda x: re.sub(r"[^A-Z0-9]", "", x))


def occurrence_of(ev):
    """incident -> kept incident of its same-start occurrence."""
    return pd.Series(np.where(ev.is_duplicate, ev.dup_of, ev.incident).astype(int), index=ev.incident.values)


def pounds_by_occurrence(ev):
    occ = occurrence_of(ev)
    c = pd.read_csv(DER / "contaminants.csv.gz", usecols=["incident", "epn", "description", "quantity", "units"],
                    low_memory=False)
    c = c[c.units.eq("POUNDS") & c.incident.isin(occ.index)].copy()
    up = c.description.str.upper().str.strip()
    c["fam"] = None
    for f in ["so2", "h2s", "nox", "co"]:
        c.loc[up.str.contains(vc.CONTAM[f], regex=True, na=False) & c.fam.isna(), "fam"] = f
    c["voc"] = up.str.contains(vc.CONTAM["voc"], regex=True, na=False)
    c["q"] = c.quantity.where(~np.isclose(c.quantity, 0.0001, rtol=0, atol=1e-10), 0.0).fillna(0.0)
    c["occ"] = c.incident.map(occ)
    c["ep"] = norm_epn(c.epn)
    c["desc"] = up
    log = {"pound_rows": len(c)}
    # rows repeated exactly within an occurrence count once
    c = c.drop_duplicates(["occ", "ep", "desc", "q"])
    log["after_exact_repeats_within_occurrence"] = len(c)
    # NOx parts dropped where a total NOx row exists for the same emission point of the occurrence
    tot = c.fam.eq("nox") & c.desc.str.contains(NOX_TOTAL, regex=True, na=False)
    part = c.fam.eq("nox") & ~tot
    key = c.occ.astype(str) + "|" + c.ep
    drop = part & key.isin(set(key[tot]))
    log["nox_part_rows_dropped"] = int(drop.sum())
    c = c[~drop]
    four = c[c.fam.notna()].groupby("occ").q.sum()
    voc = c[c.voc].groupby("occ").q.sum()
    return four, voc, log


def recurrence_flags(ev, exclude):
    """Series kept incident -> 1 if the occurrence repeats an emission point used at the same RN within 30 days."""
    e = ev[ev.event_type.eq("EMISSIONS EVENT") & ev.date_source.ne("none") & ~ev.incident.isin(exclude)]
    ep = pd.read_csv(DER / "emission_points.csv.gz", usecols=["incident", "epn"])
    ep["ep"] = norm_epn(ep.epn)
    ep = ep[ep.ep.ne("")].drop_duplicates(["incident", "ep"])
    x = ep.merge(e[["incident", "rn", "event_datetime", "is_duplicate", "dup_of"]], on="incident")
    x["occ"] = np.where(x.is_duplicate, x.dup_of, x.incident).astype(int)
    x = x.sort_values("event_datetime")
    flagged = set()
    for (rn, p), g in x.groupby(["rn", "ep"], sort=False):
        if len(g) < 2:
            continue
        t = g.event_datetime.values
        occ = g.occ.values
        for i in range(1, len(g)):
            # an earlier report at this point, of another occurrence, within the 30 days before
            j = i - 1
            while j >= 0 and (t[i] - t[j]) <= np.timedelta64(30, "D"):
                if occ[j] != occ[i] and t[j] < t[i]:
                    flagged.add(occ[i])
                    break
                j -= 1
    kept = e.loc[~e.is_duplicate, "incident"]
    return pd.Series(kept.isin(flagged).astype(float).values, index=kept.values), {"recurrent_occurrences": len(flagged)}


def kept_indicator(ev, flag):
    """Weight series (by incident) that is 1 for the kept report of an occurrence when flag is true, else 0, so that
    a weighted count counts occurrences, not reports (an occurrence takes the category of its kept report)."""
    f = pd.Series(np.asarray(flag, dtype=bool), index=ev.incident.values)
    return (f & ~pd.Series(ev.is_duplicate.values, index=ev.incident.values)).astype(float)


def cause_groups(ev):
    c = pd.read_csv(DER / "causes.csv.gz", usecols=["incident", "primary_cause"]).set_index("incident").primary_cause
    pc = c.reindex(ev.incident.values)
    g = np.where(pc.isin(PROCESS), "process", np.where(pc.isin(OUTSIDE), "outside", "unknown"))
    return pd.Series(g, index=ev.incident.values)
