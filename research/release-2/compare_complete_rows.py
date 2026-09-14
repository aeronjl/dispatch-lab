"""Whole-record extension of the earlier selected-field compatibility check.

Every recorded interval field and controller-specific retrospective truth is
compared. Only execution_solver.seconds is excluded; these wall-clock samples are
retained separately. No numerical decisions are rerun or original files modified.
"""
import json,time
from pathlib import Path
from methane.siting.production import entries,read_blob
from methane.siting.store import Store,digest
root=Path('research/release-2');old=json.loads((root/'4f06ad527fdd4457a540614fa35ab1ac/programme.json').read_text());pointer=json.loads((root/'active-programme.json').read_text());new=json.loads(Path(pointer['path']).read_text());store=Store();target=root/'complete-record-comparison.json'
class Rows:
    def __init__(self,items,controller):self.items=items;self.controller=controller;self.key=None;self.value=None
    def get(self,hour):
        item=next(e for e in self.items if e['start_hour']<=hour<e['next_hour']);key=item['period_sha256']
        if key!=self.key:self.value=read_blob(store,key)['value'];self.key=key
        offset=hour-item['start_hour'];row=self.value['records'][self.controller][offset];truth=self.value['retrospective_truth_by_controller'][self.controller][offset]
        return row,truth

def normalized(row):
    if 'execution_solver' not in row or 'seconds' not in row['execution_solver']:raise ValueError('Expected execution timing field missing')
    return {**row,'execution_solver':{k:v for k,v in row['execution_solver'].items() if k!='seconds'}}

results=[]
if target.exists():
    saved=json.loads(target.read_text())
    if saved['after_programme']!=new['id']:raise ValueError('Use a new reading edition')
    results=saved['cases']
for group,count in [('seasonal',72),('annual',1)]:
    a=next(g for g in old['studies'] if g['key']==group);b=next(g for g in new['studies'] if g['key']==group)
    for ac,bc in zip(store.get('study',a['id'])['cases'][:count],store.get('study',b['id'])['cases'][:count],strict=True):
        if ac!=bc:raise ValueError('Complete original case inputs differ')
        prior=entries(store,a['id'],ac['case_id']);current=entries(store,b['id'],bc['case_id']);hours=prior[-1]['next_hour']
        if current[-1]['next_hour']<hours:raise ValueError('Original boundary has not been reached')
        if any(c['group']==group and c['case_id']==ac['case_id'] for c in results):continue
        ar,br=Rows(prior,ac['controller']),Rows(current,bc['controller']);left=[];right=[];differences=[];timings=[];keys=set()
        for hour in range(hours):
            x,xt=ar.get(hour);y,yt=br.get(hour);xn,yn=normalized(x),normalized(y);keys.update(x.keys()|y.keys())
            left.append(digest(dict(record=xn,retrospective_truth=xt)));right.append(digest(dict(record=yn,retrospective_truth=yt)))
            timings.append(dict(hour=hour,before=x['execution_solver']['seconds'],after=y['execution_solver']['seconds']))
            if left[-1]!=right[-1]:differences.append(dict(hour=hour,record_fields=[k for k in xn.keys()|yn.keys() if xn.get(k)!=yn.get(k)],truth_fields=[k for k in xt.keys()|yt.keys() if xt.get(k)!=yt.get(k)]))
        results.append(dict(group=group,case_id=ac['case_id'],hours=hours,input_identity=digest(ac),fields=sorted(keys),before=digest(left),after=digest(right),differences=differences,matched=not differences,timings=timings))
        value=dict(version='release-2-complete-record-comparison/1',before_programme=old['id'],after_programme=new['id'],before_source=old['source']['content_hash'],after_source=new['source']['content_hash'],cases=results,complete=len(results)==73,passed=all(c['matched'] for c in results),excluded_fields=['record.execution_solver.seconds'],scope='Every interval record field, including original decisions, forecasts, curtailment, component calculations and controller-specific retrospective truth. Only measured execution-solver wall-clock duration is excluded from equality and saved separately. All 72 seasonal Greedy cases plus the original 1337-hour annual prefix, rerun from identical complete case inputs. No claim about later intervals or deterministic time-limited MPC.')
        target.write_text(json.dumps(value,indent=2,allow_nan=False));print(group,ac['case_id'],hours,'matched' if not differences else 'DIFFERENT',flush=True)
        if differences:raise ValueError('Retained whole-record differences require review')
