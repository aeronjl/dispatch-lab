"""Render the authored research and source catalogue as offline Markdown and HTML."""

import html
import json
import re
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent
sources = json.loads((ROOT / "sources.json").read_text())
catalogue = json.loads((ROOT / "catalogue.json").read_text())
by_id = {s["id"]: dict(s, number=i + 1) for i, s in enumerate(sources)}
assert len(by_id) == len(sources)


def citation(key):
    s = by_id[key]
    return f"[{s['number']}: {s['title']}]({s['url']})"


def citations(text):
    return re.sub(r"\[@([a-z0-9]+)\]", lambda m: citation(m[1]), text)


rows = []
for a in catalogue["approaches"]:
    refs = " ".join(f"[{by_id[k]['number']}]({by_id[k]['url']})" for k in a["sources"])
    rows.append(
        f"| **{a['name']}** | {a['role']} {a['strength']} | {a['limit']} "
        f"| {a['evidence']} {refs} | {a['priority']} |"
    )
table = (
    "| Approach | Role and strength | Limitation | Evidence | Priority |\n"
    "|---|---|---|---|---|\n" + "\n".join(rows)
)

references = []
for s in sources:
    references.append(
        f'<a id="source-{s["id"]}"></a>\n\n'
        f"**{by_id[s['id']]['number']}. {s['authors']}.** "
        f"[{s['title']}]({s['url']}). {s['date']}. "
        f"**Evidence:** {s['type']}. **Access:** {s['access']}. "
        f"**Scope:** {s['scope']}"
    )

architecture_text = """```text
Mission + risk limits + original forecasts
                    ↓
Observations → State / health belief → Joint planner
      ↑                ↓                    ↓
      │         Diagnosis / inspection  Action proposal
      │                ↓                    ↓
      │          Recovery executive ← Safety check
      │                ↓
      └── Plant ← Local regulation and protection

Offline models / values → Evaluated candidate registry → Planner / estimator
All decisions and transitions → Versioned evidence record
```"""

architecture_html = """<figure class="architecture" aria-label="Recommended controller architecture">
<div class="architecture-top">Mission, risk limits and eligible forecasts</div>
<div class="arrow" aria-hidden="true">↓</div>
<div class="architecture-row"><div>Observations<small>Timestamped measurements</small></div><span aria-hidden="true">→</span><div>State and health belief<small>Estimates and uncertainty</small></div><span aria-hidden="true">→</span><div>Joint planner<small>Resources and commitments</small></div></div>
<div class="architecture-row connectors" aria-hidden="true"><div>↓</div><span></span><div>↓</div><span></span><div>↓</div></div>
<div class="architecture-row"><div>Diagnosis and inspection<small>Evidence and bounded probes</small></div><span aria-hidden="true">→</span><div>Recovery executive<small>Modes and verified sequences</small></div><span aria-hidden="true">←</span><div>Safety check<small>Admissible proposals and fallback</small></div></div>
<div class="arrow" aria-hidden="true">↓</div>
<div class="architecture-top">Local regulation and protection → Physical plant → New observations</div>
<figcaption>Offline training supplies evaluated model candidates. Every observation, proposal, intervention and outcome enters the versioned evidence record. This is a proposed architecture; it does not imply that the current hourly model implements local equipment protection.</figcaption>
</figure>"""

source = (ROOT / "report-source.md").read_text()
source = citations(
    source.replace("{{APPROACH_TABLE}}", table).replace("{{REFERENCES}}", "\n\n".join(references))
)
markdown = source.replace("{{ARCHITECTURE}}", architecture_text)
assert not re.search(r"\{\{|\[@", markdown)
(ROOT / "report.md").write_text(markdown)

md = MarkdownIt("commonmark", {"html": True}).enable("table")
body = md.render(source.replace("{{ARCHITECTURE}}", architecture_html))
# Compact numbered citations retain the full accessible source title.
body = re.sub(
    r'<a href="([^"]+)">(\d+): ([^<]+)</a>',
    lambda m: (
        f'<sup><a href="{m[1]}" title="{html.escape(m[3], quote=True)}" aria-label="Source {m[2]}: {html.escape(m[3], quote=True)}">[{m[2]}]</a></sup>'
    ),
    body,
)
toc = []


def heading(match):
    label = re.sub("<[^>]*>", "", match[1])
    slug = "section-" + str(len(toc) + 1)
    toc.append((slug, label))
    return f'<h2 id="{slug}">{match[1]}</h2>'


