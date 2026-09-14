"""Read-only release publication from frozen numerical operands and verification receipts."""
import argparse
import base64
import hashlib
import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from methane.qualification_analysis import compact, numerical_spreads, comparisons as paired_operands
from methane.provenance import LOADED_FILES, LOADED_SOURCE

ROOT=Path(__file__).resolve().parent

def trace_projection(row):
    """Retain numerical operands; omit repeated narrative already explained in the essay."""
    recovery=row.get('recovery') or {}
    appointment=recovery.get('test_appointment')
    if appointment:appointment={k:v for k,v in appointment.items() if k!='scope'}
    obligation=recovery.get('recovery_obligation')
    if obligation:
        obligation={k:v for k,v in obligation.items() if k not in ('scope','hour','appointment_forecast_source')}
        obligation['remaining']={k:v for k,v in obligation['remaining'].items() if k!='scope'}
    solver={k:v for k,v in row['solver'].items() if k!='message'}
    return dict(hour=row['hour'],time=row['time'],estimate=row['diagnosis']['capacity_kw'],truth=row['truth_capacity_kw'],requested=row['requested']['electrolyser_kw'],applied=row['applied']['electrolyser_kw'],methane=row['applied']['methane_kg'],battery=row['state']['battery_kwh'],h2=row['state']['h2_kg'],co2=row['state']['co2_kg'],temperature=row['state']['temperature_c'],status=recovery.get('status'),appointment=appointment,obligation=obligation,forecast=row['forecast_source'],solver=solver)

def number(x):
    if x is None:return '—'
    if isinstance(x,(int,float)):return f'{x:,.2f}'
    return str(x)

