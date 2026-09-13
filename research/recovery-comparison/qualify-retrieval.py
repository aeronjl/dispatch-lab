"""Record the tested, saved-information conditional retrieval example."""
import copy
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_retrieval_planning import compare, saved_return
from methane.evidence import save
from methane.provenance import digest
from methane.retrieval_reference import audit_candidate

source = saved_return.__wrapped__()
original = copy.deepcopy(source)
run, row, _ = source
archive = save(run, ROOT / 'runs/retrieval-qualification')
outcomes = {}
for name, options in [('qualified return', {}), ('no retrieval', {'selected': False}), ('premature charging', {'due_offset': 1})]:
    answer = compare(source, **options)
    outcomes[name] = dict(answer=answer, checks=audit_candidate(answer, row['field_operations']['planning_snapshot']))
result = dict(version='conditional-retrieval-example/1', source_unchanged=source == original,
              run_id=run['run_id'], source_hash=run['provenance']['source']['content_hash'],
              archive=str(archive), original_hour=row['hour'],
              snapshot_id=digest(row['field_operations']['planning_snapshot']), outcomes=outcomes,
              scope='Counterfactual prediction from an executed observed stranding. Illustrative fixture prices; not a fleet-performance or hardware-capability claim.')
path = Path(__file__).resolve().parent / ('retrieval-' + uuid4().hex + '.json')
path.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
summary={k:v for k,v in result.items() if k != 'outcomes'}
summary['full_artifact'] = path.name
summary['full_artifact_sha256'] = __import__('hashlib').sha256(path.read_bytes()).hexdigest()
summary['outcomes'] = {k:dict(state=v['answer']['state'],checks=v['checks'],
    conditional_returns=v['answer'].get('conditional_returns'),constraints=v['answer'].get('constraints'),
    current_requests=v['answer'].get('current_requests'),
    charging_plan=(v['answer'].get('charging') or {}).get('plan')) for k,v in outcomes.items()}
path.with_name(path.stem+'-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
print(path)
