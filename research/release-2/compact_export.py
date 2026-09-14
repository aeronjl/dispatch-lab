"""Compact offline reader for preserved studies; numerical source stays unchanged.

One calculation page per controller/interval, with a topic selector. All original
calculation objects are retained. Rendering uses text, not a numerical model.
This adapter's bytes are included alongside the separately identified production
calculation source and the study's original execution source.
"""
import hashlib, html, json, posixpath, zipfile
from pathlib import Path
from methane import studies
from methane.bundle import playback
from methane.documentation import calculation
from methane.evidence import staging, publish_completed
from methane.model_topics import TOPICS
from methane.offline_model import CSS, original_reference, rows, encoded
from methane.provenance import LOADED_CAPSULE, LOADED_FILES, LOADED_SOURCE, digest
from methane.source_capsule import decode

VERSION='dispatch-lab/compact-preservation-reader/1'
SCRIPT="""const data=JSON.parse(document.getElementById('data').textContent),selector=document.getElementById('topic'),body=document.getElementById('values');for(const [key,entry] of Object.entries(data.topics)){const option=document.createElement('option');option.value=key;option.textContent=key;selector.append(option);}function show(){body.replaceChildren();const entry=data.topics[selector.value];for(const [key,value] of entry.readable){const tr=document.createElement('tr');for(const text of [key,value]){const td=document.createElement('td');td.textContent=text;tr.append(td);}body.append(tr);}document.getElementById('context').textContent=entry.note;}selector.addEventListener('change',show);show();"""

def page(title,body,css='model/report.css'):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><link rel="stylesheet" href="'+css+'"><main><h1>'+html.escape(title)+'</h1>'+body+'</main></html>'

def pages(result,archive_href):
    meta=dict(version=VERSION,run_id=result['run_id'],original_source=result.get('provenance',{}).get('source'),original_prices=result.get('decision_cost_version'),reader_production_source=LOADED_SOURCE['content_hash'],reader_adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='Derived offline reading, not new dispatch. Original snapshots are retained. No solver or learning fixture runs here.')
    yield 'model/report.css',(CSS+'select{font:inherit;background:#222;color:inherit;padding:9px;max-width:100%}').encode()
    for name in ('DepartureMono-Regular.woff2','OFL.txt'):yield 'model/'+name,LOADED_FILES['assets/fonts/'+name]
    yield 'model/manifest.json',encoded(meta)
    doc=result.get('documentation');yield 'model/documentation.json',encoded(doc)
    details={k:'<a href="model/documentation.json">Original parameter, interface and evidence metadata</a>' for k in (doc or {}).get('topics',{})}
    intro='<p><a href="playback.html">Recorded playback</a> · <a href="'+html.escape(archive_href,quote=True)+'">Complete original recording</a> · <a href="../../compact-reader-source.py">Reader adapter source</a> · <a href="../../model-report-source.json">Calculation source capsule</a> · <a href="model/manifest.json">Identities</a></p><p>Original explanations and saved examples remain separate from derived calculation tables. Selecting a topic only reveals stored values; no numerical model runs in this reader. Missing original explanations are not reconstructed.</p>'
    examples=[]
    for key,value in result.get('learning_examples',{}).items():
        name='model/example-'+digest(key)[:16]+'.json';yield name,encoded(value)
        metrics=''.join('<li>'+html.escape(str(m['label'])+': '+str(m['value'])+' '+str(m.get('unit','')))+'</li>' for m in value.get('metrics',[]))
        examples.append('<section><h3>'+html.escape(key)+' · saved example</h3><p>'+html.escape(value.get('summary',''))+'</p><ul>'+metrics+'</ul><p><a href="'+name+'">Complete saved inputs, outputs and checks</a></p></section>')
    index=[]
    for controller,records in result['records'].items():
        cid=digest(controller)[:16]
        for hour,record in enumerate(records):
            context=dict(controller=controller,interval=hour,time=record['time'],original_source=meta['original_source'],original_prices=meta['original_prices'],reader_source=LOADED_SOURCE['content_hash'])
            topics={}
            for key in TOPICS:
                value=calculation(result,key,controller,hour)
                note='Retrospective execution calculation; not empirical validation.'
                if key in ('economics','experiments'):note=f'Accumulated through interval {hour}; original dispatch prices remain frozen. Derivation source is separately identified.'
                elif key in ('controllers','weather'):note='Recorded prediction and decision information; no future realised weather substituted.'
                elif key=='diagnosis':note='Recorded observations and before/after estimates. A procedure is not diagnostic confirmation.'
                displayed=value
                if key=='controllers':displayed={**value,'solver':record['decision']['plan'].get('solver'),'trajectory':[dict(offset=i,applied=r['applied'],ending=r['state']) for i,r in enumerate(value.get('trajectory',[]))]}
                topics[key]=dict(note=note,calculation=value,readable=list(rows(displayed)))
            if 'field_operations' in record:
                field=record['field_operations'];displayed={k:v for k,v in field.items() if k not in ('decision','planning_snapshot')}
                topics['service-work']=dict(note='Recorded service decisions, work, accounting and events; applied effects are retrospective. Complete planning snapshots remain in the calculation data.',calculation=field,readable=list(rows(displayed)))
            name=f'{cid}-h{hour:04d}'
            payload=dict(context=context,topics=topics)
            raw=encoded(payload);yield 'model/'+name+'.json',raw
            # JSON text is escaped for a script data block. It is never executed as code.
            data=raw.decode().replace('</','<\\/')
            body='<p><a href="../model-report.html">Model report</a> · <a href="'+name+'.json">Complete calculation data</a></p><p class="context">'+html.escape(controller+' · interval '+str(hour)+' · '+record['time'])+'</p><p class="context">Original execution '+html.escape((meta['original_source'] or {}).get('content_hash','unavailable'))+' · calculation source '+LOADED_SOURCE['content_hash']+'</p><label for="topic">Recorded topic</label> <select id="topic"></select><p id="context"></p><div class="table-scroll" tabindex="0"><table><thead><tr><th>Quantity or field</th><th>Stored value, unit and transformation</th></tr></thead><tbody id="values"></tbody></table></div><noscript><p>Enable local JavaScript to select stored topics, or open the complete calculation JSON above. No network is needed.</p></noscript><script id="data" type="application/json">'+data+'</script><script>'+SCRIPT+'</script>'
            yield 'model/'+name+'.html',page('Recorded calculation',body,css='report.css').encode()
            index.append('<tr><td>'+html.escape(controller)+'</td><td>'+str(hour)+'</td><td>'+html.escape(record['time'])+'</td><td><a href="model/'+name+'.html">Read stored calculations</a></td></tr>')
    body=intro+original_reference(doc,details)+'<h2>Saved learning outputs</h2>'+(''.join(examples) or '<p>No original saved examples.</p>')+'<h2>Recorded calculations</h2><div class="table-scroll" tabindex="0"><table><thead><tr><th>Controller</th><th>Interval</th><th>Time</th><th>Calculation</th></tr></thead><tbody>'+''.join(index)+'</tbody></table></div>'
    yield 'model-report.html',page('Saved model report · compact reader',body).encode()

