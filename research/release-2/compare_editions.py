"""Compare the preserved edition with the fresh checkpoint-source programme."""
import json,time
from pathlib import Path
from methane.siting.production import entries,PeriodRows,state,read_blob
from methane.siting.store import Store,digest
root=Path('research/release-2');old=json.loads((root/'4f06ad527fdd4457a540614fa35ab1ac/programme.json').read_text());pointer=json.loads((root/'active-programme.json').read_text());new=json.loads(Path(pointer['path']).read_text());store=Store();target=root/'source-comparison.json'
fields=('hour','requested','applied','state','observations_after','diagnosis_after','lifecycle','field_operations','co2_delivered_kg','co2_rejected_kg','forced_trip')
class FullRows(PeriodRows):
 def part(self,item):
  key=item['period_sha256']
  if key not in self.cache:
   saved=read_blob(self.store,key)
   if saved.get('schema_version')!='site-period-storage/1':raise ValueError('Unknown full-record period')
   self.cache.clear();self.cache[key]=saved['value']['records'][self.controller]
  return self.cache[key]

results=[]
if target.exists():
 saved=json.loads(target.read_text())
 if saved.get('version')=='release-2-source-comparison/2' and saved['after_programme']==new['id']:results=saved['cases']

for group,count in (('seasonal',72),('annual',1)):
 a=next(g for g in old['studies'] if g['key']==group);b=next(g for g in new['studies'] if g['key']==group);before=store.get('study',a['id']);after=store.get('study',b['id'])
 for ac,bc in zip(before['cases'][:count],after['cases'][:count],strict=True):
  if ac['config']!=bc['config'] or ac['environment_id']!=bc['environment_id'] or ac['controller']!=bc['controller']:raise ValueError('Original input pairing changed')
  prior=entries(store,a['id'],ac['case_id']);hours=prior[-1]['next_hour']
  if any(r['group']==group and r['case_id']==ac['case_id'] and r['hours']==hours and r['matched'] for r in results):continue
  while True:
   current=entries(store,b['id'],bc['case_id'])
   if current and current[-1]['next_hour']>=hours:break
   if state(store,b['id'])['status'] in ('invalid','incomplete','cancelled','interrupted'):raise ValueError('Fresh study incomplete; original results retained')
   time.sleep(15)
  ar=FullRows(store,prior,ac['controller']);br=FullRows(store,current,bc['controller']);ah,bh=[],[];different=[]
  for i in range(hours):
   x={k:ar[i][k] for k in fields};y={k:br[i][k] for k in fields};ah.append(digest(x));bh.append(digest(y))
   if ah[-1]!=bh[-1]:different.append(dict(hour=i,fields=[k for k in fields if x.get(k)!=y.get(k)]))
  item=dict(group=group,case_id=ac['case_id'],hours=hours,input_id=digest(dict(config=ac['config'],environment=ac['environment_id'],controller=ac['controller'])),before=digest(ah),after=digest(bh),differences=different,matched=not different);results.append(item)
  value=dict(version='release-2-source-comparison/2',before_programme=old['id'],after_programme=new['id'],before_source=old['source']['content_hash'],after_source=new['source']['content_hash'],cases=results,complete=len(results)==73,passed=all(r['matched'] for r in results),scope='All 72 original Greedy seasonal cases and the 1337-hour saved annual prefix, each rerun from its initial state. Complete physical, observation, service and lifecycle records are compared. This does not qualify unexecuted future intervals or assert deterministic time-limited MPC decisions.')
  target.write_text(json.dumps(value,indent=2));print(group,ac['case_id'],hours,'matched' if item['matched'] else 'DIFFERENT',flush=True)
  if different:raise ValueError('Preserved differences require review')
