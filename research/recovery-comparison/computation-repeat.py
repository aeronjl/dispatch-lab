"""A second numerical execution of the same non-null normal-service cases.

This is not a new environmental seed or a new physical scenario. It measures
within-mode computation variation under the same finite budgets before ranking modes.
"""
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from methane.recovery_comparison import ARMS, ROOT as REPORT_ROOT, VERSION, fixture, specification
from methane.studies import create

parent=json.loads((REPORT_ROOT/sys.argv[1]/'programme.json').read_text())
folder=REPORT_ROOT/uuid4().hex
folder.mkdir()
p=dict(version=VERSION,created_at=time.time(),basis=parent['basis'],seeds=parent['seeds'],entries=[],
       comparison_programme=sys.argv[1],
       protocol_scope='Second numerical execution of the identical normal-service configuration and three fixed event seeds, across all three modes. Finite budgets and physics are unchanged. These repeats measure computation variation, not independent environmental replication. No null condition is included in this sensitivity.',
       weather_scope='Identical reproducible synthetic input and forecast recipe to the parent normal-service cases.')
c=fixture('normal-service',parent['basis'])
for arm in ARMS:
    s=specification(c,'normal-service',arm,p['seeds'])
    s['title']='Normal service · numerical repeat 2 · '+arm
    s['question']='How large are same-information numerical differences relative to differences between policy modes?'
    m=create(basis=c.to_dict(),specification=s)
    p['entries'].append(dict(condition='normal-service',arm=arm,repeat=2,edition_id=m['edition_id']))
    (folder/'programme.json').write_text(json.dumps(p,indent=2)+'\n')
print(folder)
