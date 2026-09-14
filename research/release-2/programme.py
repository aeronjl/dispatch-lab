"""Release-2 matched, resumable studies over original cached European environments.

Creation freezes designs and source. Execution uses each saved source capsule.
Never overwrites an earlier edition; --new is required for a new programme.
"""
import argparse, copy, json, time, uuid
from dataclasses import replace
from pathlib import Path
from methane.config import Config
from methane.lifecycle.fixtures import illustrative
from methane.provenance import LOADED_SOURCE
from methane.siting.contracts import DeploymentDesign
from methane.siting.production import create, inspect, launch, state as study_state
from methane.siting.store import Store, atomic, encode, digest

ROOT=Path('research/release-2')
POLICIES=('none','periodic','condition','forecast-window')
SEEDS=(7,42)


def design(store, env, policy, *, age=45000, solar_age=20*8766, commission=False, variant='reference'):
    original=store.get('design',env['design_id'])
    base=Config(weather=Config.from_dict(original['config']).weather)
    base=replace(base, scenario=replace(base.scenario,hours=168,horizon_hours=24,seed=7,capacity_fraction=1,flow_bias_fraction=0,solver_seconds=.1), service_policy=None, recovery_policy=None, investigation_policy=None)
    c=illustrative(base,commission=commission,aged=True,policy=policy)
    # Deliberately simple service baseline shared across all maintenance policies.
    from methane.services.configuration import ServiceSystem
    from methane.service_economics import ACTIVITY_VERSION, illustrative as prices
    c=replace(c, service_system=ServiceSystem(cleaning_model='section-optical/1',support_model='logistics/1',environment_source='weather',cleaning_policy='condition',maintenance_enabled=True,outcome_randomness='target-action-request/1'), service_economics=prices(c.costs,version=ACTIVITY_VERSION), sensors=replace(c.sensors,ambiguity_policy='retain-capacity/1'))
    life=copy.deepcopy(c.lifecycle)
    for spec in life['conditions']:
        spec['initial_calendar_hours']=solar_age if spec['asset']=='solar' else 0
        spec['initial_operating_hours']=age if spec['asset']=='electrolyser' else 0
        spec['periodic_hours']=168 if env['hours']<8760 else 4380
    if variant=='slow-low-rate':
        for s in life['conditions']:
            s['replacement_hours']=12;s['pv_loss_per_year']=.0025;s['stack_mv_per_1000h']=2
    if variant=='fast-high-rate':
        for s in life['conditions']:
            s['replacement_hours']=2;s['pv_loss_per_year']=.01;s['stack_mv_per_1000h']=8
    if variant=='support-loss':
        life['outages']=[dict(resource=r,start_hour=24,end_hour=72) for r in ('access','reference','communications')]
        for s in life['conditions']:s['opening_spares']=0;s['delivery_hours']=72
    if variant=='failed-work':
        for s in life['conditions']:s['replacement_success_fraction']=0
    if variant=='unobserved':
        for s in life['conditions']:s['sensor_dropout']=True
    if variant=='low-power':c=replace(c,plant=replace(c.plant,solar_kw=500,battery_kwh=200))
    if variant=='extra-feed':c=replace(c,plant=replace(c.plant,co2_delivery_kg=600))
    c=replace(c,lifecycle=life)
    label=f'{policy} / {variant} / '+('redeployment' if commission else 'operating plant')
    d=DeploymentDesign(site_revision=env['site_revision'],name='R2 '+label,config=c.to_dict(),assumptions=[
        'Reduced whole-asset ageing. Initial exposure is declared, not measured.',
        'Uniform condition across commissioned capacity; not a heterogeneous installation population.',
        'Project crew and work rates are illustrative; field support and project labour are separate.',
        'Rates, reference channel, part prices and failed-work scenarios are not field calibration.',
        'Periodic 168-hour short-window or 4380-hour annual rule is a comparison choice, not a vendor maintenance recommendation.'
    ])
    return store.put('design',d),c


