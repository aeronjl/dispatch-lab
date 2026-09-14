"""Source-bound independent checks and terminal comparisons of completed R2 cases.

Partial and failed executions remain in the study. This reader never resumes or
changes a case. Compact receipts are separately saved from the original results.
"""
import itertools, json, time
from pathlib import Path
from methane.config import Config
from methane.provenance import LOADED_SOURCE
from methane.simulation import summarise
from methane.siting.production import entries, PeriodRows, directory, state
from methane.siting.store import Store, atomic, encode
from methane.siting.verification import verify_case

class Prefix:
    def __init__(self,rows,n):self.rows=rows;self.n=n
    def __len__(self):return self.n
    def __iter__(self):return itertools.islice(self.rows,self.n)
    def __getitem__(self,k):
        if isinstance(k,slice):return list(self)[k]
        i=k if k>=0 else self.n+k
        if i<0 or i>=self.n:raise IndexError(i)
        return self.rows[i]

FIELDS=('hours','methane_kg','utilisation','h2_produced_kg','curtailed_kwh','reactor_starts','electrolyser_starts','forced_downtime_hours','total_eur','eur_per_kg_ch4','assumed_contribution_eur','variable_and_wear_eur','ending','co2_rejected_kg','false_alarms','uncertain_hours','fallbacks','limited_solves','max_balance_error','field_energy_kwh','service_outcomes')
def compact(summary,truth):
    value={k:summary.get(k) for k in FIELDS}
    lc=summary['lifecycle']
    value['lifecycle']={k:lc.get(k) for k in ('cash_eur','construction_capital_eur','consumed_parts_eur','maintenance_resource_eur','project_crew_hours','packages','accepted_capacity','ending_condition','verified_replacements','unresolved_jobs','expenditure')}
    value['retrospective_condition']=truth['lifecycle_condition']
    value['service_inventories']=summary.get('field_operations',{}).get('inventories')
    value['service_ending_work']=summary.get('service_work')
    return value

s=Store();pointer=json.loads(Path('research/release-2/active-programme.json').read_text());p=json.loads(Path(pointer['path']).read_text());out=Path(pointer['path']).parent/'analysis';out.mkdir(exist_ok=True)
if LOADED_SOURCE['content_hash']!=p['source']['content_hash']:raise ValueError('New checker source: review and record a separate analysis edition')
for group in p['studies']:
    manifest=s.get('study',group['id']);cases=[]
    for case in manifest['cases']:
        receipt=out/(group['key']+'-'+case['case_id']+'.json')
        if receipt.exists():cases.append(json.loads(receipt.read_text()));continue
        path=directory(s,group['id'])/case['case_id']/'summary.json'
        while not path.exists():
            status=state(s,group['id'])['status']
            if status in ('invalid','incomplete','cancelled','interrupted'):raise ValueError('Saved unfinished study: '+status)
            time.sleep(15)
        original=json.loads(path.read_text());items=entries(s,group['id'],case['case_id']);rows=PeriodRows(s,items,case['controller']);truth=rows.truth()
        independent=verify_case(s,group['id'],case['case_id'])
        windows=sorted({min(case['hours'],v) for v in (24,72,168,720,2160,4380,8760)})
        prefixes=[]
        for n in windows:
            summary=original if n==case['hours'] else summarise(Prefix(rows,n),Config.from_dict(case['config']),Prefix(truth,n))
            prefixes.append(dict(boundary_hour=n,**compact(summary,truth[n-1])))
        record=dict(study_id=group['id'],case_id=case['case_id'],label=case['label'],design_id=case['design_id'],environment_id=case['environment_id'],controller=case['controller'],seed=case['config']['scenario']['seed'],policy=case['config']['lifecycle']['maintenance_policy'],source=p['source']['content_hash'],independent=independent,prefixes=prefixes)
        atomic(receipt,encode(record));cases.append(record);print(group['key'],case['case_id'],independent['status'],independent['checks'],'checks',flush=True)
        if independent['status']!='passed':raise ValueError('Saved independent failures; do not hide them')
    atomic(out/(group['key']+'-index.json'),encode(dict(study_id=group['id'],source=p['source']['content_hash'],cases=[dict(case_id=c['case_id'],label=c['label'],checks=c['independent']['checks'],status=c['independent']['status'],path=str(out/(group['key']+'-'+c['case_id']+'.json'))) for c in cases])))
