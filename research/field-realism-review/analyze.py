"""Retain all cases; replace only the documented misconfigured portable arms."""
import json,hashlib,csv,statistics,collections
from pathlib import Path
R=Path(__file__).resolve().parent;E=R/'experiments'
allrows=[];groups=[]
for folder in ['primary','boundary','portable-correction','portable-boundary-correction']:
 root=E/folder
 plan=json.loads((root/'cases.json').read_text())
 for packet in plan:
  path=root/'cases'/packet['case_id']/'summary.json'
  if not path.exists():
   allrows.append(dict(case=packet['case'],status='incomplete',suite=folder,path=str(path.relative_to(R))));continue
  s=json.loads(path.read_text());s['suite']=folder;s['path']=str(path.relative_to(R));s['use']='retained setup error' if folder in ('primary','boundary') and s['case']['arm']=='portable-wet' else 'comparison'
  if s.get('archive'):
   assert hashlib.sha256((path.parent/s['archive']).read_bytes()).hexdigest()==s['archive_sha256']
  sc=s.get('service_cost',{});m=s.get('metrics',{});end=s.get('ending_service',{}) or {}
  exorders=end.get('executive',{}).get('orders',[])
  s['unresolved_orders']=[{'order_id':o['order_id'],'action':o['action'],'status':o['status']} for o in exorders if o['status'] not in ('complete','completed','cancelled')]
  s['service_quantities']=sc.get('quantities',{});allrows.append(s)
used=[s for s in allrows if s.get('use')=='comparison']
for hours in [48,240]:
 bins=collections.defaultdict(list)
 for s in used:
  if s.get('hours')==hours:
   c=s['case'];bins[(c['family'],str(c.get('power')),str(c.get('soil')),c.get('condition',''),c['arm'])].append(s)
 for key,ss in sorted(bins.items()):
  row=dict(hours=hours,family=key[0],power=key[1],soil=key[2],condition=key[3],arm=key[4],n=len(ss),case_paths=[s['path'] for s in ss])
  measures={'methane_kg':[s['methane_kg'] for s in ss],'allocated_eur':[s['costs']['total_eur'] for s in ss],'decision_eur':[s['costs']['variable_and_wear_eur'] for s in ss],'contribution_eur':[s['costs']['assumed_contribution_eur'] for s in ss],'service_allocated_eur':[s['service_cost']['total_eur'] for s in ss],'fault_hours':[s['metrics']['fault_active_hours'] for s in ss],'available_dc_kwh':[s['available_dc_kwh'] for s in ss],'curtailment_kwh':[s['curtailment_kwh'] for s in ss],'human_visits':[s['service_quantities'].get('human_visits',0) for s in ss],'crew_hours':[s['service_quantities'].get('crew-hours',0) for s in ss],'travel_hours':[s['service_quantities'].get('crew-travel-hours',0) for s in ss],'unresolved':[len(s['unresolved_orders']) for s in ss]}
  for name in ['battery_kwh','h2_kg','co2_kg','temperature_c']:measures['ending_'+name]=[s['ending_plant'][name] for s in ss]
  for name,values in measures.items():row[name]={'mean':statistics.mean(values),'min':min(values),'max':max(values)}
  groups.append(row)
# Exactly matched comparisons; a zero production difference has no methane-price break-even.
pairs=[]
for s in used:
 if s['case']['arm'] in ('no-service','no-cleaning'):continue
 c=s['case'];bs=[b for b in used if b['hours']==s['hours'] and all(b['case'].get(k)==c.get(k) for k in ('family','seed','power','soil','condition')) and b['case']['arm'] in ('no-service','no-cleaning')];assert len(bs)==1
 b=bs[0];dm=s['methane_kg']-b['methane_kg'];dc=s['costs']['variable_and_wear_eur']-b['costs']['variable_and_wear_eur']
 pairs.append(dict(case=s['path'],baseline=b['path'],delta_methane_kg=dm,delta_decision_cost_eur=dc,delta_allocated_cost_eur=s['costs']['total_eur']-b['costs']['total_eur'],break_even_methane_eur_per_kg=dc/dm if dm>1e-9 else None,interpretation='No additional methane in this trace; no finite positive-output methane-price break-even' if abs(dm)<1e-9 else 'Conditional fixed-trace price only'))
weather=[]
for p in sorted((R.parent.parent/'runs/weather').glob('*.json')):
 w=json.loads(p.read_text());r=w.get('request',{});h=w.get('raw',{}).get('hourly',{})
 weather.append(dict(path=str(p.relative_to(R.parent.parent)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),request=r,url=w.get('url'),retrieved_at=w.get('retrieved_at'),variables=list(h),start=h.get('time',[None])[0],end=h.get('time',[None])[-1],missing_service_fields=[k for k in ('wind_speed_10m','precipitation') if k not in h]))
(E/'weather-inventory.json').write_text(json.dumps(weather,indent=2)+'\n')
output=dict(schema_version='realism-analysis/1',all_cases=len(allrows),comparison_cases=len(used),retained_setup_error_cases=sum(s.get('use')=='retained setup error' for s in allrows),statuses=dict(collections.Counter(s['status'] for s in allrows)),audits_passed=sum(s.get('audit_passed',False) for s in allrows),audit_assertions=sum(s.get('independent_checks',0) for s in allrows),groups=groups,matched_differences=pairs)
(E/'analysis.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
# Full values/terminal service structures remain in the linked immutable summaries.
fields=['suite','case_id','status','use','hours','methane_kg','available_dc_kwh','curtailment_kwh','service_bus_kwh','audit_passed','path']
with (E/'case-index.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:s.get(k) for k in fields} for s in allrows)
print(json.dumps({k:v for k,v in output.items() if k not in ('groups','matched_differences')},indent=2))
for g in groups:
 if g['hours']==48:print(g['family'],g['condition'] or g['power']+'/'+g['soil'],g['arm'],'service',round(g['service_allocated_eur']['mean'],2),'fault',g['fault_hours'],'dc',round(g['available_dc_kwh']['mean'],1),'endh2',round(g['ending_h2_kg']['mean'],2))
