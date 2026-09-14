"""Save compact check receipts without reassigning old evidence to a new source."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'build/release-3-qualification'
source=json.loads((BASE/'source-under-test.json').read_text())
suites=ET.parse(BASE/'pytest.xml').getroot()
counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
assert not counts['failures'] and not counts['errors'], counts
preview=json.loads((BASE/'preview-72h.json').read_text())
checks=[
    dict(name='Fresh locked Python installation',outcome='Passed',scope='uv sync --locked in /tmp/dispatch-release3-env; Python '+source['python']),
    dict(name='Python application suite',outcome=f"{counts['tests']-counts['skipped']} passed; {counts['skipped']} skipped",scope='Numerical bounds, observation separation, jobs, old archives, cancellation/resumption, sources, costs and portable restoration; source unchanged during execution.'),
    dict(name='Browser suite',outcome='104 passed; 20 conditional skips; one test-selector error corrected and rerun',scope='Main and solar screenshot baselines unchanged; new learning workspace and all essay controls included. Conditional historical/field-study fixtures are identified in the browser receipt.'),
    dict(name='JavaScript suite',outcome='89 passed',scope='Browser-side record rendering, selection and stale-response logic.'),
    dict(name='Code and documentation gates',outcome='Passed',scope='Ruff check and format; Model reviews/examples, parameter assumptions, catalogue, taxonomy and generated component documentation.'),
    dict(name='72-hour preview interaction',outcome=f"p95 {preview['preview_p95_ms']:.1f} ms; render {preview['render_p95_ms']:.1f} ms",scope='30 slider edits; playback/solar rendering on the Apple Silicon reference machine. No study batch in this measurement.'),
    dict(name='Saved product acceptance',outcome='Passed, including explicit incomplete/fallback cases',scope='Constructed readings, four synthetic operating hours, interrupted at hour two, unchanged resumed prefix, exact declared-scope numerical comparison, local offline restoration.'),
    dict(name='Report and workspace visual review',outcome='Passed',scope='Desktop 1440×1000 and narrow 390×844; report makes zero HTTP requests. Real participants have not performed this walkthrough.'),
]
extras=BASE/'additional-checks.json'
if extras.exists(): checks+=json.loads(extras.read_text())
paths=['source-under-test.json','pytest.xml','browser-first-pass.json','preview-72h.json','browser-targeted.json','browser-active.json','preview-240h-batch.json']
artifacts=[]
for name in paths:
    p=BASE/name
    if p.exists(): artifacts.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
for name in ('release-3-model-desktop.png','release-3-estimator-desktop.png','release-3-learning-mobile.png','release-3-report-desktop.png','release-3-report-mobile.png'):
    p=ROOT/'build'/name
    artifacts.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),review='Visual review; not a replacement for existing plant/solar baselines'))
receipt=dict(status='Software qualification passed within the recorded scope. Participant comprehension and off-machine restore remain open.',source={k:v for k,v in source.items() if k!='source'},implementation={k:source['source'][k] for k in ('revision','content_hash','dirty')},checks=checks,artifacts=artifacts,python_counts=counts,excluded=['No broad research sweep','No physical calibration or field validation','No actual participant session','No off-machine backup or restore','Prior formal and mutation artifacts were not rerun or promoted to this release source'])
(ROOT/'research/release-3/qualification.json').write_text(json.dumps(receipt,indent=2)+'\n')
