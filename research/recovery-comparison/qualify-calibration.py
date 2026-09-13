"""New audit and calibration edition after the stock-bound checker correction.

Keeps the original audits/fit and original simulated physical records unchanged.
Uses the same predeclared candidate models and availability cutoff.
"""
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from methane.duration_calibration import fit
from methane.evidence import load
from methane.provenance import digest, source_identity
from methane.reference import VERSION, audit

if VERSION!='dispatch-lab/reference/2':
    raise ValueError('Run only after the separately tested numeric stock-bound checker correction')
original=Path(sys.argv[1]).resolve()
old=json.loads((original/'result.json').read_text())
protocol=json.loads((original/'protocol.json').read_text())
folder=original.parent/uuid4().hex
folder.mkdir()
checker_source=source_identity()
audit_folder=ROOT/'build/recovery-comparison/calibration-audits'/folder.name
audit_folder.mkdir(parents=True)
observations=[];sources=[];qualifications=[]
for source in old['source_runs']:
    r=load(source['archive'])
    checked=audit(r)
    artifact=audit_folder/(r['run_id']+'.json')
    with artifact.open('x') as stream:json.dump(checked,stream,indent=2,allow_nan=False)
    qualification=dict(run_id=r['run_id'],original_numerical_source=source['source_hash'],
        original_audit_passed=source['independent_check_passed'],checker=VERSION,
        checker_source_hash=checker_source['content_hash'],passed=checked['passed'],checks=len(checked['checks']),
        failed_checks=[x for x in checked['checks'] if not x['passed']],failures=checked['failures'],
        artifact=str(artifact.relative_to(ROOT)),artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
    qualifications.append(qualification)
    sources.append({**source,'independent_check_passed':checked['passed'],'qualification':qualification})
    print(r['run_id'],checked['passed'],len(qualification['failed_checks']),flush=True)
    if r['status']!='complete' or not checked['passed']:continue
    for row in r['records']['Greedy']:
        for packet in row['field_operations'].get('duration_observations',[]):
            if packet['group'] is None:continue
            item=dict(packet)
            for key in ('id','order_id','asset_id'):item[key]=r['run_id']+'/'+item[key]
            observations.append(item)
protocol['dataset']['observations']=observations
protocol['dataset']['source']['reference']=digest(sources)
protocol['qualification']=dict(original_calibration=str(original.relative_to(ROOT)),
    method='New independent audits use numeric boundary overrun in resource units with the unchanged declared numerical tolerance. No physical action, observation or original evidence is rewritten.',
    predeclared_candidates_unchanged=True,availability_cutoff_unchanged=True,audits=qualifications)
with (folder/'protocol.json').open('x') as stream:json.dump(protocol,stream,indent=2,allow_nan=False)
result=fit(protocol['dataset'],protocol['candidates'],protocol['cutoff'],protocol['bounds'])
result['source_runs']=sources
result['qualification']=protocol['qualification']
result['fitting_source']=checker_source
with (folder/'result.json').open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
print(folder/'result.json',flush=True)
