"""Build tools/hand_coding.html: a single offline page for hand-coding the 400-event validation sample.

The page shows only each event's cause text (never the rules' output), saves progress in the
browser, and exports a CSV. Open the file in any browser; nothing is uploaded anywhere.
Usage: python3 src/make_coding_page.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from details_store import iter_details  # noqa: E402

CATS = [("weather", "Weather", "storm, lightning, freeze, ice, heavy rain, high wind, flood"),
        ("third_party", "Third party", "another company or outside facility caused it"),
        ("power", "Power or electrical", "power loss or dip, breaker, transformer, electrical fault"),
        ("operator", "Operator or procedure", "a person's action or a procedure caused it"),
        ("instrument", "Instrument or control", "failed sensor, controller, PLC, false signal"),
        ("equipment", "Equipment", "leak, rupture, crack, seal or gasket failure, broken part"),
        ("upset", "Process upset", "unit tripped or went out of range, no deeper cause stated"),
        ("maintenance_startup", "Maintenance or startup", "planned work, repair, startup, restart, tie-in")]


def main():
    ids = [int(x) for x in (ROOT / "data/samples/cause_validation_sample.txt").read_text().split()]
    found = {n: p.get("cause", "") or "" for n, p in iter_details(set(ids))}
    items = [{"id": n, "text": found[n]} for n in ids if n in found]
    if len(items) != len(ids):
        sys.exit(f"only {len(items)} of {len(ids)} validation pages are saved")
    data = json.dumps({"items": items, "cats": [{"key": k, "label": l, "hint": h} for k, l, h in CATS]})
    data = data.replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", data)
    out = ROOT / "tools" / "hand_coding.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {len(items)} events, {out.stat().st_size / 1e3:.0f} KB")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hand coding: emission event causes</title>
<style>
:root{--bg:#f6f6f4;--card:#fff;--ink:#1b1b1b;--mute:#666;--line:#d9d9d4;--acc:#1f5eff;--ok:#1a7f4b}
@media(prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1e;--ink:#eee;--mute:#9a9a9a;--line:#333;--acc:#6b95ff;--ok:#4cc38a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
.bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.prog{flex:1;min-width:160px;height:8px;background:var(--line);border-radius:4px;overflow:hidden}
.prog i{display:block;height:100%;background:var(--ok);width:0}
button{font:inherit;padding:8px 14px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);cursor:pointer}
button.primary{background:var(--acc);border-color:var(--acc);color:#fff}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px}
.text{font-size:18px;white-space:pre-wrap;word-break:break-word}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:8px}
label.opt{display:flex;gap:8px;align-items:flex-start;padding:8px 10px;border:1px solid var(--line);border-radius:8px;cursor:pointer}
label.opt.on{border-color:var(--acc);background:color-mix(in srgb,var(--acc) 12%,transparent)}
label.opt small{display:block;color:var(--mute)}
.mute{color:var(--mute);font-size:14px}.derived{font-weight:600}
details{margin-bottom:12px}summary{cursor:pointer;color:var(--mute)}
input[type=text]{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
</style></head><body><main>
<h1 style="font-size:20px;margin:0 0 8px">Hand coding: what caused each emission event?</h1>
<details><summary>How to code (short version)</summary>
<p class="mute">Read the cause text. Tick <b>every</b> category it clearly describes. The primary cause is chosen for you: the first ticked category in this order: weather, third party, power, operator, instrument, equipment, process upset, maintenance. If the text gives no cause at all, tick <b>Unknown</b>. Code what the text says, not what you guess. A different company or facility counts as third party; the plant's own equipment does not. Report-status boxes are separate from cause. Keys: 1 to 8 toggle categories, 0 unknown, D / N / E toggle the status boxes, Enter or right arrow next, left arrow back.</p></details>
<div class="bar"><span>Coder: <input type="text" id="coder" placeholder="your initials" size="8"></span>
<span id="count" class="mute"></span><div class="prog"><i id="pbar"></i></div></div>
<div class="card"><div class="mute" id="pos"></div><div class="text" id="text"></div></div>
<div class="card"><div class="grid" id="cats"></div>
<div class="grid" style="margin-top:8px"><label class="opt" id="unk"><input type="checkbox" id="unkbox"><span>Unknown, no cause stated<small>key 0</small></span></label></div>
<p class="mute" style="margin:12px 0 4px">Report status (separate from cause)</p>
<div class="grid" id="stats"></div>
<p style="margin:12px 0 0">Primary cause: <span class="derived" id="primary">(tick at least one box, or Unknown)</span></p></div>
<div class="bar"><button id="prev">Back</button><button id="next" class="primary">Save and next</button>
<button id="nextun">Jump to next not coded</button><span style="flex:1"></span><button id="dl">Download CSV</button></div>
<p class="mute">Your work is saved in this browser as you go. Download the CSV when you finish, or any time as a backup.</p>
<script>
const D=__DATA__;const KEY="handcoding_v1";const ORDER=D.cats.map(c=>c.key);
const STAT=[["duplicate","Duplicate","text says it duplicates another report","d"],["not_reportable","Not reportable","text says it was below the reportable amount","n"],["filed_in_error","Filed in error","text says retracted, withdrawn or filed by mistake","e"]];
let S={};try{S=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
let i=0;const $=id=>document.getElementById(id);
function save(){try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}}
function cur(){const id=D.items[i].id;return S[id]||(S[id]={cats:[],unknown:false,status:[],done:false,at:null})}
function primary(r){if(r.unknown&&!r.cats.length)return"unknown";for(const k of ORDER)if(r.cats.includes(k))return k;return null}
function coded(r){return r&&r.done}
function build(){
 $("cats").innerHTML=D.cats.map((c,n)=>`<label class="opt" data-k="${c.key}"><input type="checkbox" data-k="${c.key}"><span>${c.label}<small>${c.hint} (key ${n+1})</small></span></label>`).join("");
 $("stats").innerHTML=STAT.map(s=>`<label class="opt" data-s="${s[0]}"><input type="checkbox" data-s="${s[0]}"><span>${s[1]}<small>${s[2]} (key ${s[3].toUpperCase()})</small></span></label>`).join("");
 document.querySelectorAll("#cats input").forEach(b=>b.onchange=()=>toggle(b.dataset.k));
 document.querySelectorAll("#stats input").forEach(b=>b.onchange=()=>togStat(b.dataset.s));
 $("unkbox").onchange=()=>toggleUnknown();}
function toggle(k){const r=cur();r.cats=r.cats.includes(k)?r.cats.filter(x=>x!==k):[...r.cats,k];if(r.cats.length)r.unknown=false;save();render()}
function toggleUnknown(){const r=cur();r.unknown=!r.unknown;if(r.unknown)r.cats=[];save();render()}
function togStat(s){const r=cur();r.status=r.status.includes(s)?r.status.filter(x=>x!==s):[...r.status,s];save();render()}
function render(){
 const r=cur(),it=D.items[i];$("pos").textContent=`Event ${i+1} of ${D.items.length}`+(coded(r)?"  (coded)":"");
 $("text").textContent=it.text||"(no cause text on the page)";
 document.querySelectorAll("#cats input").forEach(b=>{b.checked=r.cats.includes(b.dataset.k);b.parentElement.classList.toggle("on",b.checked)});
 document.querySelectorAll("#stats input").forEach(b=>{b.checked=r.status.includes(b.dataset.s);b.parentElement.classList.toggle("on",b.checked)});
 $("unkbox").checked=r.unknown;$("unk").classList.toggle("on",r.unknown);
 const p=primary(r);$("primary").textContent=p?(p==="unknown"?"unknown":D.cats.find(c=>c.key===p).label):"(tick at least one box, or Unknown)";
 const n=D.items.filter(x=>coded(S[x.id])).length;$("count").textContent=`${n} of ${D.items.length} coded`;$("pbar").style.width=(100*n/D.items.length)+"%"}
function commit(){const r=cur();if(!primary(r)){alert("Tick at least one category, or Unknown, before moving on.");return false}r.done=true;r.at=new Date().toISOString();save();return true}
function go(d){i=Math.max(0,Math.min(D.items.length-1,i+d));render();window.scrollTo(0,0)}
$("next").onclick=()=>{if(commit())go(1)};$("prev").onclick=()=>go(-1);
$("nextun").onclick=()=>{const j=D.items.findIndex((x,n)=>n>i&&!coded(S[x.id]));const k=j>=0?j:D.items.findIndex(x=>!coded(S[x.id]));if(k>=0){i=k;render()}else alert("All events are coded.")};
$("dl").onclick=()=>{const q=v=>`"${String(v).replace(/"/g,'""')}"`;const hdr=["incident","coder","primary_cause",...ORDER.map(k=>"cause_"+k),"cause_unknown",...STAT.map(s=>"status_"+s[0]),"coded_at"];
 const rows=D.items.filter(x=>coded(S[x.id])).map(x=>{const r=S[x.id];return[x.id,$("coder").value,primary(r),...ORDER.map(k=>r.cats.includes(k)),r.unknown,...STAT.map(s=>r.status.includes(s[0])),r.at].map(q).join(",")});
 const blob=new Blob([[hdr.join(","),...rows].join("\n")],{type:"text/csv"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`hand_coding_${$("coder").value||"coder"}.csv`;a.click()};
$("coder").value=localStorage.getItem(KEY+"_coder")||"";$("coder").oninput=()=>{try{localStorage.setItem(KEY+"_coder",$("coder").value)}catch(e){}};
document.addEventListener("keydown",e=>{if(e.target.tagName==="INPUT"&&e.target.type==="text")return;
 const n=parseInt(e.key,10);if(n>=1&&n<=D.cats.length)return toggle(D.cats[n-1].key);if(e.key==="0")return toggleUnknown();
 const s=STAT.find(x=>x[3]===e.key.toLowerCase());if(s)return togStat(s[0]);
 if(e.key==="Enter"||e.key==="ArrowRight"){if(e.key==="Enter"){if(commit())go(1)}else go(1)}if(e.key==="ArrowLeft")go(-1)});
build();const first=D.items.findIndex(x=>!coded(S[x.id]));i=first>=0?first:0;render();
</script></main></body></html>
"""

if __name__ == "__main__":
    main()
