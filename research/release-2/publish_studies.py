"""Publish completed lifecycle studies and verify portable Sites restoration.

No publication is reused as evidence for another source. Missing commercial
assumptions remain missing; the annual cash view never fabricates extra years.
"""
import hashlib, json, time
from pathlib import Path
from methane.siting import reporting, cashflow
from methane.siting.production import state, inspect
from methane.siting.store import Store, atomic, encode
from methane.siting.verification import verify_case

store=Store();pointer=json.loads(Path('research/release-2/active-programme.json').read_text());p=json.loads(Path(pointer['path']).read_text());root=Path(pointer['path']).parent
for group in p['studies']:
    target=root/(group['key']+'-publication.json')
    if target.exists():continue
    while state(store,group['id'])['status'] in ('ready','pending','running'):time.sleep(15)
    if state(store,group['id'])['status']!='complete':raise ValueError('Preserved incomplete result requires separate review')
    # Do not publish a favourable conclusion before independent checks finish.
    while not (root/'analysis'/(group['key']+'-index.json')).exists():time.sleep(15)
    value=inspect(store,group['id']);pub=reporting.publish(store,'study',group['id']);print(group['key'],'published',pub['publication_id'],flush=True)
    bundle=reporting.bundle(store,pub['publication_id']);print(group['key'],'bundle',bundle,flush=True)
    path=Path(bundle['path'])
    restored=Store(Path('build/release-2/sites-restored')/group['key'])
    receipt=reporting.restore(path,restored)
    # The restored study's original inputs and all committed period identities are verified.
    # Independently audit one restored case; all source cases were checked separately.
    check=verify_case(restored,group['id'],value['cases'][0]['case_id'])
    if check['status']!='passed':raise ValueError('Restored chronology failed')
    output=dict(study_id=group['id'],source=p['source']['content_hash'],publication=pub,bundle=bundle,bundle_sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),restoration=receipt,restored_reference=check,scope='Complete Sites bundle inventory and restored source/data identities. First restored case independently checked; every original case has its own independent check. No network or new numerical decisions in restoration.')
    if group['key']=='annual':
        cash=[]
        for case in value['cases']:
            assumption=cashflow.defaults(case['config'])
            assumption['life_years']=1;assumption['items']=[i for i in assumption['items'] if i['year']<=1]
            assumption['name']='One recorded lifecycle year / missing quotations remain explicit'
            assumption['assumptions']=['Exactly the recorded chronological year; no weather-year or lifecycle repetition.','Methane acceptance remains its uncontracted default; no implied fuel acceptance.','Illustrative capital and service assumptions are not quotations; missing fields are not zero.']
            report=cashflow.report(store,group['id'],case['case_id'],assumption)
            cash.append(report)
        atomic(root/'annual-cash.json',encode(cash));output['cash_report']='annual-cash.json'
    atomic(target,encode(output));print(group['key'],'restored and checked',flush=True)
