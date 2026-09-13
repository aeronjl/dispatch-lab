"""Render the authored design and saved evidence. No network or plant execution."""
import html
import json
import re
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent


def build():
    source_record = json.loads((ROOT / 'sources.json').read_text())
    sources = source_record['sources']
    by_id = {s['id']: s for s in sources}
    catalogue = json.loads((ROOT / 'data-catalogue.json').read_text())
    samples = json.loads((ROOT / 'retrieval-20260913/resource-samples.json').read_text())
    authored = (ROOT / 'design.md').read_text()

    def citation(match):
        s = by_id[match[1]]
        return f'<a class="cite" href="{html.escape(s["url"], quote=True)}" title="{html.escape(s["title"], quote=True)}">{html.escape(s["publisher"])} · {html.escape(s["title"])}</a>'

    body = MarkdownIt('commonmark', {'html': True}).enable('table').render(
        re.sub(r'\[\[([\w-]+)\]\]', citation, authored))
    headings = []

    def heading(match):
        title = match[1]
        ident = 'section-' + str(len(headings) + 1)
        headings.append((ident, title))
        return f'<h2 id="{ident}">{title}</h2>'

    body = re.sub(r'<h2>(.*?)</h2>', heading, body)
    body = body.replace('<table>', '<div class="table-scroll" tabindex="0" role="region" aria-label="Comparison table"><table>').replace('</table>', '</table></div>')
    reference_rows = ''.join(
        f'<li id="source-{s["id"]}"><a href="{html.escape(s["url"], quote=True)}">{html.escape(s["title"])}</a><p class="small">{html.escape(s["publisher"])} · {html.escape(s["used_for"])}</p></li>'
        for s in sources)
    body = body.replace('<div id="references"></div>', f'<ol id="references">{reference_rows}</ol>')
    nav = ''.join(f'<a href="#{i}">{t}</a>' for i, t in headings)
    data = json.dumps(dict(sources=by_id, catalogue=catalogue, resource=samples), ensure_ascii=False).replace('<', '\\u003c')
    # Saved numbers remain readable with scripting disabled.
    rows = ''.join(f'<tr><th scope="row">{s["name"]}</th><td>{s["annual"]["E_y"]:.2f}</td></tr>' for s in samples['sites'])
    fallback = f'<noscript><p>JavaScript enables the saved-data explorer. Reference PV yields (kWh per 1 kWp per year):</p><table><thead><tr><th>City anchor</th><th>PVGIS annual yield</th></tr></thead><tbody>{rows}</tbody></table><p>The <a href="data-catalogue.json">data catalogue</a> remains available as a saved file.</p></noscript>'
    body = body.replace('<div id="resource-example" aria-label="Saved PVGIS resource example"></div>', '<div id="resource-example" aria-label="Saved PVGIS resource example"></div>' + fallback)
    output = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sites · Dispatch Lab design</title><link rel="stylesheet" href="report.css"></head>
<body><a class="skip" href="#content">Skip to the design</a>
<header><a href="../README.md">Dispatch Lab / Research</a><span>13 September 2026 · Design proposal</span></header>
<aside><p class="eyebrow">In this design</p><nav aria-label="Report sections">{nav}</nav></aside>
<main id="content"><p class="eyebrow">Sites / From geography to operation</p>{body}</main>
<script type="application/json" id="saved-data">{data}</script><script src="report.js"></script></body></html>'''
    (ROOT / 'report.html').write_text(output)
    print(f'Built report: {len(sources)} sources, {len(catalogue)} connector families, {len(samples["sites"])} saved PVGIS examples')


if __name__ == '__main__':
    build()
