"""Parse one TCEQ emission event incident detail page into a dict.

Every labelled value on the page is kept. Labels we do not recognise go into
`extra` instead of being dropped, and `warnings` lists anything that looks off
(for example, fewer contaminant rows than the page says it has).
"""
import re

from bs4 import BeautifulSoup

KNOWN = {
    "incident tracking number": "incident",
    "incident status": "incident_status",
    "report type": "report_type",
    "report date": "report_date",
    "name of owner or operator": "owner_operator",
    "cn": "cn",
    "regulated entity name": "regulated_entity_name",
    "rn": "rn",
    "physical location": "physical_location",
    "county": "county",
    "event/activity type": "event_type",
    "date and time event discovered or scheduled activity start": "start_text",
    "date and time event or scheduled activity ended": "end_text",
    "event duration": "duration_text",
    "initial notification date/time": "initial_notification",
    "method": "notification_method",
    "notification jurisdictions": "notification_jurisdictions",
    "publication status": "publication_status",
}
COMMENT_KEYS = {
    "cause of emission event": "cause",
    "actions taken": "actions_taken",
    "basis used to determine quantities": "basis",
}
REQUIRED = ["incident", "report_type", "report_date", "rn", "event_type", "start_text"]


def clean(node):
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def to_float(s):
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    out = {"extra": {}, "process_units": [], "facilities": [], "emission_points": [], "warnings": []}

    for table in soup.find_all("table", class_="aeme"):
        summary = (table.get("summary") or "").strip()
        low = summary.lower()
        rows = table.find_all("tr")

        if low == "process area or unit list":
            out["process_units"] = [clean(td) for r in rows for td in r.find_all("td")]

        elif low == "facility list section":
            for r in rows:
                tds = r.find_all("td")
                if len(tds) >= 2:
                    out["facilities"].append({"name": clean(tds[0]), "fin": clean(tds[1])})
                elif len(tds) == 1:
                    out["facilities"].append({"name": clean(tds[0]), "fin": ""})

        elif low.startswith("emission point"):
            out["emission_points"].append(parse_emission_point(table, summary, out["warnings"]))

        elif low == "displays comment section":
            label = None
            for r in rows:
                th, td = r.find("th"), r.find("td")
                if th is not None and td is None:
                    label = clean(th)
                elif td is not None and label is not None:
                    key = next((v for k, v in COMMENT_KEYS.items() if label.lower().startswith(k)), None)
                    if key:
                        out[key] = clean(td)
                    else:
                        out["extra"][label.rstrip(":")] = clean(td)
                    label = None

        else:  # key-value tables: header, duration, notification
            for r in rows:
                cells = r.find_all(["th", "td"])
                i = 0
                while i < len(cells) - 1:
                    if cells[i].name == "th" and cells[i + 1].name == "td":
                        label = clean(cells[i]).rstrip(":").strip()
                        value = clean(cells[i + 1])
                        key = KNOWN.get(label.lower())
                        if key:
                            out[key] = value
                        else:
                            out["extra"][label] = value
                        i += 2
                    else:
                        i += 1

    for field in REQUIRED:
        if not out.get(field):
            out["warnings"].append(f"missing:{field}")
    return out


def parse_emission_point(table, summary, warnings):
    ep = {"summary": summary, "name": "", "epn": "", "declared_total": None, "contaminants": []}
    rows = table.find_all("tr")
    data_rows = []
    for r in rows:
        ths, tds = r.find_all("th"), r.find_all("td")
        text = clean(r)
        m = re.search(r"List of Air Contaminant Compounds\s*-\s*(\d+)\s*total", text, re.I)
        if m:
            ep["declared_total"] = int(m.group(1))
        elif tds and not ths and len(tds) == 2 and not ep["name"] and not ep["epn"]:
            ep["name"], ep["epn"] = clean(tds[0]), clean(tds[1])
        elif tds and not ths and len(tds) >= 6:
            data_rows.append(tds)
    # the name/EPN row uses colspan cells; fall back to those if the 2-cell test missed
    if not ep["name"] and not ep["epn"]:
        for r in rows:
            tds = r.find_all("td")
            if len(tds) == 2 and not r.find("th"):
                ep["name"], ep["epn"] = clean(tds[0]), clean(tds[1])
                break
    for tds in data_rows:
        if not any(clean(td) for td in tds):  # blank filler row, not a contaminant
            continue
        qty = clean(tds[1])
        lim = clean(tds[3])
        ep["contaminants"].append({
            "description": clean(tds[0]),
            "quantity_text": qty,
            "quantity": to_float(qty),
            "units": clean(tds[2]),
            "limit_text": lim,
            "limit": to_float(lim),
            "limit_units": clean(tds[4]),
            "authorization": clean(tds[5]),
        })
    if ep["declared_total"] is not None and ep["declared_total"] != len(ep["contaminants"]):
        warnings.append(
            f"contaminant_count_mismatch:{ep['epn'] or ep['name']}:"
            f"declared={ep['declared_total']},parsed={len(ep['contaminants'])}")
    return ep


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(parse(open(sys.argv[1], "rb").read()), indent=2))