def setup(store):
    envs=store.list('environment')
    seasonal=sorted([e for e in envs if e['hours']==168 and e['information']=='persistence/1'],key=lambda e:(e['site_revision'],e['start']))
    if len(seasonal)!=9:raise ValueError('Expected the nine preserved European seasonal environments; no silent replacement')
    annual=next(e for e in envs if e['hours']==8760 and store.get('site',e['site_revision'])['country']=='GB')
    archived=next(e for e in envs if e['hours']==72 and e['information']=='archived-ifs/1')
    programme=dict(version='release-2-lifecycle-programme/1',id=uuid.uuid4().hex,source=LOADED_SOURCE,policies=POLICIES,seeds=SEEDS,studies=[])
    groups=[]
    cases=[]
    for e in seasonal:
        site=store.get('site',e['site_revision'])
        for policy in POLICIES:
            d,_=design(store,e,policy)
            for seed in SEEDS:cases.append(dict(design_id=d,environment_id=e['id'],controller='Greedy',seed=seed,label=f"{site['name']} / {e['start'][:10]} / {policy} / seed {seed}"))
    groups.append(('seasonal','Four maintenance rules across nine saved ERA5 weeks',cases,'design'))
    cases=[]
    for policy in POLICIES:
        d,_=design(store,annual,policy,age=38000,solar_age=2*8766,commission=True)
        cases.append(dict(design_id=d,environment_id=annual['id'],controller='Greedy',seed=7,label=f'London continuous 2025 / previously used plant deployment / {policy}'))
    groups.append(('annual','Deployment through a full recorded operating year',cases,'design'))
    cases=[]
    e=next(e for e in seasonal if e['start'].startswith('2025-07') and store.get('site',e['site_revision'])['country']=='ES')
    for variant in ('slow-low-rate','fast-high-rate','support-loss','failed-work','unobserved','low-power','extra-feed'):
        for policy in POLICIES:
            d,_=design(store,e,policy,variant=variant)
            cases.append(dict(design_id=d,environment_id=e['id'],controller='Greedy',seed=7,label=f'Seville July / {variant} / {policy}'))
    groups.append(('uncertainty','Declared rate, resource and observation challenges',cases,'design'))
    cases=[]
    for controller in ('Greedy','MPC · methane','MPC · economics'):
        for policy in POLICIES:
            d,_=design(store,archived,policy)
            cases.append(dict(design_id=d,environment_id=archived['id'],controller=controller,seed=7,label=f'Saved forecast issues / {controller} / {policy}'))
    groups.append(('forecast','Maintenance under original archived ECMWF issues',cases,'autonomous'))
    for key,name,cases,mode in groups:
        study=create(store,name='Release 2 · '+name,cases=cases,mode=mode,partition_hours=168,purpose='Compare fixed starting information, actual ending stocks/condition/work and chronological costs. No calibration, optimum-policy or causal ranking claim. Forecast persistence and archived issue cases remain distinct.')
        programme['studies'].append(dict(key=key,id=study['id'],cases=len(cases),hours=sum(c['hours'] for c in study['cases'])))
    directory=ROOT/programme['id'];directory.mkdir(parents=True)
    atomic(directory/'programme.json',encode(programme));atomic(ROOT/'active-programme.json',encode(dict(path=str(directory/'programme.json'),id=programme['id'])))
    return programme,directory


def execute(store,p,directory):
    for group in p['studies']:
        snapshot=inspect(store,group['id'])
        if snapshot['state']['status']!='complete':
            if snapshot['state']['status'] != 'running':launch(store,group['id'])
            previous=None
            while True:
                state=study_state(store,group['id']);description=state.get('description')
                if description!=previous:print(group['key'],state.get('status'),description,flush=True);previous=description
                atomic(directory/(group['key']+'-progress.json'),encode(dict(state=state,note='Lightweight monitor; case entries and summaries are authoritative')))
                if state['status'] not in ('running','pending'):break
                time.sleep(5)
        final=inspect(store,group['id']);atomic(directory/(group['key']+'-result.json'),encode(final))
        print(group['key'],final['state'],flush=True)
        if final['state']['status']!='complete':raise RuntimeError('Saved incomplete study; inspect and resume explicitly')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--new',action='store_true');parser.add_argument('--create-only',action='store_true');args=parser.parse_args();store=Store()
    if args.new:p,directory=setup(store)
    else:
        path=Path(json.loads((ROOT/'active-programme.json').read_text())['path']);p=json.loads(path.read_text());directory=path.parent
    print(json.dumps(dict(programme=p['id'],studies=p['studies'])),flush=True)
    if not args.create_only:execute(store,p,directory)
