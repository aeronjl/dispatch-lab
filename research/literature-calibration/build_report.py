"""Create a self-contained HTML research report from reviewed prose and records."""

import base64
import html
import json
import re
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
sources = json.loads((HERE / "sources.json").read_text())
source_numbers = {k: i + 1 for i, k in enumerate(sources)}
body = (HERE / "report.md").read_text()


def cite(match):
    key = match.group(1)
    s = sources[key]
    return f'<a class="citation" href="{html.escape(s["url"], quote=True)}" title="{html.escape(s["title"], quote=True)}">[{source_numbers[key]} · {html.escape(s["authors_publisher"].split(";")[0].split(" / ")[0])}]</a>'


body = re.sub(r"\[\[([a-z0-9-]+)\]\]", cite, body)
rendered = MarkdownIt("commonmark", {"html": True}).enable("table").render(body)
nav = []


def heading(match):
    title = match.group(1)
    slug = re.sub(r"[^a-z0-9]+", "-", html.unescape(title).lower()).strip("-")
    nav.append((slug, html.unescape(title)))
    return f'<h2 id="{slug}" tabindex="-1">{title}</h2>'


rendered = re.sub(r"<h2>(.*?)</h2>", heading, rendered)
rendered = re.sub(
    r"<table>(.*?)</table>",
    r'<div class="table-wrap" tabindex="0" role="region" aria-label="Research comparison table"><table>\1</table></div>',
    rendered,
    flags=re.S,
)


# No network or adjacent image files are needed to read the delivered HTML.
def embed(match):
    path = HERE / match.group(1)
    return 'src="data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode() + '"'


rendered = re.sub(r'src="(figures/[^"]+\.png)"', embed, rendered)
font = base64.b64encode(
    (HERE.parent.parent / "assets/fonts/DepartureMono-Regular.woff2").read_bytes()
).decode()
css = """
@font-face{font-family:Departure;src:url(data:font/woff2;base64,FONT) format('woff2');font-display:swap}
:root{color-scheme:dark;--bg:#1b1c1a;--panel:#20211f;--amber:#ffae47;--ink:#e7dfd2;--muted:#b6a58b;--line:#51422f}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:30px}body{margin:0;background:var(--bg);color:var(--ink);font-family:Departure,monospace;font-size:15px;line-height:1.78}a{color:var(--amber);text-underline-offset:4px;overflow-wrap:anywhere}a:hover{color:#ffcf8d}a:focus-visible,input:focus-visible,button:focus-visible,.table-wrap:focus-visible{outline:2px solid var(--amber);outline-offset:5px}.skip{position:fixed;top:-70px;left:18px;background:var(--bg);padding:10px;z-index:4}.skip:focus{top:10px}
nav{position:fixed;inset:0 auto 0 0;width:260px;border-right:1px solid var(--line);padding:32px 23px;overflow:auto;background:var(--bg)}.brand{color:var(--amber);font-size:13px;letter-spacing:2px;margin:0 0 27px}.nav-title{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px}#find{display:block;width:100%;font:inherit;font-size:12px;border:1px solid var(--line);background:var(--panel);color:var(--ink);padding:10px;margin:7px 0 19px;border-radius:0}nav ul{padding:0;list-style:none;margin:0}nav li{border-top:1px solid #373125}nav a{display:block;padding:10px 0;text-decoration:none;font-size:12px;line-height:1.6;color:var(--muted)}nav a[aria-current]{color:var(--amber)}.nav-foot{margin-top:24px;border-top:1px solid var(--line);padding-top:16px;color:var(--muted);font-size:11px}
main{margin-left:260px;padding:45px 54px 70px;max-width:1370px}.eyebrow{font-size:11px;letter-spacing:1.6px;color:var(--amber);margin-bottom:20px}.edition{color:var(--muted);font-size:12px}.intro-rule{height:1px;background:var(--line);margin:24px 0 36px}h1{font-size:clamp(30px,4vw,47px);line-height:1.25;font-weight:normal;color:var(--amber);margin:0 0 38px;letter-spacing:-1px}h2{font-size:25px;line-height:1.4;color:var(--amber);font-weight:normal;margin:70px 0 25px;padding-top:24px;border-top:1px solid var(--line)}h2:first-of-type{margin-top:0}p{max-width:83ch;margin:0 0 22px}strong{color:#ffca83;font-weight:normal}code{font-family:inherit;color:#ffca83;font-size:13px;overflow-wrap:anywhere}.citation{font-size:10px;text-decoration:none;white-space:normal;line-height:1.5;vertical-align:baseline;color:var(--muted)}.citation:hover{text-decoration:underline;color:var(--amber)}.table-wrap{overflow:auto;margin:30px 0;max-width:100%;border:1px solid var(--line)}table{width:100%;border-collapse:collapse;font-size:12px;line-height:1.7;min-width:570px}th{text-align:left;color:var(--amber);font-weight:normal;background:#27241e}td,th{padding:14px 17px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border:0}td:first-child{color:#f2c082;min-width:140px}td p{margin:0}img{width:100%;height:auto;display:block;background:var(--panel);margin:32px 0;border:1px solid var(--line)}ul{padding-left:23px;max-width:87ch}li{margin-bottom:9px}.source{padding:20px 0;border-bottom:1px solid var(--line);font-size:12px}.source p{margin:5px 0}.source-title{font-size:14px}.source-meta{color:var(--muted)}.toolbar{display:flex;gap:20px;flex-wrap:wrap;margin:22px 0 30px;font-size:12px}button{font:inherit;background:transparent;border:1px solid var(--line);color:var(--amber);padding:7px 14px;cursor:pointer}.status{display:inline-block;border:1px solid #746039;padding:5px 10px;font-size:11px;color:#eec080}.closing{font-size:12px;color:var(--muted);padding-top:24px}.empty{font-size:12px;color:var(--muted)}
@media(min-width:1700px){main{margin-left:calc(260px + (100vw - 1700px)/3)}}
@media(max-width:1050px){nav{width:220px;padding:24px 17px}main{margin-left:220px;padding:36px 28px}body{font-size:14px}h2{font-size:23px}}
@media(max-width:720px){nav{position:static;width:100%;max-height:235px;border-right:0;border-bottom:1px solid var(--line);padding:17px 22px}nav .brand{margin-bottom:10px}nav .nav-title,nav .nav-foot{display:none}#find{margin:6px 0 10px}nav ul{display:flex;gap:8px;overflow:auto;padding-bottom:7px}nav li{flex-shrink:0;border:1px solid var(--line);margin:0}nav a{max-width:205px;padding:8px 12px;font-size:11px}main{margin-left:0;padding:30px 21px 45px}h1{font-size:34px;margin-bottom:30px}h2{margin-top:48px;font-size:22px}table{font-size:11px}p{line-height:1.85}.eyebrow{font-size:10px}img{margin:25px 0}.toolbar{gap:15px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{nav,.toolbar,.skip{display:none}main{margin:0;padding:0;max-width:none}body{background:white;color:#222;font-family:monospace;font-size:10pt}h1,h2,strong,a{color:#553308}h2{break-after:avoid}img{max-height:300px;object-fit:contain;break-inside:avoid}.table-wrap{overflow:visible}table{min-width:0;font-size:9pt}th{background:#eee;color:#222}td:first-child,.source-meta,.citation,.edition,.eyebrow{color:#444}}
""".replace("FONT", font)
navhtml = (
    "".join(f'<li><a href="#{s}">{html.escape(t)}</a></li>' for s, t in nav)
    + '<li><a href="#sources">Sources and access record</a></li>'
)
refs = []
for key, s in sources.items():
    refs.append(
        f'<article class="source" id="source-{key}"><p class="source-title">{source_numbers[key]:02d} · <a href="{html.escape(s["url"], quote=True)}">{html.escape(s["title"])}</a></p><p>{html.escape(s["authors_publisher"])} · {html.escape(s["publication_date"])}</p><p class="source-meta">{html.escape(s["evidence_kind"])} · Accessed {s["accessed_date"]}</p><p class="source-meta">{html.escape(s["access"])}</p></article>'
    )
