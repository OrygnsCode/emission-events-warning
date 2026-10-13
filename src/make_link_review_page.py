"""Build tools/link_review.html: the hand-review page for plant links (plan D2 item 3 and D3).

Reads data/derived/link_review_items.json (made by src/link_plants_v2.py). The page shows only identifying
records (names, addresses, county, industry codes, IDs, coordinates with map links), never emission events or
accidents. Answers already in data/manual/link_review_decisions.json are shown pre-filled. Answers are kept in the browser and downloaded as a JSON file, which goes to
data/manual/link_review_decisions.json.

Usage: python3 src/make_link_review_page.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
items = json.loads((ROOT / "data/derived/link_review_items.json").read_text())
rules = json.loads((ROOT / "rules/linking_rules.json").read_text())
# answers already given (data/manual/link_review_decisions.json) are shown pre-filled and can be changed
dfile = ROOT / "data/manual/link_review_decisions.json"
prefill = json.loads(dfile.read_text())["decisions"] if dfile.exists() else {}

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plant link review</title>
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
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:760px){.grid{grid-template-columns:1fr}}
.rec{border:1px solid var(--line);border-radius:8px;padding:10px}.rec h3{margin:0 0 6px;font-size:14px;color:var(--mute);font-weight:600}
.k{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.03em}.v{margin:0 0 6px;word-break:break-word}
.ev{font-size:13px;color:var(--mute);margin:8px 0}.ans{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.cand{border-top:1px dashed var(--line);margin-top:12px;padding-top:12px}.help{max-width:1100px;margin:0 auto;padding:0 16px;color:var(--mute);font-size:14px}
a{color:var(--accent)}.done{opacity:.55}
</style></head><body>
<header><h1>Plant link review</h1>
<div class="bar"><button class="tab on" id="t1" onclick="show('m')">Possible matches</button><button class="tab" id="t2" onclick="show('c')">Groups to check</button>
<span id="prog"></span><button onclick="exportAnswers()">Download answers</button><label><input type="checkbox" id="hide" onchange="render()"> hide answered</label></div></header>
<div class="help"><p><b>Your job:</b> decide whether two records describe the <b>same physical site</b>. You only see names, addresses, county,
industry codes, permit IDs and map points. Choose <b>Same plant</b> only when you are confident; <b>Different</b> when they are different
sites or different companies that share an address; <b>Can't tell</b> otherwise. Use the map links to look at the site. Answers save in this
browser automatically. When finished, click <b>Download answers</b> and send the file.</p>
<p id="rule"></p></div>
<main id="list"></main>
<script>
const DATA = __DATA__;
const PREFILL = __PREFILL__;
const KEY = "link_review_v1_" + DATA.made;
let ans = {}; try { ans = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
for (const [k, v] of Object.entries(PREFILL)) if (!(k in ans)) ans[k] = v;
let mode = "m";
function save(){ try { localStorage.setItem(KEY, JSON.stringify(ans)); } catch (e) {} prog(); }
function esc(s){ return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function maps(pts){ return (pts||[]).map(p => `<a target="_blank" rel="noopener" href="https://www.google.com/maps?q=${p[0]},${p[1]}&t=k">map ${p[0].toFixed(4)}, ${p[1].toFixed(4)}</a>`).join(" &middot; ") || "no coordinates"; }
function rec(title, r, kind){
  if(!r) return `<div class="rec"><h3>${esc(title)}</h3>no record</div>`;
  return `<div class="rec"><h3>${esc(title)}</h3>
  <div class="k">Names</div><div class="v">${esc(r.names)}</div>
  <div class="k">Address</div><div class="v">${esc(r.address)||"none on file"}</div>
  <div class="k">County</div><div class="v">${esc(r.county)}</div>
  <div class="k">Industry code (NAICS)</div><div class="v">${esc(r.naics)||"none"}</div>
  <div class="k">${kind==="rmp"?"IDs it listed":"TCEQ programs"}</div><div class="v">${esc(kind==="rmp"?r.ids:r.programs)||"none"}</div>
  <div class="k">Location</div><div class="v">${maps(r.points)}</div></div>`;
}
function buttons(k){
  const a = ans[k];
  return `<div class="ans">${[["same","Same plant"],["different","Different"],["unsure","Can't tell"]].map(([v,l]) =>
    `<button class="${v} ${a===v?"on":""}" onclick="setA('${k}','${v}')">${l}</button>`).join("")}</div>`;
}
function setA(k,v){ ans[k] = v; save(); render(); }
function evid(c){ return `<div class="ev">Why suggested: ${esc(c.rule.replace(/_/g," "))}${c.distance_km!=null?` &middot; ${c.distance_km} km apart`:""}${c.shared_words?` &middot; shared words: ${esc(c.shared_words)}`:""}${c.same_county?" &middot; same county":" &middot; different county"}${c.same_address?" &middot; same street address":""}</div>`; }
function render(){
  const hide = document.getElementById("hide").checked, out = [];
  if(mode==="m"){
    DATA.match_items.forEach((it,i) => {
      const keys = it.candidates.map(c => it.rmp+"|"+c.rn), done = keys.every(k => ans[k]);
      if(hide && done) return;
      out.push(`<div class="item ${done?"done":""}"><div class="k">Item ${i+1} of ${DATA.match_items.length}</div>
      ${rec("EPA RMP facility", DATA.rmp_records[it.rmp], "rmp")}
      ${it.candidates.map(c => `<div class="cand">${evid(c)}${rec("TCEQ site", DATA.rn_records[c.rn], "rn")}${buttons(it.rmp+"|"+c.rn)}</div>`).join("")}</div>`);
    });
  } else {
    DATA.chain_items.forEach((it,i) => {
      const keys = it.links.map(l => l.rmp+"|"+l.rn), done = keys.every(k => ans[k]);
      if(hide && done) return;
      out.push(`<div class="item ${done?"done":""}"><div class="k">Group ${i+1} of ${DATA.chain_items.length}: these links join records that are far apart or in different counties. Check each link.</div>
      ${it.links.map(l => `<div class="cand"><div class="ev">Linked by: ${esc(l.rule)}${l.distance_km!=null?` &middot; ${l.distance_km} km apart`:""}</div><div class="grid">${rec("EPA RMP facility", DATA.rmp_records[l.rmp], "rmp")}${rec("TCEQ site", DATA.rn_records[l.rn], "rn")}</div>${buttons(l.rmp+"|"+l.rn)}</div>`).join("")}</div>`);
    });
  }
  document.getElementById("list").innerHTML = out.join("") || "<p>All answered in this list.</p>";
  prog();
}
function prog(){
  const mk = DATA.match_items.flatMap(it => it.candidates.map(c => it.rmp+"|"+c.rn));
  const ck = DATA.chain_items.flatMap(it => it.links.map(l => l.rmp+"|"+l.rn));
  const n = a => a.filter(k => ans[k]).length;
  document.getElementById("prog").textContent = `Matches: ${n(mk)}/${mk.length} answered · Groups: ${n(ck)}/${ck.length} answered`;
}
function show(m){ mode = m; document.getElementById("t1").classList.toggle("on", m==="m"); document.getElementById("t2").classList.toggle("on", m==="c"); render(); window.scrollTo(0,0); }
function exportAnswers(){
  const blob = new Blob([JSON.stringify({items_made: DATA.made, exported: new Date().toISOString(), decisions: ans}, null, 1)], {type: "application/json"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "link_review_decisions.json"; a.click();
}
document.getElementById("rule").textContent = __RULE__;
render();
</script></body></html>"""

page = HTML.replace("__DATA__", json.dumps(items)).replace("__PREFILL__", json.dumps(prefill)).replace("__RULE__", json.dumps(rules["review_rules_for_the_reviewer"]))
out = ROOT / "tools" / "link_review.html"
out.write_text(page)
print(f"wrote {out} ({len(page) / 1e6:.1f} MB): {len(items['match_items'])} match items, {len(items['chain_items'])} groups")