body = re.sub(r"<h2>(.*?)</h2>", heading, body)
body = re.sub(
    r"<table>(.*?)</table>",
    r'<div class="table-scroll" tabindex="0"><table>\1</table></div>',
    body,
    flags=re.S,
)
# The method table is identified by its distinctive first header, without relying on table position.
body = body.replace(
    "<table>\n<thead>\n<tr>\n<th>Approach</th>",
    '<table id="approaches">\n<thead>\n<tr>\n<th>Approach</th>',
)
assert 'id="approaches"' in body
search = '<div class="catalogue-filter"><label for="method-search">Filter the approach catalogue</label><div><input id="method-search" type="search" placeholder="Try recovery, learning or uncertainty"><button id="clear-search" type="button">Show all</button></div><p id="filter-status" role="status" aria-live="polite">16 approaches</p></div>'
body = body.replace(
    '<div class="table-scroll" tabindex="0"><table id="approaches">',
    search + '<div class="table-scroll" tabindex="0"><table id="approaches">',
)
nav = "".join(f'<a href="#{slug}">{html.escape(label)}</a>' for slug, label in toc)
style = """
:root{color-scheme:light;--ink:#202124;--muted:#5b5e63;--line:#dadddf;--paper:#fff;--wash:#f4f5f6}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;color:var(--ink);background:var(--paper);font:18px/1.7 Georgia,'Times New Roman',serif}a{color:inherit;text-decoration-color:#9b9da0;text-underline-offset:3px}a:hover{text-decoration-thickness:2px}a:focus-visible,button:focus-visible,input:focus-visible,.table-scroll:focus-visible{outline:3px solid #30343b;outline-offset:4px}.skip{position:fixed;top:-100px;left:20px;background:white;z-index:5;padding:10px}.skip:focus{top:10px}
.layout{display:grid;grid-template-columns:244px minmax(0,1080px);gap:58px;max-width:1450px;margin:auto;padding:60px 44px 100px}aside{font:13px/1.5 system-ui,sans-serif;position:sticky;top:36px;align-self:start;max-height:calc(100vh - 72px);overflow:auto;padding-right:10px}aside strong{display:block;margin:0 0 18px;font-size:14px}nav a{display:block;padding:8px 0;text-decoration:none;color:var(--muted)}nav a:hover{color:var(--ink);text-decoration:underline}.downloads{border-top:1px solid var(--line);margin-top:20px;padding-top:14px}.downloads a{display:block;margin:8px 0}main{min-width:0}h1,h2,h3,th,button,label,.architecture{font-family:system-ui,-apple-system,sans-serif}h1{font-size:clamp(32px,3.2vw,48px);line-height:1.15;letter-spacing:-1.2px;margin:0 0 36px;max-width:950px}h2{font-size:28px;line-height:1.3;letter-spacing:-.45px;margin:64px 0 24px;padding-top:24px;border-top:1px solid var(--line)}h3{font-size:20px;line-height:1.4;margin:32px 0 16px}p,li{max-width:82ch}p{margin:0 0 22px}li{padding-left:3px;margin:12px 0}strong{font-weight:700}code{font: .83em/1.6 ui-monospace,SFMono-Regular,Consolas,monospace}p code,li code{background:var(--wash);padding:1px 4px}pre{background:var(--wash);padding:22px;overflow:auto;border:1px solid var(--line);border-radius:3px;line-height:1.55}pre code{font-size:13px}
.table-scroll{overflow-x:auto;margin:24px 0 32px;border:1px solid var(--line);border-radius:3px}table{border-collapse:collapse;width:100%;font:14px/1.6 system-ui,sans-serif;min-width:680px}td,th{padding:15px 16px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:var(--wash);font-size:13px}tr:last-child td{border-bottom:0}td:first-child{min-width:145px}#approaches td{font-size:13px}#approaches td:nth-child(2){min-width:210px}#approaches td:nth-child(3){min-width:210px}#approaches td:nth-child(4){min-width:175px}tr[hidden]{display:none}.catalogue-filter{font:14px/1.5 system-ui,sans-serif;margin:28px 0 0}.catalogue-filter label{display:block;font-weight:600;margin-bottom:10px}.catalogue-filter>div{display:flex;gap:12px}input{font:15px system-ui,sans-serif;border:1px solid #888;border-radius:3px;padding:11px 13px;width:min(100%,430px);min-width:0;background:white;color:var(--ink)}button{font-size:14px;background:var(--wash);border:1px solid #888;border-radius:3px;padding:10px 14px;cursor:pointer;white-space:nowrap}.catalogue-filter p{color:var(--muted);font-size:12px;margin:9px 0 0}.architecture{background:var(--wash);padding:25px;margin:28px 0;border:1px solid var(--line);font-size:14px;line-height:1.5}.architecture-top{border:1px solid #8b8d90;padding:16px;text-align:center;background:#fff}.architecture-row{display:grid;grid-template-columns:1fr 18px 1fr 18px 1fr;align-items:center;gap:6px}.architecture-row>div{padding:16px 12px;border:1px solid #8b8d90;background:white;min-height:102px}.architecture small{display:block;font-size:12px;line-height:1.4;color:var(--muted);margin-top:8px}.connectors>div{border:0;min-height:0;background:none;text-align:center;padding:7px;font-size:20px}.arrow{text-align:center;padding:8px;font-size:20px}.architecture figcaption{font:12px/1.6 system-ui,sans-serif;color:var(--muted);margin:18px 0 0}.footer{margin-top:50px;padding-top:22px;border-top:1px solid var(--line);font:13px/1.6 system-ui,sans-serif;color:var(--muted)}
@media(max-width:1000px){.layout{grid-template-columns:180px minmax(0,1fr);gap:28px;padding:36px 25px}body{font-size:17px}.architecture{padding:15px}.architecture-row{grid-template-columns:1fr}.architecture-row>span{display:none}.connectors{display:none}.architecture-row>div{min-height:0}h1{font-size:36px}}
@media(max-width:720px){.layout{display:block;padding:28px 20px 70px}aside{position:static;max-height:none;padding:0 0 25px;margin-bottom:32px;border-bottom:1px solid var(--line)}aside nav{display:flex;flex-wrap:wrap;gap:6px 17px;max-height:165px;overflow:auto}nav a{padding:3px 0;font-size:12px}.downloads{display:flex;gap:15px;flex-wrap:wrap;margin-top:15px;padding-top:9px}.downloads a{margin:2px 0}h1{font-size:34px;letter-spacing:-.7px}h2{font-size:25px;margin-top:44px}pre{padding:14px}.architecture{margin-left:0;margin-right:0}.catalogue-filter>div{gap:8px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{.layout{display:block;max-width:none;padding:0}aside,.skip,.catalogue-filter{display:none}body{font-size:10.5pt;line-height:1.5}h1{font-size:25pt}h2{font-size:17pt;margin-top:26pt}h3{font-size:12pt}table{font-size:8pt;min-width:0}#approaches td{font-size:8pt;min-width:0!important}td,th{padding:6pt}pre{white-space:pre-wrap}a{text-decoration:none}.table-scroll{overflow:visible}tr{break-inside:avoid}tr[hidden]{display:table-row}.architecture{break-inside:avoid}h2,h3{break-after:avoid}}
"""
script = """
const field=document.getElementById('method-search');
const rows=[...document.querySelectorAll('#approaches tbody tr')];
function filter(){const query=field.value.toLocaleLowerCase().trim();let count=0;for(const row of rows){row.hidden=!row.textContent.toLocaleLowerCase().includes(query);if(!row.hidden)count++;}document.getElementById('filter-status').textContent=`${count} of ${rows.length} approaches`;}
field.addEventListener('input',filter);
document.getElementById('clear-search').addEventListener('click',()=>{field.value='';filter();field.focus();});
"""
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Autonomous management of renewable-powered methane plants</title><style>{style}</style></head><body><a class="skip" href="#report">Skip to report</a><div class="layout"><aside aria-label="Report navigation"><strong>Contents</strong><nav>{nav}</nav><div class="downloads"><a href="report.md">Markdown report</a><a href="catalogue.json">Approach catalogue</a><a href="sources.json">Source records</a></div></aside><main id="report">{body}<p class="footer">Research assessment · 10 September 2026 · No application code or controller behaviour changed. The report works offline; following an external source link requires a connection.</p></main></div><script>{script}</script></body></html>"""
(ROOT / "report.html").write_text(page)
print(
    json.dumps(
        {
            "sources": len(sources),
            "approaches": len(rows),
            "sections": len(toc),
            "words": len(markdown.split()),
            "html_bytes": len(page.encode()),
        }
    )
)
