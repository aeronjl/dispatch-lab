"""Expose the preserved research programme as recipes; execute no numerical cases."""
import json
from pathlib import Path
from methane.siting.store import Store
from methane.siting.workflow import save_template

root=Path('research/release-2')
pointer=json.loads((root/'active-programme.json').read_text())
p=json.loads(Path(pointer['path']).read_text());store=Store();out=[]
methods={
 'seasonal':'Compare four maintenance rules on identical saved ERA5 weeks, plant assumptions and seeds. Report methane, curtailment, costs and ending energy, gas, thermal, condition, stock and unfinished work at equal boundaries. Separate seed variation from weather samples.',
 'annual':'Compare declared maintenance rules through a continuous London year. Preserve deployment state, condition and stocks across partitions and year boundaries. Report throughput, dated expenses and remaining obligations; do not repeat the first year to invent lifetime cash flow.',
 'uncertainty':'Within each disclosed parameter scenario, compare the four rules with identical information and inputs. Keep scenarios separate; their ranges are not probability intervals. Report failed and unobserved work and conclusions that reverse.',
 'forecast':'Compare Greedy and both MPC objectives with the same eligible original ECMWF issues, six-hour publication lag and ERA5 reference. Separate controller and maintenance-policy effects. Report solver terminations, fallbacks and ending inventories; no requirement that MPC wins.',
}
for g in p['studies']:
 m=store.get('study',g['id'])
 t=save_template(store,g['id'],name='Lifecycle / '+g['key'],question=m['purpose'],method=methods[g['key']],limitations='Existing illustrative European fixture. Whole-asset replacement duration, sensing and degradation are hypotheses, not calibrated service capabilities. ERA5 is reanalysis. Short-window periodic work is due at H168 and therefore unexposed in a 168-hour run. Saved inputs are required; missing data must fail visibly.')
 out.append(dict(key=g['key'],template_id=t['id'],original_study_id=g['id'],cases=len(t['recipe']['cases']),path=str(store.path('template',t['id'])),recipe=t))
(root/'templates.json').write_text(json.dumps(dict(version='release-2-templates/1',programme=p['id'],executed_by_registration=False,templates=out),indent=2))
print(json.dumps([dict(key=t['key'],id=t['template_id'],cases=t['cases']) for t in out]))
