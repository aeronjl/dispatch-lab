"""Finish the first annual case, then cancel the optional remaining policies.

Release scope changed on 2026-09-14: the four-policy study remains partial.
This monitor changes no numerical inputs or completed results.
"""
import json
import time
from pathlib import Path
from methane.siting.production import cancel, directory, state
from methane.siting.store import Store, atomic, encode

store = Store()
study_id = 'eb104280b3cbe4bf0dec35384108891b91025799b25c93f76a07da0edc9e4635'
output = Path('research/release-2/annual-acceptance-stop.json')
while not (directory(store, study_id) / 'case-001' / 'summary.json').exists():
    progress = state(store, study_id)
    if progress['status'] != 'running':
        raise RuntimeError(f'Annual acceptance stopped before completion: {progress}')
    time.sleep(5)
request = cancel(store, study_id)
while state(store, study_id)['status'] == 'running':
    time.sleep(5)
receipt = dict(study_id=study_id, representative_case='case-001',
               completed_hours=8760, request=request, final_state=state(store, study_id),
               reason='Product acceptance replaces the full research matrix as the release gate. Remaining cases and partial intervals are preserved.')
atomic(output, encode(receipt))
print(json.dumps(receipt), flush=True)
