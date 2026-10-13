"""Plan D12, settling step: typed sites the strict rule left unmatched or matched to several RMP facilities are shown
to the author with looser suggestions (any shared name word in the same city, including common words; or a shared
uncommon name word anywhere in Texas; city text split at "/" and with "near"/"area" removed), at most 12 each.
The author picks the RMP facility that is the same site, or "none of these". No accident data is shown.
Output: tools/news_settle.html (answers download as news_settle_answers.json)
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_plants_v2 import words  # noqa: E402
import news_completeness as N  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
R = dict(dtype=str, keep_default_na=False)
STOP = {"TEXAS", "PLANT", "COMPANY", "INC", "LLC", "CORPORATION", "CORP", "THE", "AND", "FACILITY", "NOW", "NEAR"}


def main():
    ans = json.loads((ROOT / "data/manual/news_review_answers.json").read_text())["answers"]
    f = pd.read_csv(ROOT / "data/slices/rmp_raw/tblS1Facilities.csv.gz", usecols=[
        "EPAFacilityID", "FacilityName", "ParentCompanyName", "FacilityStr1", "FacilityCity", "ReceiptDate"], **R)
    names = (f.FacilityName + " " + f.ParentCompanyName).map(words)
    dfreq = pd.Series([w for n in names for w in n]).value_counts()
    rare = set(dfreq[dfreq / f.EPAFacilityID.nunique() <= 0.005].index)
    f["w"] = [n - STOP for n in names]
    f["city"] = f.FacilityCity.map(N.letters)
    latest = f.sort_values("ReceiptDate").groupby("EPAFacilityID").tail(1).set_index("EPAFacilityID")
    strict = {}
    exec_out = {}
    # rerun the strict step to know which typed sites need settling
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        N.main()
    inc = pd.read_csv(ROOT / "private/news_completeness_incidents.csv")
    typed_unmatched = sorted(set(inc.loc[inc.site.isna(), "typed"].dropna()))
    several = sorted({v["other"] for k, v in ans.items() if v.get("site") == "other"} - set(inc.typed.dropna()))
    items = []
    for t in typed_unmatched + several:
        m = re.match(r"\s*([^,]+),\s*([^,(]+)", t)
        nm, city = (m.group(1), m.group(2)) if m else (t, "")
        cities = {N.letters(re.sub(r"\b(near|area)\b", "", c, flags=re.I)) for c in city.split("/")}
        nw = words(nm) - STOP
        same_city = f[f.city.isin(cities) & f.w.map(lambda w: bool(w & nw))]
        statewide = f[f.w.map(lambda w: bool(w & nw & rare))]
        c = pd.concat([same_city, statewide]).drop_duplicates("EPAFacilityID")
        c = c.assign(n=c.w.map(lambda w: len(w & nw))).sort_values("n", ascending=False).head(12)
        items.append({"key": "SITE-%02d" % len(items), "typed": t, "candidates": [
            {"id": i, "name": latest.at[i, "FacilityName"], "address": f"{latest.at[i, 'FacilityStr1']}, {latest.at[i, 'FacilityCity']}",
             "older_names": sorted(set(f.loc[f.EPAFacilityID.eq(i), "FacilityName"]) - {latest.at[i, "FacilityName"]})[:3]}
            for i in c.EPAFacilityID]})
    print(len(items), "sites to settle;", sum(1 for i in items if i["candidates"]), "with suggestions")
    page = PAGE.replace("__DATA__", json.dumps(items))
    (ROOT / "tools/news_settle.html").write_text(page)


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>News sites to settle</title><style>
:root{--bg:#fafaf8;--card:#fff;--ink:#1d1d1b;--mute:#666;--line:#ddd;--on:#24508f;--no:#a3261d}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--card:#202020;--ink:#eee;--mute:#aaa;--line:#3a3a3a;--on:#8fb3ec}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px}main{max-width:900px;margin:0 auto;padding:16px}
.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:0 0 14px}.k{color:var(--mute);font-size:12px}
.c{border-top:1px dashed var(--line);margin-top:8px;padding-top:8px}button{font:inherit;padding:5px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
button.on{background:var(--on);color:#fff;border-color:var(--on)}button.on.no{background:var(--no);border-color:var(--no)}</style></head><body>
<header><b>News sites to settle</b> · <span id="p"></span> · <button onclick="dl()">Download answers</button></header>
<main><p class="k">Each card is a site you typed. Pick the RMP record that is the same physical site, or "None of these". No accidents are shown.</p><div id="l"></div></main>
<script>const D=__DATA__;const K="news_settle_v1";let A={};try{A=JSON.parse(localStorage.getItem(K)||"{}")}catch(e){}
function e(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function s(k,v){A[k]=v;try{localStorage.setItem(K,JSON.stringify(A))}catch(x){}r()}
function r(){document.getElementById("l").innerHTML=D.map((it,i)=>`<div class="item"><div class="k">${i+1} of ${D.length}</div><b>${e(it.typed)}</b>
${it.candidates.map(c=>`<div class="c">${e(c.name)} · ${e(c.address)}${c.older_names.length?`<div class="k">also filed as: ${e(c.older_names.join("; "))}</div>`:""}
<div><button class="${A[it.key]===c.id?"on":""}" onclick="s('${it.key}','${c.id}')">This one</button></div></div>`).join("")}
<div class="c"><button class="no ${A[it.key]==="none"?"on":""}" onclick="s('${it.key}','none')">None of these</button></div></div>`).join("");
document.getElementById("p").textContent=D.filter(it=>A[it.key]).length+" of "+D.length+" answered"}
function dl(){const b=new Blob([JSON.stringify({exported:new Date().toISOString(),items:D.map(it=>({key:it.key,typed:it.typed})),answers:A},null,1)],{type:"application/json"});
const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="news_settle_answers.json";a.click()}r();</script></body></html>"""

if __name__ == "__main__":
    main()
