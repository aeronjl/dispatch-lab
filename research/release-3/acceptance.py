"""Small saved product walkthrough. No policy ranking or field-calibration claim.

Run from the repository root with its locked Python environment. The fixture is
shared with the named Sites continuity test; scripts and tests are in the source
capsule. Each invocation creates a fresh local artifact directory.
"""
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_siting_production import fixture
from methane.learning_lab import deployment, editions, estimators, workflow
from methane.learning_lab.fixtures import teaching_dataset
from methane.provenance import LOADED_SOURCE
from methane.siting import production, reporting
from methane.siting.store import Store


def main():
    root = ROOT / 'build' / 'release-3' / ('acceptance-' + uuid.uuid4().hex[:12])
    store = Store(root / 'original')
    dataset = teaching_dataset(store)
    evaluations = [estimators.fit(store, dataset['id'], task=task) for task in estimators.TASKS]
    pv = next(e for e in evaluations if e['model']['task'] == 'pv')
    registration = deployment.register(store, name='Saved shadow acceptance', model_id=pv['model_id'])
    reserve = deployment.register(store, name='Reserve hypothesis / user-run template', mode='homeostatic')
    design, environment = fixture(store, 4)
    recipe = workflow.comparison_template(store, design, environment, [reserve['id']])
    study = production.create(store, name='Release 3 product acceptance', cases=[dict(design_id=design, environment_id=environment, deployment_id=registration['id'])], partition_hours=2)
    save = production.save_period
    def stop(s, result):
        key = save(s, result)
        production.cancel(s, study['id'])
        return key
    production.save_period = stop
    try:
        production.execute(store, study['id'])
    finally:
        production.save_period = save
    interrupted = production.inspect(store, study['id'])
    assert interrupted['cases'][0]['completed_hours'] == 2
    prefix = production.entries(store, study['id'], 'case-001')[0]
    (production.directory(store, study['id']) / 'cancel').unlink()
    production.execute(store, study['id'])
    completed = production.inspect(store, study['id'])
    assert completed['cases'][0]['completed_hours'] == 4
    assert production.entries(store, study['id'], 'case-001')[0] == prefix
    repeat = editions.repeat(store, study['id'])
    production.execute(store, repeat['id'])
    difference = editions.compare(store, study['id'], repeat['id'])
    assert not difference['missing_hours']
    publication = reporting.publish(store, 'study', study['id'])
    bundle = reporting.bundle(store, publication['publication_id'])
    restored = Store(root / 'restored')
    reporting.restore(bundle['path'], restored)
    assert restored.get('model', pv['model_id']) == store.get('model', pv['model_id'])
    assert restored.read_raw(dataset['observations_sha256']) == store.read_raw(dataset['observations_sha256'])
    ep = reporting.publish(store, 'evaluation', pv['id'])
    eb = reporting.bundle(store, ep['publication_id'])
    receipt = dict(
        source={k: LOADED_SOURCE[k] for k in ('revision', 'content_hash', 'dirty')},
        scope='Product acceptance: constructed observation channels and four synthetic operating hours. No field validation or policy ranking.',
        root=str(root.relative_to(ROOT)), dataset_id=dataset['id'],
        evaluations=[{k:e.get(k) for k in ('id','model_id','status','comparisons','rows_per_split','reason')} for e in evaluations],
        study_id=study['id'], interrupted_hours=2, resumed_hours=4,
        unchanged_prefix=True, numerical_edition_id=repeat['id'],
        differences={k:difference.get(k) for k in ('id','status','comparison','differences','missing_hours','input_comparison')},
        registered_summary=completed['cases'][0]['summary']['experimental_policy'],
        user_run_recipe=dict(study_id=recipe['study_id'], template_id=recipe['template']['id'], case_labels=[c['label'] for c in recipe['template']['recipe']['cases']], boundary=recipe['template']['boundary']), recipe_executed=False,
        portable_bundles=[dict(path=str(Path(b['path']).relative_to(ROOT)), bytes=Path(b['path']).stat().st_size, uncompressed_bytes=b['uncompressed_bytes'], omissions=b['manifest'].get('omissions',[])) for b in (bundle,eb)],
        restored_original_model_and_observations=True,
        participant_sessions=0, off_machine_restore=False,
    )
    target=ROOT/'research/release-3/acceptance.json'
    target.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(receipt=str(target),root=str(root),difference_status=difference['status']),indent=2))

if __name__ == '__main__':
    main()
