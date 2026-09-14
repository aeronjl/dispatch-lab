"""Preserve a dated engineering review of the original qualification source."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from methane.assumptions import freshness
from methane.provenance import LOADED_FILES, LOADED_SOURCE
from methane.siting.production import directory
from methane.siting.store import Store
from methane.source_capsule import decode

root = Path(__file__).resolve().parent
p = json.loads((root / '3a3e10655452448a91ab784fb43cc0bd/programme.json').read_bytes())
s = Store(p['store_root'])
capsule = json.loads((directory(s, p['groups'][0]['study_id']) / 'source-capsule.json').read_bytes())
old = decode(capsule)
changes = {
    'methane/documentation.py': 'Current reader exposes topic-specific operands and relevant parameter references; reads the original decision estimate. Changes display/report projection only.',
    'methane/release_qualification.py': 'Future programme preparation now also rejects stale assumption mechanism bindings. Original frozen studies are preserved.',
    'methane/service_learning.py': 'Teaching inspection charts hide ineligible raw values until the clock reaches availability. No simulation observation kernel change.',
    'methane/services/obligation_recovery.py': 'Rejects non-advancing or greater-than-1000-increment probe schedules. None of the declared qualification parameters reaches this guard; ordinary target calculation is unchanged.',
}
changed = [k for k, v in old.items() if k.startswith('methane/') and LOADED_FILES.get(k) != v]
assert set(changed) == set(changes), 'New source differences require an authored review'
a = json.loads(old['docs/assumption-review.json'])
b = json.loads(LOADED_FILES['docs/assumption-review.json'])
assert a['parameters'] == b['parameters'] and a['sources'] == b['sources']
group_changes = []
for key, group in a['groups'].items():
    for field in ('boundary', 'next_data', 'sources'):
        assert group.get(field) == b['groups'][key].get(field)
    for field in group:
        if field != 'bindings' and group[field] != b['groups'][key].get(field):
            group_changes.append(dict(group=key, field=field, original=group[field], release=b['groups'][key].get(field)))
value = dict(
    version='release-one-historical-source-review/1',
    reviewed_at=datetime.now(timezone.utc).isoformat(),
    reviewer='Engineering agent; source-diff and record review, not empirical validation',
    frozen_source=p['groups'][0]['source'], frozen_capsule_sha256=capsule['sha256'],
    current_source=LOADED_SOURCE['content_hash'],
    original_assumption_freshness=freshness(a, old),
    original_registry_edition=a['edition'], current_registry_edition=b['edition'],
    parameter_evidence_unchanged=True, source_registry_unchanged=True,
    capability_boundaries_and_evidence_needs_unchanged=True,
    narrative_changes=group_changes,
    narrative_review='Final review adds the implemented version-5 deadline mechanism, its checks and new topic bindings. It does not add calibration, repair capabilities or change parameter evidence.',
    changes=[dict(path=k, frozen_sha256=hashlib.sha256(old[k]).hexdigest(), release_sha256=hashlib.sha256(LOADED_FILES[k]).hexdigest(), review=changes[k]) for k in changed],
    unchanged_numerical_files={k: hashlib.sha256(v).hexdigest() for k, v in old.items() if k.startswith('methane/') and k not in changed},
    outcome='Reviewed for the declared numerical fixture; original stale documentation remains stale. No new calibration or retroactive original review is asserted.',
    scope='All 104 cases retain the frozen source and independent audits. The final source has a separate full regression and 36-hour numerical reproduction. Teaching and reader corrections do not relabel the frozen study as a final-source execution.',
)
with (root / 'frozen-source-review.json').open('x') as f:
    json.dump(value, f, indent=2)
print('Original stale groups:', [k for k, v in value['original_assumption_freshness'].items() if v == 'stale'])
