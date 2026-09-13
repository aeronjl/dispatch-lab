"""New predeclared deadline sensitivity after the retained seed-7 pilot.

Only the post-diagnosis/mission recovery wait changes from 12 to 24 hours.
Original service deadlines, prices, physical work and unknown outcomes are held fixed.
"""
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from methane.recovery_comparison import ARMS, ROOT as REPORT_ROOT, VERSION, fixture, specification
from methane.studies import create

folder = REPORT_ROOT / uuid4().hex
folder.mkdir()
p = dict(version=VERSION, created_at=time.time(), basis=None, seeds=[7,17,29], entries=[],
         protocol_scope='Declared 24-hour verification-window sensitivity following the retained 12-hour seed-7 pilot. 48-hour physical horizon, three event seeds and three policy arms. Only the configured recovery wait changes; original service deadlines and physical inputs stay fixed. Not selected on favourable outcomes.',
         weather_scope='Reproducible synthetic weather, identical to the persistent-damage comparison fixture.',
         original_programme='d831e3e1a50b4983b14853c8401c1817', comparison_programme=sys.argv[1])
parent = json.loads((REPORT_ROOT / sys.argv[1] / 'programme.json').read_text())
p['basis'] = parent['basis']
p['seeds'] = parent['seeds']
c = fixture('persistent-damage', parent['basis'])
c = replace(c, recovery_policy=replace(c.recovery_policy, maximum_wait_hours=24))
for arm in ARMS:
    s = specification(c, 'persistent-damage', arm, p['seeds'])
    s['title'] = 'Recovery window 24 hours · ' + arm
    s['question'] = 'Does a longer bounded verification window permit observed tests after an overnight power shortage?'
    m = create(basis=c.to_dict(), specification=s)
    p['entries'].append(dict(condition='verification-window-24h', arm=arm, repeat=1, edition_id=m['edition_id']))
    (folder/'programme.json').write_text(json.dumps(p,indent=2)+'\n')
print(folder)
