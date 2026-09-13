"""Compact descriptive outcomes from one immutable programme report revision."""
import collections
import json
import statistics
import sys
from pathlib import Path
from report_metrics import episode_metrics

p = Path(sys.argv[1])
r = json.loads(p.read_text())
records = r['records']
out = dict(report=str(p), source_hashes=sorted({x['source_hash'] for x in records}),
           status_counts=dict(collections.Counter(x['status'] for x in records)),
           independent_checks=dict(collections.Counter(str((x.get('audit') or {}).get('passed')) for x in records)),
           matching=r['matching'], null=r['null_trace_identical_by_seed'],
           null_numerical_spread=r['null_numerical_spread'], groups=[], cases=[])
for x in records:
    metrics=next(iter((x.get('metrics') or {}).values()),{})
    fields=metrics.get('field_operations') or {}
    terminal=(x.get('verification') or [{}])[-1]
    item=dict(condition=x['condition'],arm=x['arm'],seed=x['seed'],repeat=x['repeat'],
              status=x['status'],edition_id=x['edition_id'],case_id=x['case_id'],run_id=x.get('run_id'),archive=x.get('archive'),error=x.get('error'),
              audit=x.get('audit'),source_hash=x['source_hash'],weather_hash=x['weather_hash'],
              methane_kg=x.get('methane_kg'), ending=x.get('ending'),
              service_inventories=fields.get('inventories'),
              mission_counts=x.get('mission_counts'), service_fallback_intervals=x.get('fallback_intervals'),
              candidate_states=x.get('solver_statuses'), conditional_returns=x.get('conditional_returns'),
              verification_ending=terminal,metrics={k:metrics.get(k) for k in
                ('total_eur','assumed_contribution_eur','eur_per_kg_ch4','curtailed_kwh','utilisation',
                 'electrolyser_starts','reactor_starts','forced_downtime_hours','detection_delay_hours',
                 'false_alarms','uncertain_hours','capacity_restored_hour','capacity_confirmed_hour',
                 'limited_solves','fallbacks','field_energy_kwh','hours')},
              field_cost_views=fields.get('views'),field_quantities=fields.get('quantities'))
    item['verification_episode_metrics']=episode_metrics(x.get('verification') or [])
    service=metrics.get('service_work') or {}
    item['ending_service_resources']=(service.get('executive') or {}).get('resources',[])
    surface=service.get('surface') or {}
    item['ending_surface']=surface
    sections=surface.get('sections',[])
    area=sum(s['area_m2'] for s in sections)
    item['ending_modelled_transmission']=sum(s['area_m2']*s['transmission'] for s in sections)/area if area else None
    progress_path=Path(__file__).resolve().parents[2]/'runs/studies'/x['edition_id']/'progress.json'
    if progress_path.exists():
        progress=json.loads(progress_path.read_text())
        if progress.get('report_id'):
            item['study_report']='../../runs/studies/'+x['edition_id']+'/reports/'+progress['report_id']+'.html'
    out['cases'].append(item)
for condition in sorted({x['condition'] for x in records}):
    for arm in ('fixed','adaptive','risk-aware'):
        group=[x for x in out['cases'] if x['condition']==condition and x['arm']==arm]
        valid=[x for x in group if x['status']=='complete']
        summary=dict(condition=condition,arm=arm,cases=len(group),complete=len(valid))
        for key in ('methane_kg','service_fallback_intervals'):
            values=[x[key] for x in valid if x.get(key) is not None]
            summary[key]=dict(mean=statistics.mean(values),minimum=min(values),maximum=max(values)) if values else None
        for key in ('assumed_contribution_eur','total_eur','forced_downtime_hours','limited_solves','fallbacks'):
            values=[x['metrics'][key] for x in valid if x['metrics'].get(key) is not None]
            summary[key]=dict(mean=statistics.mean(values),minimum=min(values),maximum=max(values)) if values else None
        summary['confirmed_recovery_cases']=sum(x['metrics'].get('capacity_confirmed_hour') is not None for x in valid)
        summary['ending_escalations']=sum(x['verification_ending'].get('status')=='escalation-required' for x in valid)
        summary['missions']=dict(sum((collections.Counter(x.get('mission_counts') or {}) for x in valid),collections.Counter()))
        out['groups'].append(summary)
path=p.parent / (p.stem + '-summary.json')
with path.open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
print(path)
print(json.dumps({k:v for k,v in out.items() if k not in ('cases','matching','null_numerical_spread','groups')},indent=2))
