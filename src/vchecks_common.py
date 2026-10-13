"""Shared pieces of the warning-sign checks V1 to V5 (plan D6 items 6 to 11). No accident data is read here.

events():   the D6 event set (emissions events at plants with an RMP risk period, June 2003 to 2021, after the
            same-start merge; frozen duplicate and filed-in-error flags and NARROW_NON_EVENT hits dropped; reports
            later found below the reportable amount kept), with UTC start and end, RN location, county,
            pollutant families and a flare flag.
episodes(): reports at the same RN whose event hours overlap, merged into one episode.
Run as a script to write events.pkl, episodes.pkl and event_set_log.json to data/derived/vchecks.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from census_event_text import NARROW_NON_EVENT  # noqa: E402
from census_monitors import CONTAM_FAMILY  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DER = ROOT / "data" / "derived"
OUT = DER / "vchecks"
START, END = pd.Timestamp("2003-06-01"), pd.Timestamp("2021-12-31 23:59")
MOUNTAIN = {"EL PASO", "HUDSPETH"}   # D6 item 5: these counties keep Mountain time; all others Central
FAMILIES = ["so2", "h2s", "nox", "co", "benzene", "butadiene", "voc"]
CONTAM = dict(CONTAM_FAMILY, co=r"^(CARBON MONOXIDE|CO|CO \(STARTUP/SHUTDOWN\))$")
FLARE = re.compile(r"\bflar", re.I)


def km(lat1, lon1, lat2, lon2):
    x = np.radians(np.asarray(lon2) - lon1) * np.cos(np.radians((np.asarray(lat2) + lat1) / 2))
    return 6371.0 * np.hypot(x, np.radians(np.asarray(lat2) - lat1))


def bearing(lat1, lon1, lat2, lon2):
    """Compass bearing in degrees from point 1 to point 2."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - lon1)
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return (np.degrees(np.arctan2(y, x)) + 360) % 360


def to_utc(local, county):
    """Local clock time (with daylight saving) to naive UTC, by county time zone."""
    parts = []
    for tz, mask in (("America/Denver", county.isin(MOUNTAIN)), ("America/Chicago", ~county.isin(MOUNTAIN))):
        s = local[mask]
        if len(s):
            loc = s.dt.tz_localize(tz, ambiguous=np.ones(len(s), dtype=bool), nonexistent="shift_forward")
            parts.append(loc.dt.tz_convert("UTC").dt.tz_localize(None))
    return pd.concat(parts).reindex(local.index)


def rn_points():
    p = pd.read_parquet(DER / "tceq_rn_points_raw.parquet")
    p = p[p.lat.between(25.5, 36.6) & p.lon.between(-106.7, -93.4)]
    return p.groupby("rn")[["lat", "lon"]].median()


