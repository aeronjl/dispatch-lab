"""Extract a post-hoc counterexample; does not rerun or alter its decisions."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from methane.evidence import load

summary = json.loads((HERE / '621aec1013f54ddf867731447170cd24/reports/f3bd14d270fc42ccae26ae64a11e525c-summary.json').read_text())
case = next(x for x in summary['cases'] if x['arm'] == 'risk-aware' and x['seed'] == 7)
assert case['status'] == 'complete'
record = load(case['archive'])
controller = next(iter(record['records']))
truth = {x['hour']: x for x in record['retrospective_truth_by_controller'][controller]}
rows = []
for row in record['records'][controller]:
    rows.append(dict(
        hour=row['hour'], pv_kw=row['pv_kw'],
        requested_kw=row['requested']['electrolyser_kw'],
        applied_kw=row['applied']['electrolyser_kw'],
        decision_start_capacity_kw=row['decision']['diagnosis']['capacity_kw'],
        observations_after=row['observations_after'],
        diagnosis_after=row['diagnosis_after'],
        recovery_status=row['decision']['recovery_planning']['status'],
        probe_requested=row['decision']['probe'],
        retrospective_capacity_kw=truth[row['hour']]['capacity_kw'],
        methane_kg=row['applied']['methane_kg'],
    ))
assert rows[15]['diagnosis_after']['status'] == 'ambiguous'
assert rows[15]['decision_start_capacity_kw'] == 450
assert rows[15]['diagnosis_after']['capacity_kw'] < 135
assert all(r['retrospective_capacity_kw'] == 450 for r in rows)
output = dict(
    version='recovery-repeat-counterexample/1',
    selection='Post-hoc inspection of the largest absolute normal-service numerical-repeat methane difference. Not a preselected success or an independent causal ablation.',
    timing='Decision-start estimates and recovery status precede interval observations and diagnosis_after. Retrospective capacity was never supplied to the controller.',
    limitation='The H15 observation identifies the harmful estimate transition, not the first divergence between the two optimisation executions. No general causal attribution to risk preference is established.',
    archive=case['archive'], integrity_sha256=record['integrity_sha256'],
    source_hash=case['source_hash'], study_report=case['study_report'], rows=rows,
)
with (HERE / 'repeat-counterexample.json').open('x') as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
print('48 original intervals retained, with explicit observation timing and retrospective boundary')