def write(source,destination):
    original=json.loads((ROOT.parent/'autonomy-qualification/report.json').read_bytes())
    previous={(c['study_id'],c['case_id']):c for c in original['cases']}
    raw=json.loads(source.read_bytes());cases=[compact(c) for c in raw['cases']]
    matched=[c for c in raw['cases'] if c['group'].startswith('matched-')]
    repeat_integrity=numerical_spreads(matched)
    pairing=paired_operands(matched)
    assert all(c['same_environment'] and c['same_source'] for c in pairing)
    for c,r in zip(cases,raw['cases']):
        if c['group']=='saved-failures':
            before=previous[(c['label']['original_study'],c['label']['original_case'])]
            c['original']={k:before[k] for k in ('study_id','case_id','outcome','metrics','source')}
        c['trace']=[trace_projection(t) for t in r['timeline']]
        c['terminal_obligations']=(r['timeline'][-1].get('service_control') or {}).get('obligations') if r['timeline'] else None
        # Public ending resources and orders are retained without duplicating all histories.
        terminal=c.pop('ending_services',None) or {}
        c['ending_services']={k:terminal.get(k) for k in ('robots','service_kits','cleaning_kits','calibration_kits','orders','support','hardware','surface')}
        c['ending_services']['resource_accounting']=(terminal.get('executive') or {}).get('resources')
    groups=defaultdict(list)
    for c in cases:
        if c['group'].startswith('matched-'):
            groups[(c['group'],c['label']['seed'],c['controller'])].append(c)
    repeats=[]
    for (group,seed,controller),cs in groups.items():
        metrics={}
        for k in ('methane_kg','assumed_contribution_eur','capacity_confirmed_hour','fallbacks','limited_solves'):
            values=[c['metrics'].get(k) for c in cs];valid=[x for x in values if x is not None]
            metrics[k]=dict(values=values,minimum=min(valid) if valid else None,maximum=max(valid) if valid else None,missing=len(values)-len(valid))
        repeats.append(dict(group=group,seed=seed,controller=controller,cases=[c['case_id'] for c in cs],metrics=metrics))
    # Conservative finite-sample separation, not confidence intervals or statistical significance.
    comparisons=[]
    for group in ('matched-local','matched-joint'):
        controllers=list(dict.fromkeys(r['controller'] for r in repeats if r['group']==group))
        for a in controllers:
            for b in controllers[controllers.index(a)+1:]:
                for metric in ('methane_kg','assumed_contribution_eur'):
                    by_seed=[]
                    for seed in (7,17,29):
                        aa=next(r for r in repeats if r['group']==group and r['seed']==seed and r['controller']==a)['metrics'][metric]
                        bb=next(r for r in repeats if r['group']==group and r['seed']==seed and r['controller']==b)['metrics'][metric]
                        lo=bb['minimum']-aa['maximum'] if aa['minimum'] is not None and bb['minimum'] is not None else None
                        hi=bb['maximum']-aa['minimum'] if lo is not None else None
                        by_seed.append(dict(seed=seed,alternative_minus_baseline_min=lo,alternative_minus_baseline_max=hi))
                    conclusion='not separated across every seed'
                    if all(x['alternative_minus_baseline_min'] is not None and x['alternative_minus_baseline_min']>1e-6 for x in by_seed):conclusion='alternative exceeds baseline numerical range in every declared seed'
                    elif all(x['alternative_minus_baseline_max'] is not None and x['alternative_minus_baseline_max']<-1e-6 for x in by_seed):conclusion='baseline exceeds alternative numerical range in every declared seed'
                    comparisons.append(dict(group=group,baseline=a,alternative=b,metric=metric,seeds=by_seed,conclusion=conclusion))
    before=Counter(c['original']['outcome'] for c in cases if 'original' in c)
    after=Counter(c['outcome'] for c in cases if 'original' in c)
    columns=list(next(t for c in cases for t in c['trace']))
    for c in cases:c['trace']=[[t[k] for k in columns] for t in c['trace']]
    publication=dict(version='release-one-publication/1',trace_columns=columns,trace_scope='Each trace row is an array in trace_columns order. Selected original numerical operands; repeated scope prose and native solver message omitted. Full records remain in the source operands and preserved periods.',programme=raw['programme'],source_operands=str(source.resolve()),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),numerical_sources=sorted({c['source'] for c in cases}),reporting_source=LOADED_SOURCE['content_hash'],cases=cases,numerical_repeats=repeats,repeat_input_integrity=repeat_integrity,matched_input_differences=pairing,comparisons=comparisons,original_outcomes=dict(before),corrected_outcomes=dict(after),checks=Counter((c['checks'] or {}).get('status','missing') for c in cases))
    if destination.exists() or destination.with_suffix('.json').exists():raise ValueError('Choose a new immutable report destination')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.with_suffix('.json').write_text(json.dumps(publication,ensure_ascii=False,separators=(',',':')))
    esc=html.escape
    table=lambda headings,rows:'<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headings)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(number(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    recovery_table=table(['Outcome','Original v4','Corrected v5'],[(k,before[k],after[k]) for k in sorted(before.keys()|after.keys())])
    repeat_table=table(['Group / seed','Controller','Methane range kg','Contribution range EUR','Confirmation boundaries','Fallback counts'],[(r['group']+' / '+str(r['seed']),r['controller'],f"{number(r['metrics']['methane_kg']['minimum'])}–{number(r['metrics']['methane_kg']['maximum'])}",f"{number(r['metrics']['assumed_contribution_eur']['minimum'])}–{number(r['metrics']['assumed_contribution_eur']['maximum'])}",str(r['metrics']['capacity_confirmed_hour']['values']),str(r['metrics']['fallbacks']['values'])) for r in repeats])
    comparison_table=table(['Group','Baseline','Alternative','Metric','Finite-sample conclusion'],[(r['group'],r['baseline'],r['alternative'],r['metric'],r['conclusion']) for r in comparisons])
    font=base64.b64encode(LOADED_FILES['assets/fonts/DepartureMono-Regular.woff2']).decode()
    interpretation=(ROOT/'interpretation.html').read_text() if (ROOT/'interpretation.html').exists() else '<p>Numerical results are saved; interpretation review is pending.</p>'
    roadmap=(ROOT/'roadmap.html').read_text() if (ROOT/'roadmap.html').exists() else '<p>Updated delivery roadmap is pending.</p>'
    data=json.dumps(publication,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    text='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dispatch Lab · Release 1</title><style>
@font-face{font-family:Departure;src:url(data:font/woff2;base64,FONT)}*{box-sizing:border-box}body{margin:0;background:#222;color:#ffbd69;font:14px/1.85 Departure,monospace}main{max-width:1240px;margin:auto;padding:40px 28px}nav{display:flex;gap:20px;flex-wrap:wrap;border-bottom:1px solid #70502c;padding-bottom:20px}a{color:inherit;text-underline-offset:4px}h1{font-size:38px;line-height:1.35;max-width:950px;margin:54px 0 24px}h2{font-size:24px;margin-top:58px}h3{font-size:18px}p,li{max-width:95ch}li{margin:12px 0}button,select,input{font:inherit;color:inherit;background:#292622;border:1px solid #92602d;padding:10px;max-width:100%}select{width:100%}input[type=range]{width:100%;accent-color:#ffa631}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px}td,th{padding:12px;border-bottom:1px solid #5f462c;text-align:left;vertical-align:top}th{font-weight:normal}.muted{color:#c59b6c;font-size:12px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.8 Departure,monospace;max-height:550px;overflow:auto;border:1px solid #5f462c;padding:16px}svg{width:100%;height:auto}svg text{fill:currentColor;font:12px Departure,monospace}a:focus-visible,button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid #ffe5bd;outline-offset:4px}.controls{display:grid;gap:14px;margin:25px 0}@media(max-width:600px){main{padding:22px 16px}h1{font-size:26px}h2{font-size:21px}}
</style><main><nav><a href="#results">Findings</a><a href="#repeats">Matched comparisons</a><a href="#trace">Inspect an interval</a><a href="#evidence">Evidence and limitations</a><a href="../../docs/roadmap.md">Roadmap</a></nav><p class="muted">Dispatch Lab / Release 1 / hourly research sandbox</p><h1>Qualified reference autonomy</h1><p>A fixed recovery obligation, individual test appointments, executable service explanations and repeatable controller comparisons.</p><p>COUNT declared executions / HOURS completed hourly intervals. All original failed or incomplete outcomes remain in the evidence.</p><section id="results"><h2>What changed, and what the experiments establish</h2>INTERPRETATION<h3>The original version-4 cases, revisited</h3>RECOVERY<p>Every version-4 case in the previous publication is included. Its numerical horizon, budget, seed and environment are retained. The recovery policy version changes; the new source identity is recorded. These are controlled software repetitions, not new weather years or field repairs.</p></section><section id="repeats"><h2>Matched comparisons and numerical variation</h2><p>Common-local comparisons hold service/recovery policy fixed while changing the process objective. Common-joint comparisons hold the version-5 service system fixed between methane and economic MPC. These are separate comparisons. Three event seeds each have three numerical repetitions at the declared 12-hour horizon and one-second process-solver limit; individual service comparisons retain their separately recorded limits.</p>REPEATS<h3>Which differences exceed the sampled numerical variation?</h3>COMPARISONS<p>Range separation is a conservative description of these finite samples, not a confidence interval or a universal controller ranking. Unseparated comparisons remain unresolved. Numerical repeats do not count as additional weather observations.</p></section><section id="trace"><h2>Follow the original decision</h2><label for="case">Saved execution</label><select id="case"></select><label for="hour">Interval <span id="hour-label"></span></label><input id="hour" type="range" min="0" value="0"><svg id="plot" viewBox="0 0 1000 380" role="img" aria-label="Recorded cumulative methane and estimated versus retrospective true capacity"></svg><pre id="operands" tabindex="0"></pre><p class="muted">The plot is recorded playback. Amber capacity is the controller estimate; the pale dashed line is retrospective simulator truth. Truth is not available to the controller. Episode deadlines and individual appointments are distinct operands.</p><h3>Ending resources and unresolved work</h3><pre id="ending" tabindex="0"></pre></section><section id="evidence"><h2>Verification, preservation and limits</h2><p>Independent checks: CHECKS. Physical conservation and causal information boundaries are separate from empirical calibration. Use the Model workspace to inspect the seven new service essays and their applicable evidence.</p><p><a href="report.json">Machine-readable publication</a> · <a href="validation.json">Executed validation and source identities</a> · <a href="walkthrough.json">Comprehension walkthrough</a> · <a href="evidence-plan.json">Consequential evidence gaps</a> · <a href="README.md">Reproduction instructions</a></p><p>No equipment-matched field clock data, thermal calibration, logistics quotations or calibrated repair reliability have been supplied. A human module replacement is not autonomous robotic repair. ERA5 is reanalysis; seasonal persistence and archived forecasts retain different information assumptions. No land consent, certified product acceptance or positive project return is inferred.</p><p>Original numerical operands and source capsules remain in the Sites store. Its export restores saved playback and enables a separate numerical edition. Git preserves this compact write-up and protocol, not the large original datasets. Opening this report needs no network; external source references remain links.</p><p class="muted">Numerical sources: SOURCES<br>Reporting source: REPORTSOURCE<br>Original operand SHA256: OPERANDHASH</p></section></main><script type="application/json" id="data">DATA</script><script>
const data=JSON.parse(document.getElementById('data').textContent),q=id=>document.getElementById(id),num=v=>v==null?'unavailable':typeof v==='number'?v.toLocaleString('en-GB',{maximumFractionDigits:2}):String(v);
data.cases.forEach(c=>{c.trace=c.trace.map(values=>Object.fromEntries(data.trace_columns.map((key,i)=>[key,values[i]])))});
data.cases.forEach((c,i)=>q('case').add(new Option(c.group+' / '+c.label.pair+' / '+c.controller+' / seed '+c.label.seed+' / repeat '+c.label.repetition+' / '+c.outcome,i)));
function draw(){const c=data.cases[Number(q('case').value)],rows=c.trace;q('hour').max=Math.max(0,rows.length-1);const i=Math.min(Number(q('hour').value),rows.length-1),r=rows[i];if(!r){q('plot').innerHTML='';q('operands').textContent='No completed interval. Status: '+c.status;return;}q('hour-label').textContent='H'+r.hour+' / '+r.time;let methane=0;const ps=rows.map(r=>({...r,cumulative:(methane+=r.methane)}));let svg='';[['cumulative','Cumulative methane / kg',0],['estimate','Capacity / kW: estimate and retrospective truth',170]].forEach(([key,title,top])=>{const max=Math.max(1,...ps.map(x=>x[key]),...ps.map(x=>key==='estimate'?x.truth:0));const path=k=>ps.map((x,j)=>(j?'L':'M')+(100+j*870/Math.max(1,ps.length-1)).toFixed(2)+' '+(top+125-x[k]/max*95).toFixed(2)).join(' ');svg+=`<text x="15" y="${top+20}">${title}</text><text x="15" y="${top+70}">${num(ps[i][key])}</text><path d="M100 ${top+125}H970" stroke="#6f5434"/><path d="${path(key)}" fill="none" stroke="#ffa631" stroke-width="2"/>`;if(key==='estimate')svg+=`<path d="${path('truth')}" fill="none" stroke="#e9d9c0" stroke-dasharray="5 4"/>`;});svg+=`<path d="M${100+i*870/Math.max(1,rows.length-1)} 25v280" stroke="#e9d9c0" opacity=".4"/>`;q('plot').innerHTML=svg;q('operands').textContent=JSON.stringify({study:c.study_id,case:c.case_id,source:c.source,...r},null,2);q('ending').textContent=JSON.stringify({plant:c.ending,services:c.ending_services,service_obligations_at_last_decision:c.terminal_obligations,final_estimate:c.final_estimate,metrics:c.metrics,checks:c.checks},null,2);}
q('case').addEventListener('change',()=>{q('hour').value=0;draw()});q('hour').addEventListener('input',draw);draw();
</script></html>'''
    text=text.replace('<a href="../../docs/roadmap.md">Roadmap</a>','<a href="#roadmap">Releases 2 and 3</a>').replace('</section></main><script','</section><section id="roadmap">ROADMAP</section></main><script')
    variables={'FONT':font,'COUNT':str(len(cases)),'HOURS':str(sum(c['hours'] for c in cases)),'INTERPRETATION':interpretation,'ROADMAP':roadmap,'RECOVERY':recovery_table,'REPEATS':repeat_table,'COMPARISONS':comparison_table,'CHECKS':esc(str(dict(publication['checks']))),'SOURCES':esc(', '.join(publication['numerical_sources'])),'REPORTSOURCE':publication['reporting_source'],'OPERANDHASH':publication['source_sha256'],'DATA':data}
    import re
    text=re.sub('|'.join(sorted(variables,key=len,reverse=True)),lambda m:variables[m[0]],text)
    destination.write_text(text)
    return publication

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args();write(a.source,a.destination)
