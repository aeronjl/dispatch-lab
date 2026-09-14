"""Collect exact qualification artifacts without promoting earlier source evidence."""
import hashlib,json,re
from pathlib import Path
from methane.provenance import LOADED_SOURCE,LOADED_FILES
from methane.source_capsule import decode
from methane.siting.store import Store

ROOT=Path('research/release-2');root=Path('build/engineering/current')
def read(p):return json.loads(Path(p).read_text())
def artifact(p):
    p=Path(p);return dict(path=str(p),sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),bytes=p.stat().st_size)
pointer=read(ROOT/'active-programme.json');programme=read(pointer['path']);study=programme['studies'][0]['id']
old=decode(read(Path('runs/sites/execution')/study/'source-capsule.json'))
changed=[key for key in sorted(old.keys()|LOADED_FILES.keys()) if old.get(key)!=LOADED_FILES.get(key)]
allowed={'.gitignore','docs/component-catalogue.json','tests/browser/lifecycle.spec.cjs','tests/browser/uncertainty.spec.cjs'}
if set(changed)-allowed:raise ValueError('Unreviewed source difference: '+str(set(changed)-allowed))
evidence=read(root/'evidence-catalogue.json');docs=read('build/model/evidence.json');browser=read(root/'browser-tests.json');recorded=read(root/'browser-recorded.json');active=read(root/'browser-active.json');lc=read('build/release-2/lifecycle-performance.json');model=read('build/model/active-batch-performance.json');rerun=read('build/release-2/offline/recomputation.json')
node=Path('/tmp/r2-node-release.log').read_text();tests=int(re.search(r'(?:#|ℹ) tests (\d+)',node)[1]);failed=int(re.search(r'(?:#|ℹ) fail (\d+)',node)[1])
checks=dict(source=programme['source']['content_hash']==LOADED_SOURCE['content_hash'],component_evidence=evidence['passed'],model_topics=docs['source_matches'] and all(x['status']=='passed' for x in docs['topics'].values()),node=tests==89 and failed==0,lifecycle_latency=all(v['input_p95_ms']<=200 and v['render_p95_ms']<=10 for v in lc['results'].values()),battery_learning_latency=model['preview_p95_ms']<=200 and model['render_p95_ms']<=10,recorded_rerun=rerun['source_matches'] and rerun['independent_reference_passed'] and rerun['status']=='complete')
value=dict(version='release-2-qualification/1',source=LOADED_SOURCE['content_hash'],execution_revision=programme['source']['revision'],reading_revision=LOADED_SOURCE['revision'],capsule_changes=changed,capsule_change_scope='No numerical source or rendering implementation changed after programme freeze. Final capsule adds browser assertions/reviewed image tests, generated topic-index metadata and ignore rules. Original study capsule remains intact.',passed=all(checks.values()),checks=checks,python=next(c for c in evidence['checks'] if c['name']=='python'),node=dict(tests=tests,failed=failed),browser=browser['stats'],recorded_browser=recorded['stats'],model_topics={k:v['status'] for k,v in docs['topics'].items()},interactive=dict(solar=active,battery=model,lifecycle=lc),numerical_rerun={k:v for k,v in rerun.items() if k not in ('recorded_environment','recomputed_environment')},artifacts=[artifact(p) for p in (root/'pytest.xml',root/'evidence-catalogue.json',root/'browser-tests.json',root/'browser-recorded.json',root/'browser-active.json',root/'formal.json',root/'mutations.json',root/'performance-gates.json',root/'offline-check.json',root/'recomputation.json','build/model/evidence.json','build/release-2/lifecycle-performance.json')],limitations=['The full default browser run skips optional fixture-specific checks; four recorded lifecycle/lineage/offline checks ran separately.','Formal checks cover four declared bounded state models, not the complete plant or lifecycle.','The comprehension walkthrough is agent-authored, not a participant study.','These checks do not establish empirical calibration or safety certification.'])
(ROOT/'qualification.json').write_text(json.dumps(value,indent=2,allow_nan=False));print(json.dumps(dict(passed=value['passed'],checks=checks,changes=changed)))
