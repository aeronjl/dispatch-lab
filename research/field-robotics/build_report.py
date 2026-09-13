"""Build a self-contained, offline research report from authored source records."""

import hashlib
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


def cite(text):
    return re.sub(r"\[@([a-z0-9]+)\]", lambda m: citation(m[1]), text)


rows = []
for a in catalogue["archetypes"]:
    refs = " ".join(citation(k) for k in a["sources"])
    rows.append(
        f"| **{a['name']}** | {a['maturity']}. {a['examples']}. {refs} | {a['mechanism']} {a['simulation']} | {a['limits']} **Scope:** {a['priority']}. |"
    )
table = (
    "| Hardware class | Evidence and examples | Mechanics to represent | Limits and proposed scope |\n|---|---|---|---|\n"
    + "\n".join(rows)
)
refs = []
for s in sources:
    refs.append(
        f'<a id="source-{s["id"]}"></a>\n\n**{by_id[s["id"]]["number"]}. {s["authors"]}.** [{s["title"]}]({s["url"]}). {s["date"]}. **Evidence:** {s["type"]}. **Access:** {s["access"]}. **Scope:** {s["scope"]}'
    )
source = (ROOT / "report-source.md").read_text()
used = set(re.findall(r"\[@([a-z0-9]+)\]", source)) | {
    k for a in catalogue["archetypes"] for k in a["sources"]
}
assert used == set(by_id), (used - set(by_id), set(by_id) - used)
source = cite(source.replace("{{CATALOGUE}}", table).replace("{{REFERENCES}}", "\n\n".join(refs)))
architecture_text = """```text
Current observations + eligible forecasts + mission requirements
                              ↓
             Plant and service-state estimates
                              ↓
   Service scheduler ↔ Plant dispatch planner
          ↓                 ↓
   Work orders        Electricity / operating commitments
          ↓                 ↓
   Task executive ← Prerequisites and resource checks
          ↓
   Robot / fixed station / human crew → Physical effects
          ↓                                  ↓
   Timestamped observations ← Acceptance test / plant

Docks, tools, spares, references and access constrain each task.
Every attempted task → Resource ledger + human work + evidence.
```"""
architecture_html = """<figure class="architecture" aria-label="Proposed field operations architecture">
<div class="architecture-top">Current observations, eligible forecasts and mission requirements</div><div class="arrow" aria-hidden="true">↓</div>
<div class="architecture-row"><div>Plant and service estimates<small>State, uncertainty and usable resources</small></div><span aria-hidden="true">→</span><div>Service scheduler<small>Inspection, maintenance and work orders</small></div><span aria-hidden="true">↔</span><div>Dispatch planner<small>Power allocation and operating commitments</small></div></div>
<div class="arrow" aria-hidden="true">↓</div><div class="architecture-top">Task executive checks access, operating state, capability and resources</div><div class="arrow" aria-hidden="true">↓</div>
<div class="architecture-row"><div>Mobile robot<small>Travel, sensing and compatible tools</small></div><span></span><div>Fixed hardware<small>Sampling, calibration and remote actuation</small></div><span></span><div>Human service<small>Remote assistance, site work and replenishment</small></div></div>
<div class="arrow" aria-hidden="true">↓</div><div class="architecture-top">Physical effects → Acceptance checks → New observations and estimates</div>
<figcaption>Proposed task-level simulation. Docks, tools, spares, references and access constrain each task. All attempts record resource use, human work and evidence; motion completion alone does not establish restoration.</figcaption></figure>"""
markdown = source.replace("{{ARCHITECTURE}}", architecture_text)
assert not re.search(r"\{\{|\[@", markdown)
(ROOT / "report.md").write_text(markdown)
body = (
    MarkdownIt("commonmark", {"html": True})
    .enable("table")
    .render(source.replace("{{ARCHITECTURE}}", architecture_html))
)
body = re.sub(
    r'<a href="([^"]+)">(\d+): ([^<]+)</a>',
    lambda m: (
        f'<sup><a href="{m[1]}" title="{html.escape(m[3], quote=True)}" aria-label="Source {m[2]}: {html.escape(m[3], quote=True)}">[{m[2]}]</a></sup>'
    ),
    body,
)
toc = []


