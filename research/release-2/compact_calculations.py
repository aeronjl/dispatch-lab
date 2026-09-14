"""Reconcile every saved compact topic over the preserved 120-hour reader fixture.

This is a reading-adapter check against its identified production calculation
functions, not an independent physical check or a new numerical experiment.
"""
import hashlib,json,time
from pathlib import Path
from methane import studies
from methane.documentation import calculation
from methane.provenance import LOADED_SOURCE

base=Path('research/release-2')
preflight=json.loads((base/'compact-preflight-2.json').read_text())
if preflight['reader_source']!=LOADED_SOURCE['content_hash']:
    raise ValueError('Reconcile with the captured reader source, not a later implementation')
record=json.loads((base/'preservation/recovery.json').read_text())
report=studies.stored_report(record['edition_id'])
entry=next(c for c in report['cases'] if c['entry'].get('archive'))
result=studies.archive_for(record['edition_id'],entry['entry'])
if result['run_id']!=preflight['original_run']:raise ValueError('Reader fixture changed')
def sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
before=sha(result);checks=0;failures=[];intervals=[];start=time.perf_counter()
for path in sorted((Path(preflight['reader'])/'model').glob('*-h*.json')):
    packet=json.loads(path.read_text());context=packet['context'];controller=context['controller'];hour=context['interval']
    if context['reader_source']!=LOADED_SOURCE['content_hash']:raise ValueError('Mixed derivation sources')
    for key,saved in packet['topics'].items():
        expected=result['records'][controller][hour]['field_operations'] if key=='service-work' else calculation(result,key,controller,hour)
        checks+=1
        if saved['calculation']!=expected:failures.append(dict(controller=controller,hour=hour,topic=key))
    intervals.append(dict(controller=controller,hour=hour,topics=len(packet['topics']),saved_packet_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
unchanged=before==sha(result)
receipt=dict(version='release-2-compact-calculation-check/1',original_run=result['run_id'],original_source=preflight['original_source'],reader_source=LOADED_SOURCE['content_hash'],adapter_sha256=preflight['adapter_sha256'],checks=checks,interval_count=len(intervals),failures=failures,source_record_unchanged=unchanged,elapsed_seconds=time.perf_counter()-start,passed=not failures and unchanged and len(intervals)==sum(map(len,result['records'].values())),intervals=intervals,scope='Every stored topic object at every interval in the preserved 120-hour reader fixture matches the identified production calculation function, including accumulated costs, original forecast plans, observations and complete service-work snapshots. This checks the reading adapter; independent physics and whole-bundle integrity remain separate claims.')
(base/'compact-calculations.json').write_text(json.dumps(receipt,indent=2,allow_nan=False))
print(json.dumps({k:v for k,v in receipt.items() if k!='intervals'}),flush=True)
if not receipt['passed']:raise SystemExit(1)
