"""Build compact, inspectable report data from preserved receipts, never run a model."""
import copy, hashlib, json
from pathlib import Path
ROOT=Path('research/release-2')

def read(path,default=None):return json.loads(Path(path).read_text()) if Path(path).exists() else default

def build():
    pointer=read(ROOT/'active-programme.json');manifest=read(pointer['path']);folder=Path(pointer['path']).parent
    studies=[]
    for group in manifest['studies']:
        cases=[]
        saved=read(Path('runs/sites/study')/(group['id']+'.json'))
        byid={c['case_id']:c for c in saved['cases']}
        for path in sorted((folder/'analysis').glob(group['key']+'-case-*.json')):
            c=read(path);config=copy.deepcopy(byid[c['case_id']]['config']);config['lifecycle'].pop('maintenance_policy')
            matched=dict(config=config,environment=c['environment_id'],controller=c['controller'])
            pair=hashlib.sha256(json.dumps(matched,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            prefixes=[]
            for original in c['prefixes']:
                w=copy.deepcopy(original);service=w.pop('service_ending_work') or {}
                executive=service.get('executive') or {}
                w['terminal_service']={k:service.get(k) for k in ('robots','support','portable','cleaning_kits','calibration_kits','service_kits')}
                w['terminal_service']['open_orders']=[{k:o.get(k) for k in ('order_id','action','target','status','phase','reason','started_at')} for o in executive.get('orders',[]) if o['status'] not in ('completed','cancelled','failed')]
                prefixes.append(w)
            cases.append(dict(case_id=c['case_id'],label=c['label'],policy=c['policy'],seed=c['seed'],controller=c['controller'],pair=pair,environment_id=c['environment_id'],design_id=c['design_id'],independent=dict(status=c['independent']['status'],checks=c['independent']['checks'],failures=c['independent']['failures']),prefixes=prefixes,original_detail=str(path.relative_to(ROOT))))
        pairs={}
        for c in cases:pairs.setdefault(c['pair'],{})[c['policy']]=c
        deltas=[]
        for key,policies in pairs.items():
            if 'none' not in policies:continue
            b=policies['none']['prefixes'][-1]
            for policy,c in policies.items():
                if policy=='none':continue
                last=c['prefixes'][-1]
                reversals=[]
                signs=[]
                for x,y in zip(policies['none']['prefixes'],c['prefixes'],strict=True):
                    if x['boundary_hour']!=y['boundary_hour']:raise ValueError('Unmatched windows')
                    delta=y['methane_kg']-x['methane_kg'];sign=1 if delta>1e-6 else -1 if delta < -1e-6 else 0
                    if sign:signs.append((x['boundary_hour'],sign))
                for a,z in zip(signs,signs[1:]):
                    if a[1]!=z[1]:reversals.append([a[0],z[0]])
                deltas.append(dict(case_id=c['case_id'],baseline=policies['none']['case_id'],policy=policy,methane_kg=last['methane_kg']-b['methane_kg'],allocated_eur=last['total_eur']-b['total_eur'] if last['total_eur'] is not None and b['total_eur'] is not None else None,cash_eur=last['lifecycle']['cash_eur']-b['lifecycle']['cash_eur'],boundary_reversals=reversals))
        studies.append(dict(**group,cases_expected=group['cases'],case_records=cases,paired_deltas=deltas,publication=read(folder/(group['key']+'-publication.json'))))
    preservation=[]
    for name in ('recovery','cleaning','information','corrected-support','provision','interface'):
        p=read(ROOT/'preservation'/(name+'.json'),{});p.pop('cases',None);preservation.append(dict(name=name,**p,offline=read(ROOT/'preservation'/(name+'-offline.json'))))
    qualification=read(ROOT/'qualification.json',{})
    cases=[c for g in studies for c in g['case_records']]
    gates=dict(numerical_cases=len(cases)==116 and all(c['independent']['status']=='passed' for c in cases),preservation=len(preservation)==6 and all(v.get('matched_traces')==v.get('total') and v.get('offline',{} ) and v['offline']['complete_archives_passed'] for v in preservation),site_bundles=all(g['publication'] and g['publication']['restored_reference']['status']=='passed' for g in studies),qualification=qualification.get('passed',False),new_offline=read(ROOT/'offline.json',{}).get('offline_passed',False),observability=read(ROOT/'observability.json',{}).get('passed',False))
    data=dict(version='release-2-report/1',programme=manifest['id'],source=manifest['source']['content_hash'],studies=studies,preservation=preservation,qualification=qualification,offline=read(ROOT/'offline.json'),observability=dict(passed=read(ROOT/'observability.json',{}).get('passed',False),cases=len(read(ROOT/'observability.json',{}).get('cases',[]))),gates=gates,complete=all(gates.values()),totals=dict(cases=len(cases),expected_cases=116,hours=sum(c['prefixes'][-1]['boundary_hour'] for c in cases),expected_hours=sum(g['hours'] for g in studies),independent_checks=sum(c['independent']['checks'] for c in cases)),annual_cash=read(folder/'annual-cash.json',[]))
    (ROOT/'summary.json').write_text(json.dumps(data,indent=2,allow_nan=False))
    return data

if __name__=='__main__':
    d=build();print(json.dumps(dict(totals=d['totals'],gates=d['gates'],complete=d['complete'])))