def export(identifier,destination,root=studies.STORE,report_id=None):
    directory=studies.location(identifier,root)
    if studies.withdrawal(identifier,root):raise ValueError('Withdrawn publication')
    value=studies.stored_report(identifier,root,report_id);capsule=json.loads((directory/'source-capsule.json').read_text());source=decode(capsule);inventory={}
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with staging(destination) as temporary,zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
        def add(name,content):
            if name in inventory:raise ValueError('Duplicate bundle member')
            if isinstance(content,Path):
                with content.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
                z.write(content,name)
            else:
                if isinstance(content,str):content=content.encode()
                sha=hashlib.sha256(content).hexdigest();z.writestr(name,content)
            inventory[name]=sha
        for path in directory.rglob('*'):
            if path.is_file() and path.resolve() not in (temporary.resolve(),destination.resolve()) and '__pycache__' not in path.parts and path.suffix!='.log' and path.name!='cancel':add(identifier+'/'+str(path.relative_to(directory)),path)
        add('study.html',studies.offline_html(value,playback_links=True));add('study.md',studies.markdown(value));add('model-report-source.json',encoded(LOADED_CAPSULE));add('compact-reader-source.py',Path(__file__))
        for n,c in enumerate(value['cases']):
            if not c['entry'].get('archive'):continue
            result=studies.archive_for(identifier,c['entry'],root);prefix='playback/'+c['case_id'];add(prefix+'/playback.html',playback(result,source))
            archive_href=posixpath.relpath(identifier+'/'+c['entry']['archive'],prefix)
            for name,content in pages(result,archive_href):add(prefix+'/'+name,content)
            if (n+1)%12==0:print(identifier,n+1,'cases exported',flush=True)
        for name in ('reference.py','recovery_belief_reference.py','lifecycle_reference.py','recovery_loop_reference.py','autonomy_reference.py','duration_reference.py','retrieval_reference.py','performance_reference.py'):
            if 'methane/'+name in source:add('checker/'+name,source['methane/'+name])
        add('check_study.py',LOADED_FILES['methane/study_bundle_check.py'])
        add('README.txt',f'''Dispatch Lab compact preservation bundle / {VERSION}
Open study.html, then a case's playback/model-report.html offline. Select an interval
and topic to reveal stored calculations; no numerical model runs in the reader.
Original explanation snapshots, saved examples and complete calculation objects
remain available. The compact adapter is in compact-reader-source.py; production
calculation functions are in model-report-source.json. These reading sources are
separate from the study's original execution source under {identifier}/.
All original edition records, manifests, reports, source and archives are retained.
Verify without external packages or network:
  python -I -S check_study.py .
New numerical repetitions use the original source and locked dependencies; never
overwrite or relabel the original study. Hashes establish integrity, not calibration.
''')
        z.writestr('bundle.json',json.dumps(dict(schema_version='dispatch-lab/study-bundle/1',reader_version=VERSION,edition_id=identifier,report_id=value.get('report_id'),files=inventory,archives=[dict(path=identifier+'/'+c['entry']['archive'],status=c['entry']['status']) for c in value['cases'] if c['entry'].get('archive')]),indent=2))
        z.close();return publish_completed(temporary,destination)