js = """
const field=document.querySelector('#find');const items=[...document.querySelectorAll('nav li')];
field.addEventListener('input',()=>{let n=0;items.forEach(li=>{li.hidden=!li.textContent.toLowerCase().includes(field.value.toLowerCase());if(!li.hidden)n++});document.querySelector('#empty').hidden=n>0;});
const observer=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){document.querySelectorAll('nav a').forEach(a=>{if(a.hash==='#'+e.target.id)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current')})}},{rootMargin:'-10% 0px -75% 0px'});document.querySelectorAll('h2[id]').forEach(h=>observer.observe(h));
document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{const h=document.querySelector(a.hash);if(h)h.focus({preventScroll:true})}));
document.querySelector('#print').addEventListener('click',()=>window.print());
"""
htmlout = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>A firmer physical basis · Dispatch Lab</title><meta name="description" content="Literature calibration with held-out solar and electrolyser fits, reactor response, battery curves and field-hardware evidence."><style>{css}</style></head><body><a class="skip" href="#main">Skip to report</a><nav aria-label="Report topics"><p class="brand">DISPATCH LAB</p><label class="nav-title" for="find">Find a topic</label><input id="find" type="search" placeholder="Solar, faults, costs…" autocomplete="off"><ul>{navhtml}</ul><p class="empty" id="empty" hidden>No matching topic</p><p class="nav-foot">Research edition 02<br>Literature boundary<br>12 September 2026<br><br>Reference fits and scoped evidence.<br>No production changes.</p></nav><main id="main"><div class="eyebrow">MODEL RESEARCH / LITERATURE CALIBRATION</div><div class="edition">12 September 2026 · Existing European plant fixture</div><div class="toolbar"><a href="reference-profiles.json">Reference profiles</a><a href="validation.json">Calculation checks</a><button id="print" type="button">Print report</button></div><div class="intro-rule"></div>{rendered}<h2 id="sources" tabindex="-1">Sources and access record</h2><p>{len(sources)} source records. Publication date is distinguished from retrieval date. Undated product pages are versioned by this review's access boundary.</p>{"".join(refs)}<p class="closing">Dispatch Lab · Research reference edition 02 · The simulation and historical records retain their original assumptions.</p></main><script>{js}</script></body></html>"""
(HERE / "report.html").write_text(htmlout)
print(f"Built {len(htmlout):,} characters, {len(nav)} sections, {len(sources)} sources")