def heading(m):
    slug = "section-" + str(len(toc) + 1)
    toc.append((slug, re.sub("<[^>]*>", "", m[1])))
    return f'<h2 id="{slug}">{m[1]}</h2>'


body = re.sub(r"<h2>(.*?)</h2>", heading, body)
body = re.sub(
    r"<table>(.*?)</table>",
    r'<div class="table-scroll" tabindex="0"><table>\1</table></div>',
    body,
    flags=re.S,
)
body = body.replace(
    "<table>\n<thead>\n<tr>\n<th>Hardware class</th>",
    '<table id="hardware">\n<thead>\n<tr>\n<th>Hardware class</th>',
)
assert 'id="hardware"' in body
search = '<div class="catalogue-filter"><label for="hardware-search">Filter the hardware catalogue</label><div><input id="hardware-search" type="search" placeholder="Try cleaning, prototype or sampling"><button id="clear-search" type="button">Show all</button></div><p id="filter-status" role="status" aria-live="polite">14 hardware classes</p></div>'
body = body.replace(
    '<div class="table-scroll" tabindex="0"><table id="hardware">',
    search + '<div class="table-scroll" tabindex="0"><table id="hardware">',
)
nav = "".join(f'<a href="#{slug}">{html.escape(label)}</a>' for slug, label in toc)
style = (ROOT / "style.css").read_text()
script = """const field=document.getElementById('hardware-search');
const rows=[...document.querySelectorAll('#hardware tbody tr')];
function filter(){const q=field.value.toLocaleLowerCase().trim();let count=0;for(const r of rows){r.hidden=!r.textContent.toLocaleLowerCase().includes(q);if(!r.hidden)count++;}document.getElementById('filter-status').textContent=`${count} of ${rows.length} hardware classes`;}
field.addEventListener('input',filter);document.getElementById('clear-search').addEventListener('click',()=>{field.value='';filter();field.focus();});"""
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Research and simulation design for field robotics, inspection, remote maintenance and service economics."><title>Field robotics and remote maintenance for Dispatch Lab</title><style>{style}</style></head><body><a class="skip" href="#report">Skip to report</a><div class="layout"><aside aria-label="Report navigation"><strong>Contents</strong><nav>{nav}</nav><div class="downloads"><a href="report.md">Markdown report</a><a href="catalogue.json">Hardware catalogue</a><a href="sources.json">Source records</a><a href="../autonomous-management/report.html">Earlier autonomy research</a></div></aside><main id="report">{body}<p class="footer">Research assessment · 10 September 2026 · Proposed software models only. This report changes no running simulation. Reading works offline; external references require a connection.</p></main></div><script>{script}</script></body></html>"""
(ROOT / "report.html").write_text(page)
files = [
    "methane/config.py",
    "methane/simulation.py",
    "methane/sensing.py",
    "methane/costing.py",
    "methane/solar.py",
    "docs/studies.md",
]
verification = dict(
    as_of="2026-09-10",
    sources=len(sources),
    hardware_classes=len(rows),
    sections=len(toc),
    report_words=len(markdown.split()),
    html_sha256=hashlib.sha256(page.encode()).hexdigest(),
    checked=dict(source_ids_resolve=True, all_sources_referenced=True, no_unexpanded_markers=True),
    scope="Report rendering and reference identity checks; not physical validation or robot qualification.",
    local_review_sha256={
        p: hashlib.sha256((ROOT.parent.parent / p).read_bytes()).hexdigest() for p in files
    },
)
(ROOT / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
print(json.dumps({k: v for k, v in verification.items() if k != "local_review_sha256"}))
