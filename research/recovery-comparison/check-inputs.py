"""Check original manifests and weather operands across the release comparisons."""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STORE=ROOT.parents[1]/'runs/studies'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def records(identifier):
    p=json.loads((ROOT/identifier/'programme.json').read_text())
    result=[]
    for entry in p['entries']:
        m=json.loads((STORE/entry['edition_id']/'manifest.json').read_text())
        result.extend((entry,case,m) for case in m['cases'])
    return result


def weather(entry,case):
    return json.loads((STORE/entry['edition_id']/'inputs'/(case['weather_hash']+'.json')).read_text())


main,windows,repeats=[records(x) for x in sys.argv[1:4]]
checks=[]
for kind,rows,condition in [('window',windows,'persistent-damage'),('repeat',repeats,'normal-service')]:
    for e,c,m in rows:
        a,b,n=next(x for x in main if x[0]['condition']==condition and x[0]['arm']==e['arm'] and x[1]['seed']==c['seed'])
        left=b['config']; right=json.loads(json.dumps(c['config']))
        policies=json.loads(json.dumps(c['policies']))
        if kind=='window':
            assert right['recovery_policy']['maximum_wait_hours']==24
            assert left['recovery_policy']['maximum_wait_hours']==12
            right['recovery_policy']['maximum_wait_hours']=12
            for name in policies:
                assert policies[name]['recovery']['maximum_wait_hours']==24
                policies[name]['recovery']['maximum_wait_hours']=12
        assert left==right,(kind,e['arm'],c['seed'],'configuration mismatch')
        assert b['policies']==policies,(kind,e['arm'],c['seed'],'other policy mismatch')
        assert n['source_hash']==m['source_hash']
        wa,wb=weather(a,b),weather(e,c)
        changed_keys=[k for k in set(wa)|set(wb) if wa.get(k)!=wb.get(k)]
        # These two hashes bind full controller/execution configurations, so a
        # recovery-window change alters them even though weather inputs agree.
        pa=wa.pop('performance_boundary');pb=wb.pop('performance_boundary')
        assert set(pa)==set(pb)=={'version','controller','execution'}
        assert pa['version']==pb['version']=='observed-performance/1'
        assert wa==wb,(kind,e['arm'],c['seed'],'weather operands differ')
        if kind=='repeat':assert not changed_keys
        checks.append(dict(kind=kind,arm=e['arm'],seed=c['seed'],parent_case=b['case_id'],paired_case=c['case_id'],
            config_match_except_declared_window=True,policy_match_except_declared_window=True,source_match=True,
            weather_operands_match=True,weather_operand_hash=digest(wa),
            weather_envelope_changed_keys=changed_keys,
            original_weather_envelopes=[b['weather_hash'],c['weather_hash']],
            original_performance_boundaries=[pa,pb]))
out=dict(version='recovery-matched-input-check/1',scope='Manifest and weather-operand comparisons, not outcome validation. The sensitivity changes only the declared recovery wait. Its full-configuration performance-boundary hashes differ; weather times, truth, templates, vintages, snapshots and other fields remain exactly equal. Numerical repeats retain identical complete envelopes.',checks=checks)
with (ROOT/'validation/paired-manifests.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
print(len(checks),'matched case pairs passed')