def events(include_text=False):
    ev = pd.read_csv(DER / "events_v2.csv.gz", parse_dates=["event_datetime"])
    risk = set(pd.read_csv(DER / "plant_risk_v2.csv").plant_id)
    e = ev[ev.event_type.eq("EMISSIONS EVENT") & ev.plant_id.isin(risk) & ~ev.is_duplicate
           & ev.event_datetime.between(START, END)].copy()
    st = pd.read_csv(DER / "causes.csv.gz", usecols=["incident", "status_duplicate", "status_filed_in_error"])
    e = e.merge(st, on="incident", how="left")
    d = pd.read_parquet(DER / "details_table.parquet",
                        columns=["incident", "county", "start_text", "end_text", "cause", "actions_taken", "basis"])
    d["incident"] = d.incident.astype(int)
    e = e.merge(d, on="incident", how="left")
    text = (e.cause.fillna("") + " | " + e.actions_taken.fillna("") + " | " + e.basis.fillna("")).str.upper()
    non_event = pd.Series(False, index=e.index)
    for pat in NARROW_NON_EVENT.values():
        non_event |= text.str.contains(pat, flags=re.I, regex=True)
    n0 = len(e)
    drop = e.status_duplicate.fillna(False) | e.status_filed_in_error.fillna(False) | non_event
    log = {"after_same_start_merge": n0, "frozen_duplicate": int(e.status_duplicate.fillna(False).sum()),
           "frozen_filed_in_error": int(e.status_filed_in_error.fillna(False).sum()),
           "narrow_non_event": int(non_event.sum()), "dropped_any": int(drop.sum())}
    e, text = e[~drop].copy(), text[~drop]
    e["county"] = e.county.fillna("").str.upper().str.strip()
    s_loc = pd.to_datetime(e.start_text, format="%m/%d/%Y %I:%M %p", errors="coerce")
    e_loc = pd.to_datetime(e.end_text, format="%m/%d/%Y %I:%M %p", errors="coerce")
    log["end_after_2030_set_missing"] = int((e_loc > pd.Timestamp("2030-12-31")).sum())  # typing errors (one says 3000)
    e_loc = e_loc.where(e_loc <= pd.Timestamp("2030-12-31"))
    e["start_utc"] = to_utc(s_loc, e.county)
    e["end_utc"] = to_utc(e_loc, e.county)
    e["start_local"] = s_loc
    e = e.join(rn_points(), on="rn")
    # pollutant families reported, and the flare flag (cause, actions or emission point names)
    c = pd.read_csv(DER / "contaminants.csv.gz", usecols=["incident", "description"])
    c = c[c.incident.isin(e.incident)]
    desc = c.description.str.upper().str.strip()
    for f, pat in CONTAM.items():
        e[f"fam_{f}"] = e.incident.isin(set(c.incident[desc.str.contains(pat, regex=True, na=False)]))
    ep = pd.read_csv(DER / "emission_points.csv.gz", usecols=["incident", "epn", "name"])
    ep_flare = set(ep.incident[(ep.epn.fillna("") + " " + ep.name.fillna("")).str.contains(FLARE)])
    # D6 item 8 names cause, actions and emission point names (not the basis field)
    ca = (e.cause.fillna("") + " | " + e.actions_taken.fillna(""))
    e["flare"] = ca.str.contains(FLARE).values | e.incident.isin(ep_flare)
    log.update({"kept": len(e), "with_location": int(e.lat.notna().sum()),
                "with_valid_start": int(e.start_utc.notna().sum()),
                "with_valid_end_after_start": int((e.end_utc >= e.start_utc).sum())})
    if not include_text:
        e = e.drop(columns=["cause", "actions_taken", "basis"])
    return e, log


def episodes(e):
    """Merge reports at the same RN whose [start, end] overlap. Reports without a valid end form their own episode
    with end = start (they can still mark an episode day; V1 leaves them out)."""
    x = e.dropna(subset=["start_utc"]).copy()
    x["valid_end"] = x.end_utc.notna() & (x.end_utc >= x.start_utc)
    x["end2"] = x.end_utc.where(x.valid_end, x.start_utc)
    x = x.sort_values(["rn", "start_utc"])
    fam_cols = [c for c in x.columns if c.startswith("fam_")]
    rows = []
    for rn, g in x.groupby("rn", sort=False):
        cur = None
        for r in g.itertuples(index=False):
            if cur is not None and r.start_utc <= cur["end_utc"]:
                cur["end_utc"] = max(cur["end_utc"], r.end2)
                cur["incidents"].append(r.incident)
                cur["valid_end"] &= r.valid_end
                cur["flare"] |= r.flare
                for f in fam_cols:
                    cur[f] |= getattr(r, f)
            else:
                if cur is not None:
                    rows.append(cur)
                cur = {"rn": rn, "plant_id": r.plant_id, "county": r.county, "lat": r.lat, "lon": r.lon,
                       "start_utc": r.start_utc, "end_utc": r.end2, "start_local": r.start_local,
                       "incidents": [r.incident], "valid_end": r.valid_end, "flare": r.flare,
                       **{f: getattr(r, f) for f in fam_cols}}
        rows.append(cur)
    out = pd.DataFrame(rows)
    out["n_reports"] = out.incidents.str.len()
    return out


def main():
    """Write the D6 event set and episodes used by V1 to V5: data/derived/vchecks/events.pkl, episodes.pkl and
    event_set_log.json."""
    import json
    OUT.mkdir(parents=True, exist_ok=True)
    e, log = events()
    ep = episodes(e)
    log["episodes"] = len(ep)
    e.to_pickle(OUT / "events.pkl")
    ep.to_pickle(OUT / "episodes.pkl")
    (OUT / "event_set_log.json").write_text(json.dumps(log, indent=1) + "\n")
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
