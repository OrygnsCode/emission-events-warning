"""Build tools/outcome_link_review.html: the author's hand review of links for the independent outcomes
(plan 6.4 for National Response Center reports, H4; D2 item 7 for OSHA records, O6).

Reads data/derived/outcome_link_items.json (src/outcome_link_candidates.py). The page shows identifying fields only:
names, addresses, county or ZIP, date and why a site was suggested; never emission events or accidents. Answers save
in the browser; "Download answers" writes outcome_link_decisions.json, which goes to data/manual/.
Each card is one report; the author picks the suggested site that is the same physical site, or "none of these", or
"can't tell" (one answer per report; a site not picked counts as different).
Usage: python3 src/make_outcome_review_page.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
items = json.loads((ROOT / "data/derived/outcome_link_items.json").read_text())
dfile = ROOT / "data/manual/outcome_link_decisions.json"
prefill = json.loads(dfile.read_text())["decisions"] if dfile.exists() else {}
items["made"] = str((ROOT / "data/derived/outcome_link_items.json").stat().st_mtime_ns)
# only records with at least one candidate need an answer
items["nrc"] = [i for i in items["nrc"] if i["candidates"]]
for i in items["nrc"]:
    for c in i["candidates"]:
        c.setdefault("why", ["same county"])
csb = json.loads((ROOT / "data/derived/csb_items.json").read_text())["csb"]
items["csb"] = [i for i in csb if i["candidates"]]
items["csb_no_candidate"] = [{k: i[k] for k in ("date", "name", "address")} for i in csb if not i["candidates"]]

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Outcome link review</title>
<style>
:root{--bg:#fafaf8;--card:#fff;--ink:#1d1d1b;--mute:#666;--line:#ddd;--same:#1f7a3a;--diff:#a3261d;--unsure:#8a6d00;--accent:#24508f}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--card:#202020;--ink:#eee;--mute:#aaa;--line:#3a3a3a;--accent:#8fb3ec}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;z-index:5}
h1{font-size:18px;margin:0 0 6px}.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
button.on.same{background:var(--same);color:#fff;border-color:var(--same)}button.on.different{background:var(--diff);color:#fff;border-color:var(--diff)}
button.on.unsure{background:var(--unsure);color:#fff;border-color:var(--unsure)}button.tab.on{background:var(--accent);color:#fff;border-color:var(--accent)}
main{max-width:1100px;margin:0 auto;padding:16px}.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:0 0 16px}
.rec{border:1px solid var(--line);border-radius:8px;padding:10px}.rec h3{margin:0 0 6px;font-size:14px;color:var(--mute);font-weight:600}
.k{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.03em}.v{margin:0 0 6px;word-break:break-word}
.ev{font-size:13px;color:var(--mute);margin:8px 0}.ans{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.cand{border-top:1px dashed var(--line);margin-top:12px;padding-top:12px}.help{max-width:1100px;margin:0 auto;padding:0 16px;color:var(--mute);font-size:14px}
.done{opacity:.55}
</style></head><body>
<header><h1>Outcome link review</h1>
<div class="bar"><button class="tab on" id="t1" onclick="show('nrc')">National Response Center</button><button class="tab" id="t2" onclick="show('osha')">OSHA</button><button class="tab" id="t3" onclick="show('csb')">CSB</button>
<span id="prog"></span><button onclick="exportAnswers()">Download answers</button><label><input type="checkbox" id="hide" onchange="render()"> hide answered</label></div></header>
<div class="help"><p><b>Your job:</b> each card is one report (top). Below it are suggested sites, best matches first (the rest open with "Show more"). Click <b>This one</b> on the site that is the
<b>same physical site</b> as the report, or <b>None of these</b> if none is, or <b>Can't tell</b>. Only pick a site when you are confident.
You see names, addresses, county or ZIP and dates only; no emission events and no accidents. On the CSB tab the suggestions are RMP accident
records: pick the one that is the same accident. Answers save in this browser. When finished, click <b>Download answers</b> and send the file.</p></div>
<main id="list"></main>
<script>
const DATA = __DATA__;
const PREFILL = __PREFILL__;
const KEY = "outcome_review_v1_" + DATA.made;
let ans = {}; try { ans = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
for (const [k, v] of Object.entries(PREFILL)) if (!(k in ans)) ans[k] = v;
let mode = "nrc";
const open = {};
function save(){ try { localStorage.setItem(KEY, JSON.stringify(ans)); } catch (e) {} prog(); }
function esc(s){ return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function pick(k, id, label, cls){
  return `<button class="${cls} ${ans[k]===id?"on":""}" onclick="setA('${k}','${id}')">${label}</button>`;
}
function setA(k,v){ ans[k] = v; save(); render(); }
function render(){
  const hide = document.getElementById("hide").checked, out = [], list = DATA[mode];
  list.forEach((it,i) => {
    const done = !!ans[it.key];
    if(hide && done) return;
    out.push(`<div class="item ${done?"done":""}"><div class="k">${esc(it.source)} · item ${i+1} of ${list.length}</div>
      <div class="rec"><h3>Report</h3><div class="k">Date</div><div class="v">${esc(it.date)}</div>
      <div class="k">Company or employer</div><div class="v">${esc(it.name)||"none"}</div>
      ${it.location?`<div class="k">Location text</div><div class="v">${esc(it.location)}</div>`:""}
      <div class="k">Address</div><div class="v">${esc(it.address)}</div>
      ${it.county?`<div class="k">County</div><div class="v">${esc(it.county)}</div>`:""}</div>
      ${it.candidates.map((c,j) => `<div class="cand" ${j>=5 && !open[it.key] ? 'style="display:none"' : ""}><div class="ev">Why suggested: ${esc((c.why||[]).join("; "))}${c.shared_words&&c.shared_words.length?" · shared words: "+esc(c.shared_words.join(", ")):""}${c.street_number_match?" · same street number":""}</div>
        <div class="rec"><h3>TCEQ site</h3><div class="k">Names</div><div class="v">${esc(c.names)}</div>
        <div class="k">Addresses</div><div class="v">${esc((c.addresses||[]).join(" | "))||"none on file"}</div></div><div class="ans">${pick(it.key, c.id, "This one", "same")}</div></div>`).join("")}
      ${it.candidates.length>5 && !open[it.key] ? `<div class="ans"><button onclick="open['${it.key}']=1;render()">Show ${it.candidates.length-5} more suggested sites</button></div>` : ""}
      <div class="ans" style="margin-top:12px">${pick(it.key, "none", "None of these", "different")}${pick(it.key, "unsure", "Can't tell", "unsure")}</div></div>`);
  });
  document.getElementById("list").innerHTML = out.join("") || "<p>All answered in this list.</p>";
  prog();
}
function prog(){
  const c = l => DATA[l].filter(it => ans[it.key]).length;
  document.getElementById("prog").textContent = `NRC: ${c("nrc")}/${DATA.nrc.length} · OSHA: ${c("osha")}/${DATA.osha.length} · CSB: ${c("csb")}/${DATA.csb.length} answered`;
}
function show(m){ mode = m; ["nrc","osha","csb"].forEach((x,i) => document.getElementById("t"+(i+1)).classList.toggle("on", m===x)); render(); window.scrollTo(0,0); }
function exportAnswers(){
  const blob = new Blob([JSON.stringify({items_made: DATA.made, exported: new Date().toISOString(), decisions: ans}, null, 1)], {type: "application/json"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "outcome_link_decisions.json"; a.click();
}
render();
</script></body></html>"""

page = HTML.replace("__DATA__", json.dumps(items)).replace("__PREFILL__", json.dumps(prefill))
out = ROOT / "tools" / "outcome_link_review.html"
out.write_text(page)
print(f"wrote {out} ({len(page) / 1e6:.1f} MB): {len(items['nrc'])} NRC reports, {len(items['osha'])} OSHA records, "
      f"{len(items['csb'])} CSB investigations to answer")
