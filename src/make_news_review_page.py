"""Plan D12: draw the random sample of 500 news links and build tools/news_review.html for the author's blind check.

Frame: Texas GDELT candidates, duplicate links removed, article dates June 2003 to 2023; numpy seed 20261006.
Suggested sites: Texas RMP facilities (latest filing) with a non-generic name word in the link (words of 3 or more
letters; generic = in more than 0.5% of facility names), or whose full city name appears in the link; name matches
first, at most 15. The page shows the link, a web archive link, the article date and website only; no RMP accident
data. Output: data/manifests/news_sample_links.csv (the sample), tools/news_review.html
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_plants_v2 import words  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
R = dict(dtype=str, keep_default_na=False)


def slug_words(link):
    s = re.sub(r"^https?://[^/]+", "", str(link))
    return words(s)


def main():
    d = pd.read_csv(ROOT / "data/derived/gdelt_texas_candidates.csv.gz", dtype={"date": str})
    d["day"] = pd.to_datetime(d.date.str[:8], format="%Y%m%d", errors="coerce")
    d = d.drop_duplicates("link")
    d = d[d.day.between("2003-06-01", "2023-12-31")].reset_index(drop=True)
    frame = len(d)
    rng = np.random.default_rng(20261006)
    s = d.iloc[np.sort(rng.choice(len(d), size=500, replace=False))].reset_index(drop=True)
    s["key"] = ["NEWS-%03d" % i for i in range(len(s))]
    s[["key", "day", "website", "link"]].to_csv(ROOT / "data/manifests/news_sample_links.csv", index=False)

    f = pd.read_csv(ROOT / "data/slices/rmp_raw/tblS1Facilities.csv.gz", usecols=[
        "EPAFacilityID", "FacilityName", "ParentCompanyName", "FacilityStr1", "FacilityCity", "ReceiptDate"], **R)
    f = f.sort_values("ReceiptDate").groupby("EPAFacilityID").tail(1).reset_index(drop=True)
    names = (f.FacilityName + " " + f.ParentCompanyName).map(words)
    df = pd.Series([w for n in names for w in n]).value_counts()
    generic = set(df[df / len(f) > 0.005].index)
    f["nw"] = [n - generic for n in names]
    f["cw"] = f.FacilityCity.map(lambda c: frozenset(words(c)))
    items = []
    for r in s.itertuples():
        sw = slug_words(r.link)
        cand = []
        for x in f.itertuples():
            nm = x.nw & sw
            city = bool(x.cw) and x.cw <= sw
            if nm or city:
                cand.append((len(nm), city, x))
        cand.sort(key=lambda t: (-t[0], -int(t[1])))
        items.append({"key": r.key, "date": str(r.day.date()), "website": r.website, "link": r.link,
                      "archive": "https://web.archive.org/web/%s/%s" % (r.day.strftime("%Y%m%d"), r.link),
                      "candidates": [{"id": x.EPAFacilityID, "name": x.FacilityName,
                                      "address": f"{x.FacilityStr1}, {x.FacilityCity}",
                                      "why": ("name word: " + ", ".join(sorted(x.nw & sw)) if n else "same city")}
                                     for n, c, x in cand[:15]]})
    meta = {"frame": frame, "sample": len(s), "with_suggestions": sum(1 for i in items if i["candidates"])}
    print(meta)
    page = HTML.replace("__DATA__", json.dumps({"items": items, "meta": meta}))
    (ROOT / "tools/news_review.html").write_text(page)
    print("wrote tools/news_review.html", round(len(page) / 1e6, 2), "MB")


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>News sample review</title>
<style>
:root{--bg:#fafaf8;--card:#fff;--ink:#1d1d1b;--mute:#666;--line:#ddd;--yes:#1f7a3a;--no:#a3261d;--unsure:#8a6d00;--accent:#24508f}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--card:#202020;--ink:#eee;--mute:#aaa;--line:#3a3a3a;--accent:#8fb3ec}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;z-index:5}
h1{font-size:18px;margin:0 0 6px}.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
button.on.yes{background:var(--yes);color:#fff;border-color:var(--yes)}button.on.no{background:var(--no);color:#fff;border-color:var(--no)}
button.on.unsure{background:var(--unsure);color:#fff;border-color:var(--unsure)}button.on.site{background:var(--accent);color:#fff;border-color:var(--accent)}
main{max-width:1000px;margin:0 auto;padding:16px}.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:0 0 16px}
.k{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.03em}.v{margin:0 0 6px;word-break:break-all}
a{color:var(--accent)}.ans{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;align-items:center}.cand{border-top:1px dashed var(--line);margin-top:8px;padding-top:8px}
.help{max-width:1000px;margin:0 auto;padding:0 16px;color:var(--mute);font-size:14px}.done{opacity:.55}input{font:inherit;padding:5px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
</style></head><body>
<header><h1>News sample review</h1><div class="bar"><span id="prog"></span><button onclick="exportAnswers()">Download answers</button>
<label><input type="checkbox" id="hide" onchange="render()"> hide answered</label></div></header>
<div class="help"><p><b>For each link:</b> is it about a <b>fire, explosion, chemical release or injury at a fixed industrial site in Texas</b>
(plant, refinery, terminal, storage)? Pipelines, wells, trucks, trains and homes count as <b>No</b>. If <b>Yes</b>, pick the site from the
suggestions, or "Site not in the list" (type its name and city), or "Can't tell which site". If the article gives an incident date that differs
from the article date, type it. Open the link if the title is not enough; if it is dead, try the archive link. Answers save in this browser;
click <b>Download answers</b> at the end and send the file.</p></div>
<main id="list"></main>
<script>
const DATA = __DATA__;
const KEY = "news_review_v1";
let ans = {}; try { ans = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const open = {};
function save(){ try { localStorage.setItem(KEY, JSON.stringify(ans)); } catch (e) {} prog(); }
function esc(s){ return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function a(k){ return ans[k] || (ans[k] = {}); }
function set(k, f, v){ a(k)[f] = v; save(); render(); }
function txt(k, f, el){ a(k)[f] = el.value; save(); }
function b(k, f, v, label, cls){ return `<button class="${cls} ${(ans[k]||{})[f]===v?"on":""}" onclick="set('${k}','${f}','${v}')">${label}</button>`; }
function done(k){ const x = ans[k]; return x && (x.q1 === "no" || x.q1 === "unsure" || (x.q1 === "yes" && x.site)); }
function render(){
  const hide = document.getElementById("hide").checked, out = [];
  DATA.items.forEach((it, i) => {
    if (hide && done(it.key)) return;
    const x = ans[it.key] || {};
    let h = `<div class="item ${done(it.key)?"done":""}"><div class="k">item ${i+1} of ${DATA.items.length} · ${esc(it.date)} · ${esc(it.website)}</div>
      <div class="v"><a href="${esc(it.link)}" target="_blank" rel="noopener">${esc(it.link)}</a></div>
      <div class="v"><a href="${esc(it.archive)}" target="_blank" rel="noopener">archive copy</a></div>
      <div class="ans">${b(it.key,"q1","yes","Yes","yes")}${b(it.key,"q1","no","No","no")}${b(it.key,"q1","unsure","Can't tell","unsure")}</div>`;
    if (x.q1 === "yes") {
      const show = open[it.key] ? it.candidates : it.candidates.slice(0, 6);
      h += show.map(c => `<div class="cand"><div class="k">suggested (${esc(c.why)})</div><div class="v">${esc(c.name)} · ${esc(c.address)}</div>
        <div class="ans">${b(it.key,"site",c.id,"This site","site")}</div></div>`).join("");
      if (!open[it.key] && it.candidates.length > 6) h += `<div class="ans"><button onclick="open['${it.key}']=1;render()">Show ${it.candidates.length-6} more</button></div>`;
      h += `<div class="ans" style="margin-top:10px">${b(it.key,"site","other","Site not in the list","site")}${b(it.key,"site","unknown","Can't tell which site","unsure")}</div>`;
      if (x.site === "other") h += `<div class="ans">Name and city: <input size="40" value="${esc(x.other||"")}" onchange="txt('${it.key}','other',this)"></div>`;
      h += `<div class="ans">Incident date if different (YYYY-MM-DD): <input size="12" value="${esc(x.date||"")}" onchange="txt('${it.key}','date',this)"></div>`;
    }
    out.push(h + "</div>");
  });
  document.getElementById("list").innerHTML = out.join("") || "<p>All answered.</p>";
  prog();
}
function prog(){ document.getElementById("prog").textContent = `${DATA.items.filter(it => done(it.key)).length} of ${DATA.items.length} answered`; }
function exportAnswers(){
  const blob = new Blob([JSON.stringify({meta: DATA.meta, exported: new Date().toISOString(), answers: ans}, null, 1)], {type: "application/json"});
  const l = document.createElement("a"); l.href = URL.createObjectURL(blob); l.download = "news_review_answers.json"; l.click();
}
render();
</script></body></html>"""

if __name__ == "__main__":
    main()
