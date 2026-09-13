"""Extract the preselected fixed-mode, seed-7 deadline example from sealed runs."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from methane.evidence import load

cases=[]
for label, filename in zip(('12-hour window','24-hour window'),sys.argv[1:3]):
    summary=json.loads(Path(filename).read_text())
    case=next(x for x in summary['cases'] if x['condition'] in ('persistent-damage','verification-window-24h') and x['arm']=='fixed' and x['seed']==7)
    if case['status']!='complete':raise ValueError('Selected trace is incomplete; keep that result visible')
    r=load(case['archive']);name=next(iter(r['records']))
    truth={x['hour']:x for x in r['retrospective_truth_by_controller'][name]}
    rows=[]
    for row in r['records'][name]:
        rec=row['decision'].get('recovery_planning',{})
        rows.append(dict(hour=row['hour'],pv_kw=row['pv_kw'],
            requested_kw=row['requested']['electrolyser_kw'],delivered_kw=row['applied']['electrolyser_kw'],
            estimated_capacity_kw=row['decision']['diagnosis']['capacity_kw'],
            true_capacity_kw=truth[row['hour']]['capacity_kw'],
            methane_kg=row['applied']['methane_kg'],ending_battery_kwh=row['state']['battery_kwh'],
            status=rec.get('status'),probe=row['decision']['probe']))
    cases.append(dict(label=label,archive=case['archive'],run_id=r['run_id'],
        integrity_sha256=r['integrity_sha256'],source_hash=case['source_hash'],
        study_report=case.get('study_report'),rows=rows))
result=dict(version='recovery-window-trace/1',selection='Fixed service uncertainty, event seed 7; selected before the sensitivity completed. Other outcomes remain in the full table.',
    timing='Power and output are hourly applied interval values. Estimated capacity is the decision-start estimate. True capacity is explicitly retrospective and was not supplied to the controller.',cases=cases)
with (Path(__file__).resolve().parent/'window-trace.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
