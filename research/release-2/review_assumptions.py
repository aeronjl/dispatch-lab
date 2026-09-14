"""Register the new lifecycle hypotheses; preserve old parameter claims and sources."""
import hashlib,json
from pathlib import Path
from methane.assumptions import flatten, reference_configuration

path=Path('docs/assumption-review.json');review=json.loads(path.read_text())
review['edition']='2026-09-14 / 11'
review['release_review']='Release 2: explicit commissioning, condition observations, replacement stock and chronological accounting. Rates are scoped literature hypotheses; work, sensor and procedure values remain assumptions. No new field calibration.'
review['sources']['pv-degradation-compendium']={
 'title':'Jordan et al. Compendium of photovoltaic degradation rates (2016)', 'url':'https://doi.org/10.1002/pip.2744',
 'finding':'Crystalline-silicon median loss 0.5–0.6%/year; mean 0.8–0.9%/year. Technology, measurement and soiling differences affect interpretation.',
 'applicability':'Broad literature population; not a calibrated European site or a wear-out probability. Linear full-asset loss is a reduced model.', 'access':'Primary abstract read 2026-09-14'}
review['sources']['lifecycle-fixture']={
 'title':'Dispatch Lab declared lifecycle work and observation fixture', 'url':'docs/lifecycle.md',
 'finding':'No measured equipment source is supplied for the illustrative project crew, work duration, condition channel, part procurement or acceptance/replacement challenge.',
 'applicability':'Explicit evidence gap. Software checks establish reduced accounting only; the local contract records assumptions, not empirical evidence.', 'access':'Authored assumptions, 2026-09-14'}
for key,title,topics,mechanism,boundary,need in (
 ('commissioning','Commissioning and support chronology',['deployment','hardware','maintenance','siting'],'Declared work, acceptance, progressive capacity and departure, finite additional crew and external equipment energy.','No calibrated robot throughput or real electrical/pressure certification.','Dated installation method statement, labour/equipment invoices, access and acceptance/rework observations.'),
 ('lifecycle-condition','Condition, replacement and observation',['condition','maintenance','electrolyser','solar','economics'],'Solar calendar decline and PEM usage voltage growth; delayed noisy observations drive bounded condition replacement and finite stock.','No remaining-life oracle, calibrated dynamic degradation, automatic manipulation or unrelated fault repair.','Matched age/load/temperature and voltage/IV observations; reference quality and delay, replaceable-module costs, procedure outcomes and spare logistics.')
):
 review['groups'][key]=dict(id=key,title=title,topics=topics,mechanism=mechanism,boundary=boundary,next_data=need,sources=['doe-pem','pv-degradation-compendium','lifecycle-fixture'],checks=['tests/test_lifecycle.py'],priority=1,evidence_status='Reduced hypothesis and explicit evidence gaps',bindings={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['methane/config.py','methane/lifecycle/configuration.py','methane/lifecycle/runtime.py','methane/lifecycle/ports.py','methane/lifecycle/accounting.py','methane/lifecycle_reference.py']})
review['parameters']=[p for p in review['parameters'] if not p['path'].startswith('lifecycle.')]
known={p['path'] for p in review['parameters']}
for key,default in flatten(reference_configuration()).items():
 if not key.startswith('lifecycle.') or key in known:continue
 field=key.split('.')[-1];values=default if isinstance(default,list) else [default]
 group='lifecycle-condition' if '.conditions.' in key else 'commissioning'
 category='equipment';unit='configuration';samples=None
 if field in ('version','scope','evidence','evidence_ids','id','asset','method','labour_basis') or field=='[]':category='implementation'
 elif any(k in field for k in ('eur','price')):category='economic';unit='EUR';samples=sorted({float(x)*m for x in values if type(x) in (float,int) for m in (.5,1,2)})
 elif field in ('maintenance_policy','replacement_threshold','periodic_hours','maximum_wait_hours','crew_shift_start','maximum_attempts','replenishment'):category='policy'
 elif field.startswith('initial_') or field in ('fraction','opening_spares','stock_capacity','supplier_spares','crew_hours_per_day'):category='design'
 elif field in ('start_hour','end_hour','failed_acceptance_attempts','replacement_success_fraction','sensor_dropout','resource'):category='scenario'
 if 'hours' in field or field in ('start_hour','end_hour'):unit='h'
 elif 'noise_fraction' in field or field in ('fraction','replacement_threshold','replacement_success_fraction'):unit='fraction'
 elif field.endswith('spares') or field in ('stock_capacity','maximum_attempts','failed_acceptance_attempts'):unit='count'
 elif 'kwh' in field and 'eur' not in field:unit='kWh/work h'
 if field.endswith('eur_per_hour'):unit='EUR/h'
 if field.endswith('eur_per_kwh'):unit='EUR/kWh'
 if field=='replacement_part_eur':unit='EUR/part'
 if field=='pv_loss_per_year':unit='fraction/year';samples=[.0025,.005,.01]
 if field=='stack_mv_per_1000h':unit='mV/1000 operating h';samples=[2,4.8,8]
 if field=='stack_reference_voltage':unit='V';samples=[1.8,1.9,2]
 if field=='sensor_noise_fraction':samples=[0,.002,.01]
 if field=='replacement_success_fraction':samples=[.5,.8,1]
 if category=='equipment' and 'hours' in field:samples=sorted({max(1,float(x)*m) for x in values for m in (.5,1,2)})
 item=dict(id='parameter:'+key,path=key,label=field.replace('_',' '),group=group,category=category,unit=unit,reference_default=default,evidence_status='Literature-informed hypothesis' if field in ('pv_loss_per_year','stack_mv_per_1000h','stack_reference_voltage') else 'Declared choice' if category in ('design','policy','implementation') else 'Uncalibrated assumption',applicable_range=None,range_note='Validation bounds are not a plausible uncertainty distribution; unavailable equipment-specific evidence remains explicit.')
 if samples:item.update(sensitivity_values=samples,sensitivity_scope='Disclosed robustness scenarios, not empirical quantiles or probability weights. Review structural and equipment applicability before interpreting comparisons.')
 review['parameters'].append(item)
path.write_text(json.dumps(review,indent=2,ensure_ascii=False)+'\n')
print('Registered',sum(p['path'].startswith('lifecycle.') for p in review['parameters']),'lifecycle paths')
