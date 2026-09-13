import json,re,base64,html
from pathlib import Path
from markdown_it import MarkdownIt
R=Path(__file__).resolve().parent
S=json.loads((R/'sources.json').read_text())['items'];sm={s['id']:s for s in S}
F=json.loads((R/'capabilities.json').read_text())['items'];A=json.loads((R/'assumptions.json').read_text())['items'];result=json.loads((R/'experiments/analysis.json').read_text())
def cite(ids):return ' '.join(f'[{i}]' for i in ids)
def table(head,rows):return '\n'+'| '+' | '.join(head)+' |\n| '+' | '.join('---' for _ in head)+' |\n'+''.join('| '+' | '.join(str(v).replace('|','/') for v in row)+' |\n' for row in rows)+'\n'
def num(g,k):return f'{g[k]["mean"]:,.2f}'
clean=[]
for arm in ['no-cleaning','condition-cleaner','portable-wet']:
 g=next(g for g in result['groups'] if g['hours']==48 and g['family']=='cleaning' and g['power']=='1000' and g['soil']=='0.1' and g['arm']==arm)
 clean.append([arm,num(g,'available_dc_kwh'),num(g,'service_allocated_eur'),num(g,'allocated_eur'),num(g,'contribution_eur'),num(g,'human_visits')])
recovery=[]
for condition in ['resettable-trip','equipment-damage','reset-unavailable','crew-unavailable']:
 for arm in ['no-service','human-only','fixed-assisted','mobile-assisted']:
  g=next(g for g in result['groups'] if g['hours']==48 and g['condition']==condition and g['arm']==arm)
  fh=g['fault_hours'];recovery.append([condition,arm,f'{fh["mean"]:.1f} ({fh["min"]:.0f}–{fh["max"]:.0f})',num(g,'human_visits'),num(g,'service_allocated_eur'),num(g,'allocated_eur')])
ft=table(['Family / maturity','Supported task and boundary','Required support / current model'],[[f'**{f["review_id"]} · {f["name"]}**<br>{f["feasibility"]}',f'{f["permitted_scope"]}<br>**Unavailable:** {f["unavailable_scope"]}<br>{cite(f["sources"])}',f'{f["prerequisites"]}<br>{f["support"]}<br>**Model:** {f["current_model"]}'] for f in F])
assumptions=[]
for a in A:
 paths='; '.join(f'`{x["path"]}` = {x["default"]}' for x in a['config_bindings'])
 assumptions.append(f'''### {a['id']} · {a['claim']}

**Priority {a['priority']} · {a['role']}.** Current assumption: {a['current']}.

**Evidence or gap:** {a['range_or_gap']} {cite(a['sources'])}

**Consequence:** {a['consequence']} **Required:** {a['required_change_or_evidence']}

**Check:** {a['independent_check']}. Binding: {paths or a['binding']}.
''')
sources='\n\n'.join(f'''<a id="source-{s['id'].lower()}"></a>

**{s['id']} · [{s['title']}]({s['url']})** — {s['evidence_type']}; {s['publication']}. Accessed {s['accessed']}. {s['access']}. {s['scope']}''' for s in S)
md=(R/'report-source.md').read_text().replace('{{CLEANING_TABLE}}',table(['Arm','Available DC kWh','Service allocation €','Plant + service allocation €','Operating contribution €','Visits'],clean)).replace('{{RECOVERY_TABLE}}',table(['Condition','Arm','Fault hours mean (range)','Visits','Service allocation €','Total allocation €'],recovery)).replace('{{FAMILY_TABLE}}',ft).replace('{{ASSUMPTIONS}}','\n'.join(assumptions)).replace('{{SOURCES}}',sources)
for s in S:md=md.replace(f'[{s["id"]}]',f'[{s["title"]}]({s["url"]})')
(R/'report.md').write_text(md)
body=MarkdownIt('commonmark',{'html':True}).enable('table').render(md)
toc=[]
def heading(m):
 label=re.sub('<[^>]+>','',m.group(1));slug='section-'+str(len(toc)+1);toc.append((slug,label));return f'<h2 id="{slug}">{m.group(1)}</h2>'
body=re.sub(r'<h2>(.*?)</h2>',heading,body)
body=body.replace('<table>','<div class="table-scroll" tabindex="0" aria-label="Scrollable comparison table"><table>').replace('</table>','</table></div>')
font=base64.b64encode((R.parent.parent/'assets/fonts/DepartureMono-Regular.woff2').read_bytes()).decode()
style='''
:root{color-scheme:dark;--bg:#20201e;--panel:#282824;--ink:#ded9c9;--amber:#ffad36;--muted:#b7b29f;--line:#666047}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}body{margin:0;background:var(--bg);color:var(--ink);font:16.5px/1.7 Departure,monospace}a{color:var(--amber);text-underline-offset:4px;overflow-wrap:anywhere}a:hover{color:#ffd391}a:focus-visible,button:focus-visible,.table-scroll:focus-visible{outline:2px solid var(--amber);outline-offset:5px}nav{position:fixed;left:30px;top:35px;width:202px;font-size:12px;line-height:1.6}nav a{display:block;margin:0 0 15px;color:var(--muted);text-decoration:none}nav .brand{color:var(--amber);letter-spacing:2px;margin-bottom:36px}main{margin:60px 6vw 100px 278px;max-width:1120px}h1{font-size:44px;line-height:1.15;font-weight:normal;letter-spacing:-1px;max-width:760px;color:var(--amber);margin:0 0 24px}h2{font-size:25px;line-height:1.3;font-weight:normal;color:var(--amber);margin:80px 0 28px;border-top:1px solid var(--line);padding-top:25px}h3{font-size:19px;color:var(--amber);font-weight:normal;margin:42px 0 18px}p,li{max-width:850px}p{margin:0 0 22px}li{margin:10px 0}strong{font-weight:normal;color:#fff0cc}code{font:13px Departure,monospace;overflow-wrap:anywhere;background:var(--panel);padding:2px 4px}table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.7}td,th{border-bottom:1px solid var(--line);padding:14px 12px;text-align:left;vertical-align:top;min-width:90px}th{color:var(--amber);font-weight:normal;background:var(--panel)}td:first-child{min-width:150px}td a{font-size:11px}.table-scroll{overflow:auto;margin:28px 0 30px;border:1px solid var(--line)}.table-scroll:has(td:nth-child(3):last-child) table{min-width:800px}.topbar{font-size:11px;letter-spacing:2px;color:var(--muted);margin-bottom:45px}.menu{display:none}footer{font-size:12px;color:var(--muted);margin-top:70px;border-top:1px solid var(--line);padding-top:25px}.skip{position:absolute;left:-999px}.skip:focus{left:20px;top:10px;z-index:10;background:var(--bg)}@media(max-width:1050px){nav{width:160px;left:22px}main{margin-left:212px;margin-right:30px}h1{font-size:36px}}@media(max-width:720px){body{font-size:15px}main{margin:75px 22px 60px}h1{font-size:32px}h2{font-size:23px;margin-top:60px}nav{display:none;position:fixed;inset:48px 0 0;width:auto;padding:20px;background:var(--bg);overflow:auto;z-index:4}nav.open{display:block}nav a{font-size:15px}.menu{display:block;position:fixed;top:12px;right:18px;z-index:5;background:var(--bg);border:1px solid var(--line);color:var(--amber);font:13px Departure;padding:8px 12px}.topbar{font-size:10px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}@media print{nav,.menu{display:none}main{margin:0;max-width:none}body{background:white;color:black;font-size:10pt}h1,h2,h3,a,strong{color:black}h2{break-before:page}table{font-size:8pt}.table-scroll{overflow:visible}code{color:black;background:white}a{word-break:break-word}}
'''
nav=''.join(f'<a href="#{slug}">{html.escape(label)}</a>' for slug,label in toc)
page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Field operations — realism review · Dispatch Lab</title><style>@font-face{font-family:Departure;src:url(data:font/woff2;base64,'+font+')}'+style+'</style></head><body><a class="skip" href="#report">Skip to report</a><button class="menu" aria-controls="index" aria-expanded="false">Contents</button><nav id="index" aria-label="Report contents"><div class="brand">DISPATCH LAB<br>REALISM REVIEW</div>'+nav+'</nav><main id="report"><div class="topbar">RESEARCH / FIELD OPERATIONS / 12 SEPTEMBER 2026</div>'+body+'<footer>Independent arithmetic ≠ empirical validation. Original model and archives preserved.</footer></main><script>const b=document.querySelector(".menu"),n=document.querySelector("nav");b.onclick=()=>{const o=n.classList.toggle("open");b.setAttribute("aria-expanded",o)};n.addEventListener("click",e=>{if(e.target.closest("a")){n.classList.remove("open");b.setAttribute("aria-expanded","false")}});document.addEventListener("keydown",e=>{if(e.key==="Escape"&&n.classList.contains("open")){n.classList.remove("open");b.setAttribute("aria-expanded","false");b.focus()}});</script></body></html>'
(R/'report.html').write_text(page)
print('Report words:',len(md.split()),'HTML bytes',len(page),'topics',len(toc))
